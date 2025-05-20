# rainbow_yu pages.detect 🐋✨

import streamlit as st
from openai import OpenAI
import base64
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import io

from default_streamlit_app_util import *

st.set_page_config(page_title="智算视界 · 可视化计算", page_icon="assert/images/pure_logo.png", layout="wide")
mobile_or_computer_warning()

col1, col2 = st.columns(2)
with col1:
    st.markdown("## 📤 识别图片或手写输入")

    # 选项切换：上传 or 手绘
    input_method = st.radio("选择图像输入方式", ["上传图片", "绘制图片"], horizontal=True)

    final_image = None

    if input_method == "上传图片":
        uploaded_file = st.file_uploader(
            "请选择一张图片（jpg / jpeg / png）", type=["jpg", "jpeg", "png"], label_visibility="collapsed"
        )
        if uploaded_file:
            st.image(uploaded_file, caption="上传的图片", use_container_width=True)

    elif input_method == "绘制图片":
        st.markdown("🖌️ 使用画板进行手绘")
        canvas_result = st_canvas(
            fill_color="rgba(255, 255, 255, 1)",  # 白底
            stroke_width=3,
            stroke_color="#000000",
            background_color="#FFFFFF",
            width=600,
            height=300,
            drawing_mode="freedraw",
            key="canvas",
        )
        if canvas_result.image_data is not None:
            img = Image.fromarray(canvas_result.image_data.astype("uint8"))
            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            buffered.seek(0)
            st.image(buffered, caption="绘制的图片", use_container_width=True)
            uploaded_file = buffered
with col2:
    # 添加识别按钮
    if st.button("🔍 识别公式"):
        if uploaded_file:
            # 转为 base64
            base64_image = base64.b64encode(uploaded_file.read()).decode("utf-8")

            # 创建 OpenAI 客户端
            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key="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",
            )

            # 发起图像识别请求
            completion = client.chat.completions.create(
                model="qwen/qwen2.5-vl-32b-instruct:free",
                extra_headers={
                    "HTTP-Referer": "https://wisdom-computing-perspective.streamlit.app/detect",  # Optional. Site URL for rankings on openrouter.ai.
                    "X-Title": "智算视界 · 可视化计算",  # Optional. Site title for rankings on openrouter.ai.
                },
                extra_body={},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "tell me the latex formula in the picture? only return the latex code and without ```latex``` or \[\]"},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                    }
                ]
            )

            # 显示识别结果
            latex_res = completion.choices[0].message.content.strip()
            st.success("✅ 识别结果：")
            latex_code = st.text_area(
                "LaTeX 公式👇",
                value=f"{latex_res}",
                height=200
            )

            # 渲染公式
            st.markdown("### 渲染效果：")
            try:
                st.latex(latex_code)
            except Exception as e:
                st.error(f"渲染失败: {e}")
        else:
            st.error("❌ 请先上传图片！")
