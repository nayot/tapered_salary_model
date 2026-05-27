import os

import streamlit as st


st.set_page_config(page_title="BUU Salary Budget Portal", layout="wide")


def _read_secret_section(section_name):
    try:
        return st.secrets.get(section_name, {})
    except Exception:
        return {}


def _normalize_email_list(value):
    if value is None:
        return set()
    if isinstance(value, str):
        items = value.replace("\n", ",").split(",")
    else:
        items = value
    return {str(item).strip().lower() for item in items if str(item).strip()}


def _allowed_emails():
    authz = _read_secret_section("authorization")
    from_secrets = _normalize_email_list(authz.get("allowed_emails"))
    from_env = _normalize_email_list(os.getenv("ALLOWED_EMAILS"))
    return from_secrets | from_env


def require_google_login():
    allowed_emails = _allowed_emails()

    if not st.user.is_logged_in:
        st.title("BUU Salary Budget Portal")
        st.caption("กรุณาเข้าสู่ระบบด้วยบัญชี Google ที่ได้รับอนุญาต")
        if not allowed_emails:
            st.warning("ยังไม่ได้กำหนดรายชื่ออีเมลที่อนุญาตให้ใช้งาน")
        if st.button("เข้าสู่ระบบด้วย Google", type="primary"):
            st.login("google")
        st.stop()

    user_email = str(st.user.get("email", "")).strip().lower()
    email_verified = st.user.get("email_verified", True)

    if not user_email or not email_verified or user_email not in allowed_emails:
        st.title("ไม่ได้รับอนุญาต")
        st.error("บัญชี Google นี้ไม่ได้อยู่ในรายชื่อผู้มีสิทธิ์ใช้งานระบบ")
        if user_email:
            st.caption(f"บัญชีที่เข้าสู่ระบบ: {user_email}")
        st.button("ออกจากระบบ", on_click=st.logout)
        st.stop()

    with st.sidebar:
        st.caption(f"เข้าสู่ระบบ: {user_email}")
        st.button("ออกจากระบบ", on_click=st.logout)


require_google_login()

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
