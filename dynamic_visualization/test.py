import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# 设置页面标题
st.title("动态交互式数据可视化")

# 创建一个可选择的下拉框（选择数据类别）
data_type = st.selectbox('选择数据类型', ['销售数据', '财务数据', '市场数据'])

# 模拟不同的数据
if data_type == '销售数据':
    data = pd.DataFrame({
        '月份': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
        '销售额': [100, 150, 200, 250, 300, 350],
        '利润': [20, 40, 60, 80, 100, 120]
    })
elif data_type == '财务数据':
    data = pd.DataFrame({
        '月份': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
        '收入': [500, 550, 600, 650, 700, 750],
        '支出': [200, 250, 300, 350, 400, 450]
    })
else:
    data = pd.DataFrame({
        '月份': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
        '广告费': [50, 75, 100, 125, 150, 175],
        '市场份额': [10, 15, 20, 25, 30, 35]
    })

# 显示选择的数据表格
st.subheader(f"{data_type} 表格")
st.dataframe(data)

# 创建一个动态更新的图表
if data_type == '销售数据':
    # 销售数据的图表
    fig = px.line(data, x='月份', y=['销售额', '利润'], title=f"{data_type} - 销售与利润趋势")
elif data_type == '财务数据':
    # 财务数据的图表
    fig = px.bar(data, x='月份', y=['收入', '支出'], title=f"{data_type} - 收入与支出对比")
else:
    # 市场数据的图表
    fig = px.scatter(data, x='广告费', y='市场份额', title=f"{data_type} - 广告费与市场份额关系")

st.plotly_chart(fig)

# 可以添加其他交互式组件，例如根据用户选择展示不同的图表类型
chart_type = st.radio('选择图表类型', ['折线图', '柱状图', '散点图'])

if chart_type == '折线图':
    st.plotly_chart(fig)
elif chart_type == '柱状图':
    fig.update_traces(type='bar')
    st.plotly_chart(fig)
else:
    fig.update_traces(type='scatter', mode='markers')
    st.plotly_chart(fig)
