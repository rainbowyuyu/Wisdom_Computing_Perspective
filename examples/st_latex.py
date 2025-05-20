import streamlit as st

st.title("📄 实时 LaTeX 编辑器")

# 输入框
latex_code = st.text_area(
    "请输入 LaTeX 公式（支持 \\begin{bmatrix} 等环境）👇",
    value=r"\\begin{bmatrix} -18 & 23 & 39 \\\\ 42 & 96 & 87 \\\\ 33 & 15 & -54 \\end{bmatrix}",
    height=200
)

# 渲染公式
st.markdown("### 渲染效果：")
try:
    st.latex(latex_code)
except Exception as e:
    st.error(f"渲染失败: {e}")
