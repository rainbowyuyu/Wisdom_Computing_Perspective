"""First-party worked examples. Exact matches only; related methods are not answers."""
import re

from app.solution_models import Solution, SolutionStep, Visual
from .solution_engine import resolve_visual_functions


def example(ident, level, topic, title, problem, method, keywords, summary, steps, visual=None):
    return dict(id=ident, level=level, topic=topic, title=title, problem=problem, method=method,
                keywords=keywords.split('|'), summary=summary, steps=steps, visual=visual)


# Original, self-contained teaching examples; no third-party answer scraping or attribution.
EXAMPLES = [
    example('hs-quadratic','高中','方程与不等式','因式分解与验根',
        '解方程：x^2-5x+6=0。', '找乘积与和，再分解因式，最后代回原式。','二次|方程|因式',
        r'方程的解为 $x=2$ 或 $x=3$。', [
            ('寻找因子','两个数的积为 $6$、和为 $-5$，取 $-2,-3$。',r'(-2)(-3)=6,\quad -2-3=-5'),
            ('分解因式','拆开一次项并分组提取公因式。',r'x^2-2x-3x+6=(x-2)(x-3)=0'),
            ('分别求根','乘积为零，至少一个因式为零。',r'x-2=0\quad\text{或}\quad x-3=0'),
            ('代回检查','两个数都使原式等于零，没有新增定义域限制。',r'2^2-5\cdot2+6=0,\quad3^2-5\cdot3+6=0')],
        {'kind':'plot','functions':[{'expression':'x^2-5*x+6','domain':[0,5]}]}),
    example('hs-absolute','高中','方程与不等式','绝对值不等式',
        '解不等式：|2x-1|<3。','先去绝对值，再对三部分同时作等价变形。','绝对值|不等式',
        r'解集为 $(-1,2)$。',[
            ('化为连不等式','绝对值小于正数表示到零的距离小于该数。',r'-3<2x-1<3'),
            ('同时加一','三部分同时加一，不等号方向不变。',r'-2<2x<4'),
            ('除以正数并取端点','除以 $2$；原式为严格不等式，两端均不取。',r'-1<x<2')],
        {'kind':'number_line','rows':[{'label':'解集','intervals':[{'lower':-1,'upper':2}]}]}),
    example('hs-rational','高中','方程与不等式','分式方程与增根',
        '解方程：(x+1)/(x-1)=2。','先记录分母非零，再去分母、求解和验根。','分式|分母|方程',
        r'原方程的解为 $x=3$。',[
            ('确定定义域','分母不能为零，后续必须排除禁值。',r'x\ne1'),
            ('去分母','在定义域内两边乘以相同的非零数。',r'x+1=2(x-1)'),
            ('移项求解','展开右侧并合并同类项。',r'x+1=2x-2\Longrightarrow x=3'),
            ('验根','候选值不等于禁值，且代回两边相等。',r'\frac{3+1}{3-1}=2')]),
    example('hs-log','高中','方程与不等式','对数方程与定义域',
        '解方程：log_2(x-1)+log_2(x-3)=3。','先取真数的公共定义域，合并对数后筛选根。','对数|log|定义域',
        r'满足定义域的解为 $x=5$。',[
            ('确定真数范围','两个真数均为正。',r'x-1>0,\quad x-3>0\Longrightarrow x>3'),
            ('合并对数','同底对数相加等于乘积的对数。',r'\log_2((x-1)(x-3))=3'),
            ('转成二次方程','使用对数与指数的对应关系。',r'(x-1)(x-3)=8\Longrightarrow(x-5)(x+1)=0'),
            ('排除不合定义域的根','候选根为 $5,-1$，仅 $5>3$。',r'\log_2 4+\log_2 2=2+1=3')]),
    example('hs-trig','高中','三角与向量','区间内的三角方程',
        '求sin(x)=1/2在[0,2π]内的所有解。','先找参考角，再用象限与区间筛选。','三角|sin|角',
        r'$x=\frac{\pi}{6}$ 或 $x=\frac{5\pi}{6}$。',[
            ('求参考角','利用常用特殊角的正弦值。',r'\sin\frac{\pi}{6}=\frac12'),
            ('确定象限','正弦为正，在给定区间的第一、第二象限取解。',r'x=\frac\pi6\quad\text{或}\quad x=\pi-\frac\pi6'),
            ('检查区间与端点','两解都在区间内，端点正弦均为零。',r'x\in\left\{\frac\pi6,\frac{5\pi}6\right\}')]),
    example('hs-vector','高中','三角与向量','向量夹角',
        '已知向量a=(1,2)，b=(2,1)，求夹角的余弦值。','先算点积和模，再代入夹角公式。','向量|夹角|点积',
        r'夹角的余弦值为 $\frac45$。',[
            ('计算点积','对应分量相乘后相加。',r'\mathbf a\cdot\mathbf b=1\cdot2+2\cdot1=4'),
            ('计算向量模','两个向量都非零，可使用夹角公式。',r'|\mathbf a|=|\mathbf b|=\sqrt5'),
            ('代入公式','结果位于 $[-1,1]$，符合余弦的范围。',r'\cos\theta=\frac{\mathbf a\cdot\mathbf b}{|\mathbf a||\mathbf b|}=\frac45')],
        {'kind':'geometry','points':[[0,0],[1,2],[2,1]],'labels':['O','a','b'],'segments':[[0,1],[0,2]]}),
    example('hs-arithmetic','高中','数列','等差数列前项和',
        '等差数列首项为3，公差为2，求前10项和。','由首项、公差求末项，再用首末项配对求和。','等差|数列|前|项和',
        r'前十项和为 $S_{10}=120$。',[
            ('求第十项','从第一项到第十项共增加九个公差。',r'a_{10}=3+(10-1)\cdot2=21'),
            ('首尾配对','首项与末项、第二项与倒数第二项之和相同。',r'a_1+a_{10}=a_2+a_9=24'),
            ('计算总和','十项共五对。',r'S_{10}=\frac{10(3+21)}2=120')]),
    example('hs-geometric','高中','数列','等比数列求和',
        '等比数列首项为2，公比为3，求前5项和。','错位相减推导求和式，检查公比是否等于一。','等比|数列|公比',
        r'$S_5=242$。',[
            ('展开有限和','共有五项，最后一项的公比指数为四。',r'S_5=2+2\cdot3+2\cdot3^2+2\cdot3^3+2\cdot3^4'),
            ('乘公比并相减','相同的中间项抵消。',r'3S_5-S_5=2\cdot3^5-2'),
            ('求和','本题公比不为一，可以除以公比减一。',r'S_5=\frac{2(3^5-1)}{3-1}=242')]),
    example('hs-circle','高中','解析几何','直线与圆的位置关系',
        '直线x+y+m=0与圆(x+1)^2+(y-1)^2=9没有公共点，求m的范围。','圆心到直线距离大于半径，再解绝对值不等式。','圆|直线|公共点|距离',
        r'$m<-3\sqrt2$ 或 $m>3\sqrt2$，等号对应相切，应排除。',[
            ('读出圆心与半径','标准方程给出圆心 $(-1,1)$、半径 $3$。',r'C=(-1,1),\quad r=3'),
            ('计算距离','把圆心代入直线距离公式，不得任意赋值参数。',r'd=\frac{|-1+1+m|}{\sqrt{1^2+1^2}}=\frac{|m|}{\sqrt2}'),
            ('转化位置关系','没有公共点表示距离严格大于半径。',r'\frac{|m|}{\sqrt2}>3\Longrightarrow |m|>3\sqrt2'),
            ('分类求解','绝对值大于正数，解位于两个外侧区间。',r'm<-3\sqrt2\quad\text{或}\quad m>3\sqrt2')],
        {'kind':'geometry','circles':[{'center':[-1,1],'radius':3,'label':'C'}]}),
    example('hs-probability','高中','概率统计','无放回抽球',
        '袋中有3个红球和2个白球，不放回地随机抽取2个球，求恰好抽到1个红球的概率。','按无序等可能组合计数，避免重复计算顺序。','抽|球|概率|放回|组合',
        r'所求概率为 $\frac35$。',[
            ('明确样本空间','把每个球视为不同个体，随机取两个球，组合等可能。',r'|\Omega|=\binom52=10'),
            ('数出有利情况','恰好一个红球意味着还需要一个白球。',r'|A|=\binom31\binom21=6'),
            ('计算概率','有利组合数除以全部组合数，结果在零与一之间。',r'P(A)=\frac6{10}=\frac35')]),
    example('uni-limit','大学','微积分','有理式极限',
        '求极限：lim_(x→1)(x^2-1)/(x-1)。','先判断零比零型，再因式分解约去局部非零因子。','极限|lim|约分',
        r'极限为 $2$。',[
            ('判断直接代入的形式','分子、分母同时趋于零，不能直接做除法。',r'x^2-1\to0,\quad x-1\to0'),
            ('因式分解','极限只关心去心邻域，可在 $x\ne1$ 时约分。',r'\frac{x^2-1}{x-1}=\frac{(x-1)(x+1)}{x-1}=x+1\quad(x\ne1)'),
            ('利用连续性','约分后的函数在目标点连续。',r'\lim_{x\to1}(x+1)=2')]),
    example('uni-derivative','大学','微积分','乘积与链式求导',
        '求函数f(x)=x^2 sin(x)的导数。','先识别乘积结构，分别求导后保留两个乘积项。','导数|求导|sin|乘积',
        r'$f\prime(x)=2x\sin x+x^2\cos x$。',[
            ('拆成两个函数','分别记幂函数与三角函数。',r'u=x^2,\quad v=\sin x'),
            ('分别求导','幂函数使用幂法则，正弦的导数为余弦。',r'u\prime=2x,\quad v\prime=\cos x'),
            ('应用乘积法则','不能把两个导数直接相乘。',r'f\prime=u\prime v+uv\prime=2x\sin x+x^2\cos x')],
        {'kind':'plot','functions':[{'expression':'x^2*sin(x)','domain':[-3,3]}]}),
    example('uni-integral','大学','微积分','分部积分',
        '求不定积分：∫x e^x dx。','选择求导后简化的多项式作为u，用分部积分降次。','积分|分部|e^x',
        r'$\int xe^x\,dx=(x-1)e^x+C$。',[
            ('选择分部变量','多项式求导后次数降低，指数函数容易积分。',r'u=x,\quad dv=e^x\,dx,\quad du=dx,\quad v=e^x'),
            ('应用分部积分','把原积分换成更简单的指数积分。',r'\int xe^x\,dx=xe^x-\int e^x\,dx'),
            ('补上积分常数','不定积分表示一族原函数。',r'\int xe^x\,dx=(x-1)e^x+C'),
            ('反向验算','对结果求导应回到被积函数。',r'\frac{d}{dx}[(x-1)e^x]=e^x+(x-1)e^x=xe^x')]),
    example('uni-improper','大学','微积分','反常积分的收敛性',
        '计算反常积分：∫_1^∞ 1/x^2 dx。','先把无穷上限换成有限变量，再对积分结果取极限。','反常|无穷|积分|收敛',
        r'反常积分收敛，值为 $1$。',[
            ('按定义截断','必须先确认极限存在，不能直接把无穷当数字。',r'\int_1^\infty\frac{dx}{x^2}=\lim_{b\to\infty}\int_1^b x^{-2}\,dx'),
            ('计算有限区间积分','求原函数并代入上下限。',r'\int_1^b x^{-2}\,dx=\left[-\frac1x\right]_1^b=1-\frac1b'),
            ('取极限并判断收敛','极限是有限实数。',r'\lim_{b\to\infty}\left(1-\frac1b\right)=1')]),
    example('uni-system','大学','线性代数','消元法解方程组',
        '用消元法解方程组：x+y=3，2x-y=0。','消去一个未知数，回代另一个方程，最后检查全部方程。','方程组|消元|线性',
        r'$x=1,\ y=2$。',[
            ('对齐未知数','第二个方程与第一个方程相加，可以消去 $y$。',r'\begin{cases}x+y=3\\2x-y=0\end{cases}'),
            ('消元','对方程实施等价行变换。',r'(x+y)+(2x-y)=3+0\Longrightarrow x=1'),
            ('回代并检查','用第一式求 $y$，再代入第二式确认。',r'y=3-1=2,\quad2\cdot1-2=0')]),
    example('uni-eigen','大学','线性代数','二阶矩阵特征值',
        '求矩阵A=[[2,1],[1,2]]的特征值。','特征多项式等于零；用迹与行列式复核根的和与积。','矩阵|特征值|行列式',
        r'特征值为 $1,3$。',[
            ('构造特征方程','非零特征向量存在，要求矩阵奇异。',r'\det(A-\lambda I)=\begin{vmatrix}2-\lambda&1\\1&2-\lambda\end{vmatrix}=0'),
            ('展开行列式','二阶行列式为主对角乘积减副对角乘积。',r'(2-\lambda)^2-1=\lambda^2-4\lambda+3=0'),
            ('分解并求根','解出特征多项式的全部根。',r'(\lambda-1)(\lambda-3)=0\Longrightarrow\lambda=1,3'),
            ('迹与行列式复核','两个特征值的和等于迹，积等于行列式。',r'1+3=\operatorname{tr}A=4,\quad1\cdot3=\det A=3')]),
    example('uni-ode','大学','微分方程','一阶初值问题',
        "解初值问题：y'=2y，y(0)=3。",'先解一阶线性方程，再用初值确定常数并代回。','微分方程|初值|y\'|分离变量',
        r'$y=3e^{2x}$，定义在整个实数轴。',[
            ('用积分因子变形','乘以非零积分因子，不需要除以未知函数，零解也不会遗漏。',r'e^{-2x}(y\prime-2y)=0\Longrightarrow(e^{-2x}y)\prime=0'),
            ('积分得到通解','导数为零意味着函数为常数。',r'e^{-2x}y=C\Longrightarrow y=Ce^{2x}'),
            ('代入初值','在自变量为零处满足给定函数值。',r'3=Ce^0\Longrightarrow C=3'),
            ('验证原方程','导数等于函数的两倍，且满足初值。',r'y=3e^{2x},\quad y\prime=6e^{2x}=2y,\quad y(0)=3')]),
    example('uni-series','大学','级数','几何级数的收敛区间',
        '求幂级数Σ_(n=0)^∞ x^n的收敛区间与和函数。','先用几何级数公式，再单独检查两端点。','级数|收敛|幂级数|和函数',
        r'收敛区间为 $(-1,1)$，和函数为 $\frac1{1-x}$。',[
            ('写有限部分和','先使用有限等比和公式。',r'S_N=\sum_{n=0}^N x^n=\frac{1-x^{N+1}}{1-x}\quad(x\ne1)'),
            ('求收敛范围内的极限','绝对值小于一时，公比的高次幂趋于零。',r'|x|<1\Longrightarrow\lim_{N\to\infty}S_N=\frac1{1-x}'),
            ('检查端点与外侧','端点及外侧的通项不趋于零，不满足级数收敛的必要条件。',r'x=\pm1\ \text{或}\ |x|>1\Longrightarrow x^n\not\to0')]),
    example('uni-partial','大学','多元微积分','偏导数与梯度',
        '求f(x,y)=x^2 y+y^2在点(1,2)处的梯度。','每次对一个变量求导，把其余变量当常数，最后代入点。','偏导|梯度|多元',
        r'$\nabla f(1,2)=(4,5)$。',[
            ('对第一个变量求偏导','把 $y$ 当作常数。',r'\frac{\partial f}{\partial x}=2xy'),
            ('对第二个变量求偏导','把 $x$ 当作常数。',r'\frac{\partial f}{\partial y}=x^2+2y'),
            ('代入指定点','梯度按变量顺序排列偏导数。',r'\nabla f(1,2)=(2\cdot1\cdot2,1^2+2\cdot2)=(4,5)')]),
    example('uni-bayes','大学','概率统计','全概率与贝叶斯公式',
        '甲厂供货占60%，次品率1%；乙厂供货占40%，次品率2%。随机取一件发现是次品，求它来自乙厂的概率。','先用全概率求证据概率，再计算条件概率；分清条件的方向。','贝叶斯|条件概率|次品|全概率',
        r'次品来自乙厂的概率为 $\frac47$。',[
            ('定义事件','用 $B$ 表示来自乙厂，$D$ 表示次品。',r'P(B)=0.4,\quad P(D\mid B)=0.02'),
            ('计算全概率','甲乙供货互斥且覆盖全部来源。',r'P(D)=0.6\cdot0.01+0.4\cdot0.02=0.014'),
            ('使用贝叶斯公式','先算来自乙厂且为次品的概率，再除以证据概率。',r'P(B\mid D)=\frac{0.4\cdot0.02}{0.014}=\frac47')]),
]


