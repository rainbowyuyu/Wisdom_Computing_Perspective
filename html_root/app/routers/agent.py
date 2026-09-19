# 智能体：理解用户意图，返回跳转与动作
import json
import logging
import re
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..config import client, api_key
from ..models import AgentRequest
from ..llm_errors import llm_error_message, recoverable_error

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


def generate_plan(prompt):
    """Repair malformed plans once, within the original authorized request."""
    messages=[{'role':'user','content':prompt}]
    for attempt in range(2):
        completion=client.with_options(timeout=40,max_retries=0).chat.completions.create(
            model='qwen-plus',response_format={'type':'json_object'},temperature=0.2,messages=messages)
        raw=completion.choices[0].message.content or ''
        raw=re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip())
        try:
            parsed=json.loads(raw)
            if not isinstance(parsed,dict):raise ValueError('执行计划必须为 JSON 对象')
            steps=parsed.get('steps',[parsed])
            sections={'detect','calculate','devtools','my-formulas','examples','help','chat','settings'}
            if not isinstance(steps,list) or not 1<=len(steps)<=12:raise ValueError('steps 需要包含 1 至 12 个步骤')
            for step in steps:
                if not isinstance(step,dict) or step.get('section') not in sections:raise ValueError('每一步需要有效的 section')
                if step['section']=='chat' and not str(step.get('reply') or '').strip():raise ValueError('回复内容不能为空')
            return parsed
        except (ValueError,TypeError) as error:
            if attempt:raise ValueError('执行计划修复后仍不可用，请重试。') from error
            messages.extend([{'role':'assistant','content':raw[:20000]},
                {'role':'user','content':'执行计划格式检查失败：'+str(error)[:180]+'。请修复并重新输出完整 JSON，保留原题和要求，LaTeX 的反斜杠按 JSON 正确转义。'}])


def sanitize_latex_for_mathlive(latex: str) -> str:
    """将 LaTeX 规范化为 MathLive 可正确解析的格式。"""
    if not latex or not isinstance(latex, str):
        return ""
    s = latex.strip()
    s = re.sub(r"^```(?:latex)?\s*", "", s)
    s = re.sub(r"\s*```\s*$", "", s)
    s = re.sub(r"^\\\[\s*", "", s)
    s = re.sub(r"\s*\\\]\s*$", "", s)
    s = re.sub(r"^\$\$\s*", "", s)
    s = re.sub(r"\s*\$\$\s*$", "", s)
    s = re.sub(r"^\\\(\s*", "", s)  # 处理 \(
    s = re.sub(r"\s*\\\)\s*$", "", s)  # 处理 \)
    s = re.sub(r"\\\(", "", s)  # 移除内联的 \(
    s = re.sub(r"\\\)", "", s)  # 移除内联的 \)
    s = re.sub(r"^\\begin\s*\{\s*displaymath\s*\}\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*\\end\s*\{\s*displaymath\s*\}\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^\\begin\s*\{\s*equation\s*\}\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*\\end\s*\{\s*equation\s*\}\s*$", "", s, flags=re.IGNORECASE)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\s+", " ", s)
    s = "".join(c for c in s if c != "\x00" and (ord(c) >= 32 or c in "\n\t"))
    return s.strip()


def looks_like_single_formula(text: str) -> bool:
    """
    粗略判断一个字符串是否“更像单个公式而不是整道题”：
    - 没有中文字符
    - 没有换行
    - 不包含明显选项标记（A. / B. / （A）等）
    仅用于当 operation=solution 时，发现 formula 仍然只是一个式子时回退为“整题=用户原始提问”。
    """
    if not text or not isinstance(text, str):
        return False
    s = text.strip()
    if len(s) < 3:
        return False
    # 有中文说明更像题目描述
    if re.search(r"[\u4e00-\u9fff]", s):
        return False
    # 有多行一般也是题面
    if "\n" in s or "\r" in s:
        return False
    # 典型选项标记
    if re.search(r"\b[ABCD][\.\)]", s):
        return False
    if re.search(r"[（(][ABCD][)）]", s):
        return False
    return True


