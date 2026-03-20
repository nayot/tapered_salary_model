import streamlit as st
import numpy as np
import plotly.graph_objects as go
import math
import uuid

# --- 1. SET PAGE CONFIG ---
st.set_page_config(
    page_title="Salary Tapering Model | BUU",
    layout="wide"
)

# --- 2. INITIALIZE SESSION STATE (สำหรับเก็บภาพจำ) ---
if 'snapshots' not in st.session_state:
    st.session_state.snapshots = []

# --- 3. SIDEBAR: PARAMETERS & SNAPSHOT CONTROL ---
st.sidebar.header("⚙️ การตั้งค่าโมเดล")

b_old = st.sidebar.number_input("ฐานเดิม (B_old)", value=31500, step=500)
b_new = st.sidebar.number_input("ฐานใหม่ (B_new)", value=35000, step=500)
delta_b = b_new - b_old

s_max = st.sidebar.slider("จุดตัดชายธง (S_max)", min_value=int(b_new), max_value=120000, value=35000)
gamma = st.sidebar.slider("ความโค้ง (Gamma - γ)", min_value=0.1, max_value=5.0, value=1.0, step=0.1)

# --- ส่วน Capture กราฟ ---
st.sidebar.markdown("---")
st.sidebar.subheader("📸 ระบบเปรียบเทียบ (Snapshots)")

if st.sidebar.button("➕ Capture กราฟปัจจุบัน"):
    # บันทึกข้อมูลเส้นปัจจุบันลงในรายการ
    snap_name = f"γ={gamma:.1f}, Smax={s_max/1000:.0f}k"
    # คำนวณชุดข้อมูลสำหรับ snapshot นี้
    s0_snap = np.linspace(b_old, s_max + 5000, 1000)
    ratio_snap = np.clip(1 - (s0_snap - b_old) / (s_max - b_old), 0, 1)
    adj_snap = delta_b * (ratio_snap ** gamma)
    
    st.session_state.snapshots.append({
        'id': str(uuid.uuid4())[:4],
        'name': snap_name,
        'x': s0_snap,
        'y': adj_snap,
        'visible': True
    })
    st.sidebar.success(f"บันทึก {snap_name} แล้ว")

# แสดงรายการที่ Capture ไว้
if st.session_state.snapshots:
    for i, snap in enumerate(st.session_state.snapshots):
        col_check, col_del = st.sidebar.columns([3, 1])
        snap['visible'] = col_check.checkbox(f"แสดง: {snap['name']}", value=snap['visible'], key=f"cap_{i}")
        if col_del.button("🗑️", key=f"del_{i}"):
            st.session_state.snapshots.pop(i)
            st.rerun()
    
    if st.sidebar.button("🗑️ ล้างทั้งหมด"):
        st.session_state.snapshots = []
        st.rerun()

# --- 4. FUNCTIONS ---
def calculate_adj(salary, b_old_val, s_max_val, delta_b_val, gamma_val):
    ratio = np.clip(1 - (salary - b_old_val) / (s_max_val - b_old_val), 0, 1)
    return delta_b_val * (ratio ** gamma_val)

def ceil_to_10(number):
    """ปัดเศษตั้งแต่ 1 บาทขึ้นไป เป็น 10 บาท"""
    if number <= 0: return 0
    return math.ceil(number / 10) * 10

# ข้อมูลเส้นหลักปัจจุบัน
s0_range = np.linspace(b_old, s_max + 5000, 1000)
current_adj = calculate_adj(s0_range, b_old, s_max, delta_b, gamma)

# --- 5. MAIN DISPLAY: GRAPH ---
st.title("📊 ระบบจำลองการปรับเงินเดือนชดเชย (Flexible Tapering)")

fig = go.Figure()

# 1. วาดเส้นที่เคย Capture ไว้ (เป็นเส้นประ)
for snap in st.session_state.snapshots:
    if snap['visible']:
        fig.add_trace(go.Scatter(
            x=snap['x'], 
            y=snap['y'], 
            name=f"อ้างอิง: {snap['name']}",
            line=dict(dash='dash', width=2),
            opacity=0.6
        ))

# 2. วาดเส้นหลักปัจจุบัน (เส้นทึบ)
fig.add_trace(go.Scatter(
    x=s0_range, 
    y=current_adj, 
    name="โมเดลปัจจุบัน", 
    fill='tozeroy', 
    line=dict(color='#1f77b4', width=4)
))

fig.update_layout(
    xaxis_title="เงินเดือนเดิม (บาท)",
    yaxis_title="เงินชดเชยส่วนต่าง (บาท)",
    template="plotly_white",
    legend=dict(yanchor="top", y=0.98, xanchor="right", x=0.98, bgcolor="rgba(255, 255, 255, 0.5)"),
    hovermode="x unified"
)

st.plotly_chart(fig, use_container_width=True)

# --- 6. INDIVIDUAL SIMULATOR ---
st.divider()
st.subheader("👤 เครื่องมือจำลองรายบุคคล (Individual Simulator)")

input_col, space = st.columns([1, 2])
with input_col:
    test_sal = st.number_input("ระบุเงินเดือนปัจจุบัน (บาท):", value=20000, step=1000)

raw_adj = calculate_adj(test_sal, b_old, s_max, delta_b, gamma)
final_adj = ceil_to_10(raw_adj)
final_new_salary = test_sal + final_adj

m1, m2, m3 = st.columns(3)
m1.metric("เงินเดือนเดิม", f"{test_sal:,.0f} บาท")
m2.metric("เงินชดเชย (ปัดเป็น 10)", f"{final_adj:,.0f} บาท", delta=f"{final_adj:,.0f}")
m3.metric("เงินเดือนใหม่สุทธิ", f"{final_new_salary:,.0f} บาท")

if final_adj > 0:
    st.caption(f"💡 คำนวณจริงได้ {raw_adj:,.2f} บาท → ปัดเศษตามเงื่อนไขเป็น {final_adj:,.0f} บาท")