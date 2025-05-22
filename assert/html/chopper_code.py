import streamlit as st
import base64
import json
from PIL import Image
import io
import streamlit.components.v1 as components

# 显示图片并实现裁剪功能的HTML页面
html_code = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Image Cropper</title>
    <style>
        #container {
            position: relative;
        }
        #image {
            width: 100%;
            height: auto;
        }
        #cropper {
            position: absolute;
            border: 2px dashed #ff0000;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div id="container">
        <img id="image" src="" alt="image" />
        <div id="cropper"></div>
    </div>
    <script>
        let startX, startY, endX, endY;
        const image = document.getElementById("image");
        const cropper = document.getElementById("cropper");

        image.onload = () => {
            cropper.style.width = "0px";
            cropper.style.height = "0px";
        };

        image.addEventListener("mousedown", (e) => {
            startX = e.offsetX;
            startY = e.offsetY;
            cropper.style.left = `${startX}px`;
            cropper.style.top = `${startY}px`;
            cropper.style.width = "0px";
            cropper.style.height = "0px";
        });

        image.addEventListener("mousemove", (e) => {
            if (startX && startY) {
                endX = e.offsetX;
                endY = e.offsetY;
                cropper.style.width = `${endX - startX}px`;
                cropper.style.height = `${endY - startY}px`;
            }
        });

        image.addEventListener("mouseup", () => {
            if (startX && startY && endX && endY) {
                const cropArea = {
                    x: startX,
                    y: startY,
                    width: endX - startX,
                    height: endY - startY
                };
                // 传递裁剪区域数据给 Streamlit
                window.parent.postMessage({ type: 'crop', cropArea: cropArea }, "*");
                startX = startY = endX = endY = null;
            }
        });

        // 接收来自 Python 的图片数据
        function loadImageData(imageBase64) {
            image.src = imageBase64;
        }

        // 接收消息从 Streamlit 传递图片数据
        window.addEventListener('message', function (event) {
            if (event.data.type === 'load_image') {
                loadImageData(event.data.imageBase64);
            }
        });
    </script>
</body>
</html>
"""

# Streamlit 页面
st.set_page_config(page_title="裁剪功能", layout="wide")

# 上传图片
uploaded_file = st.file_uploader("上传图片", type=["jpg", "jpeg", "png"])
if uploaded_file:
    img = Image.open(uploaded_file)

    # 将图片转为 base64 编码传递给前端
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    # 在前端展示图片并允许裁剪
    components.html(html_code, height=500)

    # 发送图片数据到前端
    st.components.v1.html(
        f'<script>window.parent.postMessage({{type: "load_image", imageBase64: "data:image/png;base64,{img_base64}"}},"*")</script>',
        height=0
    )

    # 获取裁剪区域的坐标
    crop_area = None
    if st.session_state.get("crop_area"):
        crop_area = st.session_state.get("crop_area")

    if crop_area:
        # 裁剪图片
        left, top, width, height = crop_area["x"], crop_area["y"], crop_area["width"], crop_area["height"]
        cropped_img = img.crop((left, top, left + width, top + height))

        # 显示裁剪后的图片
        st.image(cropped_img, caption="裁剪后的图片", use_container_width=True)