def _classify_intent(text: str) -> dict:
    """
    基于关键词的轻量级意图识别模块：
    - 不直接决定步骤，但给出 role / 页面 / 模式 的强提示，供大模型参考。
    """
    t = (text or "").strip()
    lower = t.lower()
    intent = {
        "role": "none",                # student | teacher | creator | developer | none
        "prefer_detect": False,        # 是否倾向智能识别页
        "prefer_detect_only": False,   # 是否更像“只识别不跳转”
        "save_to_formulas": False,     # 是否强调“识别并保存到我的算式”
        "prefer_calculate": False,     # 是否强调动态计算 / 去计算
        "prefer_examples": False,      # 是否强调教学案例 / 视频学习
        "prefer_devtools_latex": False,
        "prefer_devtools_manim": False,
        "prefer_solution_mode": False,      # 更像“整题解题演示”
        "prefer_visualization_mode": False, # 更像“可视化动画演示”；未明确时默认用 normal 通用推演
        "examples_filter": None,            # all|favorites|watch_later|courseware
        "prefer_settings": False,           # 是否要打开/修改设置
    }
    if not t:
        return intent

    # 角色识别（与首页「按角色快速开始」保持一致语义）
    if "学生" in t:
        intent["role"] = "student"
    elif "老师" in t or "教师" in t:
        intent["role"] = "teacher"
    elif "创作者" in t or "up主" in t or ("视频" in t and ("b站" in t or "短视频" in t or "抖音" in t)):
        intent["role"] = "creator"
    elif "开发者" in t or "程序员" in t or "写代码" in t:
        intent["role"] = "developer"

    # 操作类关键词
    if "只识别" in t:
        intent["prefer_detect"] = True
        intent["prefer_detect_only"] = True
    if "识别并保存" in t or "识别后保存" in t or "保存到我的算式" in t:
        intent["prefer_detect"] = True
        intent["save_to_formulas"] = True
    if "识别" in t and not intent["prefer_detect_only"] and "保存" not in t and "去计算" not in t and "生成" not in t:
        intent["prefer_detect"] = True

    if "去计算" in t or "动态计算" in t or "计算页" in t or "计算页面" in t:
        intent["prefer_calculate"] = True

    # 仅当用户明确说要「画图/函数图像/可视化演示」等才倾向 visualization；「生成动画」「做成动画」默认用通用推演
    if any(kw in t for kw in ("画图", "画函数", "函数图像", "函数曲线", "图像演示", "可视化演示", "做成图像", "绘制图像")):
        intent["prefer_calculate"] = True
        intent["prefer_visualization_mode"] = True
    elif "生成动画" in t or "做成动画" in t or "生成" in t:
        intent["prefer_calculate"] = True

    # 明确提到“整题/题解”的强信号
    if "完整解题演示" in t or "完整解题" in t or "做一遍题解" in t or "帮我把这道题解出来" in t or "详细解答这道题" in t:
        intent["prefer_calculate"] = True
        intent["prefer_solution_mode"] = True

    # 题目型关键词：选择题/填空题/证明/求极限/微分方程/泰勒展开/幂级数等
    problem_keywords = [
        "这道题", "本题", "下列", "选择题", "填空题", "解答题",
        "已知", "若", "设", "其中", "求极限", "求导", "求积分", "求和",
        "证明", "说明", "求证", "判断", "求解", "解出",
        "微分方程", "方程组", "收敛域", "敛散性",
        "泰勒", "Taylor", "幂级数", "级数展开", "展开式", "展开成", "展开为",
    ]
    if any(kw in t for kw in problem_keywords):
        intent["prefer_calculate"] = True
        intent["prefer_solution_mode"] = True

    # 长文本 + 题目风格词汇时，也倾向整题模式
    if len(t) >= 60 and any(kw in t for kw in ("已知", "若", "其中", "设", "如下", "如图")):
        intent["prefer_calculate"] = True
        intent["prefer_solution_mode"] = True

    if "latex" in lower or "tex" in lower or "latex 编辑器" in t:
        intent["prefer_devtools_latex"] = True
    if "manim" in lower or "云端渲染" in t or "工作台" in t or "开发者工具" in t:
        intent["prefer_devtools_manim"] = True

    if "教学案例" in t or "案例" in t or "视频课" in t or "课程视频" in t:
        intent["prefer_examples"] = True
    if "收藏" in t or "我的收藏" in t:
        intent["prefer_examples"] = True
        intent["examples_filter"] = "favorites"
    if "稍后看" in t:
        intent["prefer_examples"] = True
        intent["examples_filter"] = "watch_later"
    if "课件" in t or "我的课件" in t or "课件包" in t:
        intent["prefer_examples"] = True
        intent["examples_filter"] = "courseware"

    if "设置" in t or "偏好" in t or "配置" in t or "改成" in t or "修改" in t:
        intent["prefer_settings"] = True

    # 角色 → 默认偏好
    role = intent["role"]
    if role == "student":
        intent["prefer_examples"] = True or intent["prefer_examples"]
        intent["prefer_calculate"] = True or intent["prefer_calculate"]
    elif role == "teacher":
        intent["prefer_examples"] = True or intent["prefer_examples"]
        intent["prefer_devtools_manim"] = True or intent["prefer_devtools_manim"]
    elif role == "creator":
        intent["prefer_devtools_manim"] = True or intent["prefer_devtools_manim"]
    elif role == "developer":
        intent["prefer_devtools_manim"] = True or intent["prefer_devtools_manim"]

    return intent