def catalog():
    return [{k: e[k] for k in ('id','level','topic','title','problem','method')} for e in EXAMPLES]


def normalize_problem(problem):
    # Whitespace only. Never remove signs, conditions, punctuation, or coefficients.
    return re.sub(r'\s+', '', problem)


def worked_solution(item):
    steps = [SolutionStep(title=t, explanation=e, formula=f, hint=item['method']) for t,e,f in item['steps']]
    if item['visual']:
        steps[-1].visual = Visual.model_validate(item['visual'])
    return resolve_visual_functions(Solution(title=item['title'], summary=item['summary'], steps=steps,
        source='curriculum', verification='本站整理的典型题解，仅在完整题面一致时直接使用；修改条件后将重新计算。'))


def exact_example(problem):
    target = normalize_problem(problem)
    item = next((e for e in EXAMPLES if normalize_problem(e['problem']) == target), None)
    return worked_solution(item) if item else None


def related_examples(problem):
    ranked = sorted(((sum(keyword.lower() in problem.lower() for keyword in e['keywords']), e) for e in EXAMPLES), key=lambda v: -v[0])
    return [e for score,e in ranked[:2] if score >= 2]


def teaching_context(problem):
    related = related_examples(problem)
    if not related:
        return ''
    return ('\n以下是本站典型题的方法参考，不是用户题目的答案。只借鉴适用方法；必须依据本题数字与条件重新推导，不能套用例题答案。\n'
        + '\n'.join(e['topic']+'：'+e['method'] for e in related))


def study_advice(problem, context='', failure=False):
    markers = re.findall(r'[（(][1-9一二三四五六][)）]', problem)
    if re.search(r'证明.{0,8}(黎曼猜想|哥德巴赫猜想)', problem):
        return {'blocking':True, 'message':'该问题涉及尚未解决的一般性猜想，不能给出已完成证明。',
                'suggestions':['解释题目定义和已知结论','研究一个明确的特殊情况，区分验证与证明']}
    if re.search(r'如图|见图|图中所示', problem) and not context and len(problem) < 120:
        return {'blocking':True, 'message':'题目依赖图形信息，当前只有文字，无法确认图中条件。',
                'suggestions':['使用图片识题，核对识别出的全部标注后再提交','补充点的位置、角度、长度以及所求量']}
    if failure or len(problem) > 1800 or len(markers) >= 3:
        return {'blocking':False, 'message':'这道题建议分阶段处理，保留全部已知条件，每次聚焦一个目标。',
                'suggestions':['先梳理已知条件、定义域和各小问之间的关系','只解第一问，说明每步依据并检查结论','利用前一问结论继续下一问，保留必要的分类讨论']}
    return None
