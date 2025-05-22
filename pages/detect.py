import streamlit as st
from openai import OpenAI
import base64
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import io
from default_streamlit_app_util import *
from streamlit_cropper import st_cropper

# Initialize
st.set_page_config(page_title="智算视界 · 算式检测", page_icon="assert/images/pure_logo.png", layout="wide")
mobile_or_computer_warning()


def get_openai_client():
    return OpenAI(
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key=st.secrets["aliyun_key"]
    )


client = get_openai_client()

st.markdown("## 📤 识别图片或手写输入")
input_method = st.radio("选择图像输入方式", ["上传图片", "绘制图片"], horizontal=True)
uploaded_file = None


cropped_img = None
canvas_result = None
if input_method == "上传图片":
    uploaded_file = st.file_uploader("请选择一张图片（jpg / jpeg / png）", type=["jpg", "jpeg", "png"],
                                     label_visibility="collapsed")
    if uploaded_file:
        # st.image(uploaded_file, caption="上传的图片", use_container_width=True)
        # Open the uploaded image
        img = Image.open(uploaded_file)

        # Using the cropper for interaction
        cropped_img = st_cropper(img, aspect_ratio=(2.0, 1.0), box_color="#555555")
elif input_method == "绘制图片":
        st.markdown("🖌️ 使用画板进行手绘")
        # 添加工具选择和画笔粗细调节
        tool = st.radio("🛠️ 选择工具", ["画笔", "橡皮"], horizontal=True)
        stroke_width = st.slider("✏️ 调整画笔粗细", 1, 30, 3)
        # 设置颜色：橡皮擦是白色，画笔是黑色
        stroke_color = "#FFFFFF" if tool == "橡皮" else "#000000"
        canvas_result = st_canvas(
            fill_color="rgba(255, 255, 255, 1)",
            stroke_width=stroke_width,
            stroke_color=stroke_color,
            background_color="#FFFFFF",
            width=600,
            height=300,
            drawing_mode="freedraw",
            key="canvas"
        )

col1, col2 = st.columns(2)

with col1:

        if cropped_img is not None:
            st.image(cropped_img, caption="输入的图片", use_container_width=True)
            # Save the cropped image for further use
            buffered = io.BytesIO()
            cropped_img.save(buffered, format="PNG")
            buffered.seek(0)
            uploaded_file = buffered


        if canvas_result is not None and canvas_result.image_data is not None:
            img = Image.fromarray(canvas_result.image_data.astype("uint8"))
            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            buffered.seek(0)
            st.image(buffered, caption="绘制的图片", use_container_width=True)
            uploaded_file = buffered

with col2:
    if st.button("🔍 识别公式"):
        if uploaded_file:
            with st.spinner("🧠 正在识别图像，请稍候..."):

                try:
                    # base64 编码
                    base64_image = base64.b64encode(uploaded_file.read()).decode("utf-8")

                    # 调用模型识别
                    completion = client.chat.completions.create(
                        model="qwen2.5-vl-72b-instruct",
                        extra_body={},
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "text",
                                 "text": "tell me the latex formula in the picture? only return the latex code and without ```latex``` or \\[\\]"},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                            ]
                        }]
                    )

                    latex_res = completion.choices[0].message.content.strip()
                    st.success("✅ 识别成功！")

                    latex_code = st.text_area("LaTeX 公式👇", value=latex_res, height=200)

                    st.markdown("### 渲染效果：")
                    try:
                        st.latex(latex_code)
                    except Exception as e:
                        st.error(f"渲染失败：{e}")

                except Exception as e:
                    st.error(f"识别过程中发生错误：{e}")
        else:
            st.warning("⚠️ 请先上传或绘制图片！")
