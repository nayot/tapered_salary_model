import streamlit as st


st.set_page_config(page_title="BUU Salary Budget Portal", layout="wide")

pages = [
    st.Page(
        "budget_posid.py",
        title="วิเคราะห์รายตำแหน่ง",
        icon="📍",
        default=True,
    ),
    st.Page(
        "budget_grpid.py",
        title="วิเคราะห์ภาพรวม",
        icon="📊",
    ),
]

navigation = st.navigation(
    {
        "Budget Analysis": pages,
    }
)

navigation.run()