# 知识图谱节点 -> 动作映射（供 LLM 意图识别，与 site-graph.js NODES 保持一致）
KNOWLEDGE_GRAPH_HINT = (
    "【知识图谱节点-动作映射】"
    " (1) 教学案例筛选：收藏→section=examples, examples_filter=favorites；稍后看→examples_filter=watch_later；我的课件→examples_filter=courseware；全部→examples_filter=all。"
    " (2) 系统设置：用户说「打开设置」「修改xx设置」时，section=settings。可设置 settings_section 定位到子项：appearance|profile|agent|detect|shortcuts|calc|devtools|examples。"
    " (3) 智能体可帮用户修改设置：在 step 中加 setting_key、setting_value。支持：theme(light|dark)、agent_enter_send(true|false)、detect_default_input(draw|upload)、calc_default_mode(normal|formular|visualization|solution)、devtools_default_tab(latex|manim|rainbow)、hero_effect_mode(gradient|interaction)、canvas_lock_mobile(true|false)、danmaku_enabled(true|false)、danmaku_opacity(0-100)。"
)

# 网站对外可调用的工具列表，供智能体或外部 Agent（如 function calling）按名称调用
AGENT_TOOLS = [
    {"name": "solve_steps", "description": "分步解题，自动选择 SymPy、AI 推导及交互图形，流式返回每一步。", "method": "POST", "path": "/api/solve/stream", "body": {"problem": "完整题目", "context": "可选图像描述"}},
    {"name": "render_solution", "description": "将结构化解答渲染为带章节的 Manim 动画。", "method": "POST", "path": "/api/solve/render", "body": {"solution": "solve_steps 返回的 solution 对象"}},
    {
        "name": "detect",
        "description": "上传图片识别公式，返回 LaTeX。需先登录，请求时带图片。",
        "method": "POST",
        "path": "/api/detect",
        "body": {"file": "multipart 图片"},
    },
    {
        "name": "animate_stream",
        "description": "将 LaTeX 算式转为 Manim 动画：输入主公式(matrixA)、可选第二公式(matrixB)、演示模式(operation)，流式返回解题步骤与视频 URL。用于解题、公式推演、可视化演示。",
        "method": "POST",
        "path": "/api/animate/stream",
        "body": {"matrixA": "LaTeX 主公式", "matrixB": "可选，第二公式", "operation": "normal|formular|visualization"},
    },
    {
        "name": "run_manim",
        "description": "执行用户提供的 Manim Python 代码，返回渲染后的视频 URL。",
        "method": "POST",
        "path": "/api/devtools/run_manim",
        "body": {"code": "完整 Manim 代码字符串"},
    },
    {
        "name": "formulas_list",
        "description": "获取当前用户的算式列表。",
        "method": "GET",
        "path": "/api/formulas/list",
        "query": {"username": "当前用户名"},
    },
    {
        "name": "formulas_save",
        "description": "保存一条算式到「我的算式」。",
        "method": "POST",
        "path": "/api/formulas/save",
        "body": {"username": "用户名", "latex": "LaTeX 字符串", "note": "备注"},
    },
]


