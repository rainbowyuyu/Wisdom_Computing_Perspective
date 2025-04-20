from streamlit_js_eval import streamlit_js_eval, get_geolocation
import streamlit as st

def is_computer():
    device_info = streamlit_js_eval(js_expressions="window.innerWidth", key="width")
    if device_info:
        width = device_info
        if width < 768:
            return False
        else:
            return True

def mobile_or_computer_warning():
    device_info = streamlit_js_eval(js_expressions="window.innerWidth", key="width")
    if device_info:
        width = device_info
        if width < 768:
            st.warning("👆 当前为手机端，需要切换页面和其他功能设置请展开侧边导航栏按钮")
        else:
            st.warning("👈 当前为电脑端，需要切换页面和其他功能设置请点击侧边导航栏按钮")

def login_config():
    if st.session_state.get("logged_in"):
        st.sidebar.success(f"已登录：{st.session_state['username']}")
    else:
        st.sidebar.warning("未登录")


def page_foot():
    # 页脚
    st.markdown("---")

    st.markdown(
        "<p style='text-align: center; color: gray;'>© 2025 智算视界 · Authored by rainbow_yu</p>",
        unsafe_allow_html=True
    )

def add_empty_lines(n=1):
    """添加指定数量的空行"""
    for _ in range(n):
        st.markdown("<br>", unsafe_allow_html=True)