@router.get("/tools")
async def agent_tools():
    """返回智能体可调用的网站工具列表，便于外部 Agent 或文档使用。"""
    return {"tools": AGENT_TOOLS}


@router.post("/execute")
def agent_execute(data: AgentRequest):
    """智能体：理解用户意图，返回要跳转的页面与预填/触发的动作。"""
    if not data.image_base64:
        teaching={
            '打开错题本':{'examples_filter':'wrongbook'},'错题本':{'examples_filter':'wrongbook'},
            '复习错题':{'examples_action':'review'},'开始复习':{'examples_action':'review'},
            '创建课包':{'examples_action':'create_pack'},'打开教案':{'examples_action':'lesson'},
            '编辑教案':{'examples_action':'lesson'},'打开备课工作台':{'examples_action':'lesson'},
            '打开我的课件':{'examples_filter':'courseware'},'我的课包':{'examples_filter':'courseware'},
            '打开播放器弹幕':{'examples_action':'danmaku'},'打开时间戳笔记':{'examples_action':'notes'},
        }
        action=teaching.get((data.prompt or '').strip())
        if action:
            return {'status':'success','steps':[{'section':'examples',**action,'reply':'打开教学工作台。'}]}
        direct={'打开我的算式':'my-formulas','打开教学案例':'examples','打开帮助':'help','打开 Manim 工作台':'devtools','打开 Manim 开发者工作台':'devtools'}
        section=direct.get((data.prompt or '').strip())
        if section:
            return {'status':'success','steps':[{'section':section,'devtool':'manim' if section=='devtools' else None,'reply':'正在打开对应工具。'}]}
    latex_from_image = None
    if data.image_base64:
        try:
            import base64
            from ..recognition import recognize_sync, RecognitionIssue
            if not api_key:
                return {'status':'error','message':'图片识别暂不可用，请先输入完整题面。','retryable':False}
            encoded = re.sub(r'^data:image/[^;]+;base64,', '', data.image_base64.strip())
            try: content = base64.b64decode(encoded, validate=True)
            except ValueError as error: raise RecognitionIssue('图片无法读取，请重新上传一道题的清晰图片。') from error
            recognized = recognize_sync(content, client)
            # Image interpretation never silently starts calculation. Preserve the
            # full statement for user review, without paying for a second planner.
            return {'status':'success','steps':[{'section':'detect','trigger':'none',
                'formula':recognized['problem_text'], 'recognition':recognized,
                'reply':'请先核对识别题面，再送入计算。'}]}
        except Exception as error:
            from ..recognition import RecognitionIssue
            logger.warning('Agent image recognition failed (%s)', type(error).__name__)
            return {'status':'error','message':str(error) if isinstance(error,RecognitionIssue) else llm_error_message(error),'retryable':False}

    context_prefix = ""
    if data.last_user_message or data.last_assistant_message:
        context_prefix = (
            "上一轮对话："
            + (f"用户说：{data.last_user_message}；" if data.last_user_message else "")
            + (f"助手回复：{data.last_assistant_message}。" if data.last_assistant_message else "")
            + "\n\n"
        )

    # Supported local math tasks can immediately dispatch real tools without a model round trip.
    if not data.image_base64:
        try:
            from ..math_runtime import run_math_sync
            local = run_math_sync('local',{'problem':data.prompt or ''})
        except (ValueError, SyntaxError, TypeError, OverflowError,TimeoutError):
            local = None
        if local is not None:
            return {"status": "success", "prompt": data.prompt, "steps": [{"section": "calculate", "operation": "solution", "trigger": "generate", "formula": data.prompt, "reply": "将调用符号计算、交互图形和 Manim，逐步展示这道题的解答。"}]}
    if not api_key:
        return {"status": "error", "message": "复杂题目与自然语言调度需要在服务端配置 ALIYUN_KEY。可先输入：解方程 x^2-5*x+6=0。", "retryable":False}

    intent_hint = _classify_intent(data.prompt or "")
    intent_hint_json = json.dumps(intent_hint, ensure_ascii=False)
    prompt_for_llm = (
        "本网站包含以下功能页面：detect=智能识别（手写/上传识别公式）、calculate=动态计算（输入公式生成动画）、"
        "devtools=开发者工具（含 LaTeX 可视化编辑器、LaTeX 源码、Manim 工作台/云端渲染、Rainbow 拓展库）、my-formulas=我的算式、examples=教学案例、help=帮助。"
        "网站核心能力：将 LaTeX 算式转为 Manim 动画演示（公式推演、可视化等），可被智能体调用来解题并演示。\n\n"
        + f"【服务器意图预判】{intent_hint_json}。除非用户在当前轮明确提出相反要求，否则请优先依据该预判选择 section/operation/devtool/steps。\n\n"
        + f"{KNOWLEDGE_GRAPH_HINT}\n\n"
        + context_prefix
        + "当前用户说：" + data.prompt + "\n\n"
        + ("用户上传了图片，完整题面与图形条件为：" + latex_from_image + "。计算步骤的 formula 必须保留完整题面和所有条件，不添加未验证的答案。" if latex_from_image else "用户未上传图片，若需公式请从描述或题目中提取 LaTeX。")
        + '\n\n【解析要求】当用户给出题目、算式或图片时，请先将题目解析为可编辑的 LaTeX 或可渲染的 Manim 算式（可拆解为步骤），在 formula、fill_latex 或 fill_manim_code 中体现该解析结果；若有拆解说明可放在 reply 中简要写出。'
        '\n\n【智能区分整题与单公式】必须根据用户给的是「整道题」还是「单个公式」决定 operation 和 formula 的内容：'
        ' (整题) 选择题、多选项、求完整解答、问「哪个是无穷小量/等价无穷小」、题目截图等：operation=solution，formula=整题的结构化文字（题目描述+各选项 LaTeX+极限或结论+正确答案），输入到计算页的也必须是这段整题内容，不要只填一个公式。'
        ' (单公式) 用户只给一个式子或说「把这个公式做成动画/推演」：**默认 operation=normal（通用推演）**；仅当用户明确说「画图」「函数图像」「可视化演示」「做成图像」等时才用 operation=visualization；formular 用于纯公式推演。formula=该式的 LaTeX。'
        '\n\n【重要】根据用户意图决定行为：'
        ' (1) 若用户只是提问、打招呼、闲聊，则 section="chat", 输出 reply 为友好回复。'
        ' (1b) 若用户说「打开设置」「修改xx设置」「把xx改成xx」等，section=settings；可选 settings_section 定位（appearance/profile/agent/detect/shortcuts/calc/devtools/examples）；若要直接改某项，加 setting_key 与 setting_value，如 setting_key="theme" setting_value="dark" 表示切换到深色模式。'
        ' (2) 若用户说"在 LaTeX 编辑器填入 xxx""打开 LaTeX 并填入质能方程"等，则 section=devtools, devtool=latex, fill_latex 为 LaTeX。'
        '     **常见数学概念转换**：质能方程→E=mc^2；勾股定理→a^2+b^2=c^2；欧拉公式→e^{i\\pi}+1=0 等，转为标准内联 LaTeX。'
        ' (3) 若用户说"打开云端渲染工作台/开发者工具并写一段 Manim 示例代码填入""打开 Manim 工作台并填入代码"等，则 section=devtools, devtool=manim, fill_manim_code 为一段完整的 Manim Python 代码（from manim import * 开头，含 class GenScene(Scene) 的 construct）。'
        ' (3b) Manim 工作台工具栏动作：用户说「运行/渲染 Manim」「运行代码」「执行」→ devtool_action=run；「关键帧预览」「预览关键帧」→ devtool_action=keyframe；「导入脚本」「打开导入面板」→ devtool_action=import；「保存脚本」「保存到脚本库」→ devtool_action=save；「生成视频文案」「总结脚本」→ devtool_action=summary；「打开 AI 编辑」「用 AI 改代码」→ devtool_action=ai_edit。这些与 fill_manim_code 可同时存在（先填入再执行动作）。'
        ' (4) 若用户说"只识别""识别这张图（不跳转）"，则 section=detect, trigger=recognize。'
        ' (5) 若用户说"识别公式并保存到我的算式""识别并保存"等，则先识别再保存：输出 steps 数组，第一步 section=detect, trigger=recognize；第二步 section=my-formulas 且 save_to_formulas=true（表示把上一步识别结果保存到我的算式）。'
        ' (6) 其他多步需求（如先打开工作台再填入代码、先识别再去计算等）：用 steps 数组按顺序列出每一步。单步则只输出一个 JSON 对象（不含 steps）。'
        ' (6b) 教学案例子功能：用户说「收藏」「我的收藏」「稍后看」「我的课件」「全部案例」时，section=examples，并设置 examples_filter：收藏→favorites；稍后看→watch_later；我的课件→courseware；全部→all。'
        ' 错题本用 section=examples, examples_filter=wrongbook；开始复习用 section=examples, examples_action=review。备课、填写教案用 section=examples, examples_action=lesson；创建课包用 examples_action=create_pack；播放器弹幕用 examples_action=danmaku；时间戳笔记用 examples_action=notes。教案编辑器由用户填写并保存，不要声称已经生成或保存了教案。'
        ' (7) **解题类（调用网站工具）**：当用户给出数学题（选择题、判断题、求极限、问「哪个是无穷小量/等价无穷小」等）或上传题目截图时，请：'
        ' ① 先判断是**整题**还是**单公式**：整题则 operation=solution 且 formula 为整题结构化文字；单公式则 **默认 operation=normal**，仅当用户明确说「画图」「函数图像」「可视化」时才用 visualization，formula 为该公式 LaTeX。'
        ' ② 从题目/图片中提取各选项或待比较的式子，转为标准 LaTeX（如 A: \\frac{x+\\cos x}{x}, B: \\frac{\\sin x}{x}, C: \\frac{\\sin x}{\\sqrt{x}}, D: \\frac{1}{2^x-1}）。'
        ' ③ 在 reply 中简要写出结论；reply 中的数学公式请用 $ 公式 $ 表示行内、$$ 公式 $$ 表示独立公式，便于前端渲染。'
        ' ④ **整题（完整解题演示）**：section=calculate, operation=solution, formula=**整题**结构化文字（题目描述+选项 A/B/C/D 的 LaTeX+各选项极限或结论+正确答案如 Answer: C），trigger=generate。**输入到计算页的必须是整题内容，不能只填一个公式。**'
        ' ⑤ **单公式推演**：section=calculate, formula=该式的 LaTeX, **operation=normal**（通用推演，默认）；用户明确说「画图」「函数图像」时用 operation=visualization；纯推演步骤可用 formular。trigger=generate。'
        ' ⑥ 若需对多个选项分别做单公式演示，可输出 steps：每步 section=calculate, formula=该选项 LaTeX, operation=normal（或 visualization 仅当意图明确画图）, trigger=generate。'
        '\n\n【角色化使用：按角色快速开始】当用户说“我是学生/老师/创作者/开发者”并提出学习或创作目标时，请优先返回多步 steps，并实际调用页面：'
        ' (学生) 至少两步：第一步 section="examples"（推荐 1～2 个适合的教学案例，可在 reply 里说明推荐理由）；第二步 section="calculate"，**选 operation=normal**（通用推演），根据用户要看的知识点填入代表性公式 formula 并 trigger="generate"。如用户还提到“时间戳笔记”“错题本”，请在 reply 中用 1～3 条建议说明如何在教学案例页添加时间戳笔记、如何把题目转成练习题并再次唤起智能体。'
        ' (老师) 至少三步：可以先 section="detect" 或 "calculate" 用于从板书/LaTeX 中得到公式，然后 section="devtools"（devtool="manim" 或 "latex"）填入示例代码或整题 LaTeX，最后 section="examples" 引导如何保存/整理为课件或课包；每步的说明写在 reply 中简要概括。'
        ' (创作者) 优先 section="devtools" devtool="manim" 并在 fill_manim_code 中给出一段可直接运行的 Manim 脚本，trigger="none"；然后在 reply 中给出 15～30 秒视频的大纲和分镜建议。'
        ' (开发者) 优先打开开发者工具：第一步 section="devtools" devtool="rainbow" 或 "manim"，帮助用户载入或编写示例脚本；如用户提到“组件卡片”“可复用模块”，在 reply 中说明推荐的脚本结构与如何整理为组件。'
        '\n\n动态计算页演示模式：**默认 operation=normal**（通用推演）；solution=完整解题过程且 formula 为整题文字；仅当用户明确说「画图」「函数图像」「可视化演示」时才用 visualization；formular 为纯公式推演。'
        '\n\nformula：当 operation=solution 时为整题结构化文字（可含多行、多选项）；当 operation 为 formular/visualization/normal 时为标准内联 LaTeX，不要 \\[ \\]、$$、\\begin{equation}。fill_latex 仅用于 LaTeX 编辑器，标准内联 LaTeX。'
        '\n\n请只输出一个 JSON。单步格式：{"section":"...", "settings_section":"appearance|profile|agent|detect|shortcuts|calc|devtools|examples"(section=settings 时可选), "setting_key":"", "setting_value":"", "devtool":"...", "devtool_action":"...", "examples_filter":"...", "formula":"", "fill_latex":"", "fill_manim_code":"", "operation":"...", "trigger":"...", "reply":"回复"}。'
        '多步格式：{"steps":[ 上述单步对象1, 单步对象2, ... ]}。可选字段 save_to_formulas: true 表示该步后把当前识别结果保存到我的算式。'
        " trigger：立刻生成动画填 generate；仅识别填 recognize；只跳转填 none。"
    )
    try:
        parsed = generate_plan(prompt_for_llm)

        user_prompt = data.prompt or ""

        def normalize_step(obj: dict) -> dict:
            section = str(obj.get("section") or "chat").strip()
            if section not in ("detect", "calculate", "devtools", "my-formulas", "examples", "help", "chat", "settings"):
                section = "chat"
            reply = str(obj.get("reply") or "").strip()
            devtool = obj.get("devtool") or None
            formula = str(obj.get("formula") or (latex_from_image or "")).strip()
            if not formula and latex_from_image:
                formula = latex_from_image
            operation = str(obj.get("operation") or "normal")
            if operation not in ("formular", "visualization", "normal", "solution"):
                operation = "normal"
            # 服务器预判：若明显是整道题，更倾向使用 solution 模式
            if section == "calculate" and intent_hint.get("prefer_solution_mode"):
                operation = "solution"
            if section == "calculate" and latex_from_image:
                operation = "solution"
                formula = (data.prompt + "\n图片题面：\n" + latex_from_image).strip()
            # 整题（solution）时 formula 为结构化题目文字，不做 LaTeX 清洗；单公式时再做清洗供 MathLive
            if operation != "solution":
                formula = sanitize_latex_for_mathlive(formula)
            else:
                # 若 operation=solution 但 formula 看上去仍只是单个公式，而用户原始提问更长，
                # 则优先使用用户原始提问作为“整题”内容传给动态计算页。
                if user_prompt and looks_like_single_formula(formula):
                    up = user_prompt.strip()
                    if len(up) > len(formula.strip()) + 8:
                        formula = up
            fill_latex = str(obj.get("fill_latex") or "").strip()
            fill_latex = sanitize_latex_for_mathlive(fill_latex) if fill_latex else ""
            fill_manim_code = str(obj.get("fill_manim_code") or "").strip()
            save_to_formulas = obj.get("save_to_formulas") is True
            trigger = str(obj.get("trigger") or "none")
            if trigger not in ("generate", "recognize", "none"):
                trigger = "none"
            devtool_action = str(obj.get("devtool_action") or obj.get("action") or "").strip().lower()
            if devtool_action not in ("run", "keyframe", "import", "save", "summary", "ai_edit"):
                devtool_action = None
            examples_filter = str(obj.get("examples_filter") or "").strip()
            if examples_filter not in ("all", "favorites", "watch_later", "courseware", "wrongbook"):
                examples_filter = None
            examples_action = obj.get('examples_action')
            if examples_action not in ('create_pack','lesson','danmaku','notes','review'):
                examples_action = None
            settings_section = str(obj.get("settings_section") or "").strip()
            if settings_section not in ("appearance", "profile", "agent", "detect", "shortcuts", "calc", "devtools", "examples"):
                settings_section = None
            setting_key = str(obj.get("setting_key") or "").strip() or None
            setting_value = obj.get("setting_value")
            return {
                "section": section,
                "reply": reply,
                "devtool": devtool,
                "devtool_action": devtool_action,
                "examples_filter": examples_filter,
                "examples_action": examples_action,
                "settings_section": settings_section,
                "setting_key": setting_key,
                "setting_value": setting_value,
                "formula": formula,
                "fill_latex": fill_latex,
                "fill_manim_code": fill_manim_code,
                "save_to_formulas": save_to_formulas,
                "operation": operation,
                "trigger": trigger,
            }

        if isinstance(parsed.get("steps"), list) and len(parsed["steps"]) > 0:
            steps_arr = [normalize_step(s) if isinstance(s, dict) else normalize_step({}) for s in parsed["steps"][:12]]
        else:
            steps_arr = [normalize_step(parsed)]

        if not data.image_base64 and any(s.get("trigger") == "recognize" for s in steps_arr):
            return JSONResponse(
                status_code=200,
                content={"status": "error", "message": "进行识别需要您先上传或粘贴一张公式图片，请上传后再试。", "retryable":False},
            )

        return {
            "status": "success",
            "steps": steps_arr,
            "message": "已生成工具执行计划" if len(steps_arr) > 1 else ("已准备对应步骤" if steps_arr and steps_arr[0].get("section") != "chat" else ""),
        }
    except Exception as e:
        logger.error(f"Agent LLM parse: {e}")
        return JSONResponse(status_code=200, content={"status": "error", "message": llm_error_message(e), "retryable":recoverable_error(e)})
