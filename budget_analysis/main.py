import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import math
import uuid

# --- 1. SET PAGE CONFIG ---
st.set_page_config(
    page_title="Salary Tapering Model | BUU Analysis",
    layout="wide"
)

# --- 2. LOAD DATA & CLEANING ---
@st.cache_data
def load_data():
    df_new_table = pd.read_parquet("data/new_salary_table.parquet")
    df_salary_all = pd.read_parquet("data/salary_all_posid.parquet")
    
    # ฟังก์ชันช่วยล้างข้อมูลตัวเลข (ป้องกันเครื่องหมาย , และเว้นวรรค)
    def clean_num(series):
        if series.dtype == 'object' or series.dtype == 'string':
            series = series.str.replace(',', '').str.strip()
        return pd.to_numeric(series, errors='coerce')

    # ล้างข้อมูลตารางโครงสร้าง
    for col in ['Min_Old', 'Min_New', 'Max_New', 'POS_ID']:
        if col in df_new_table.columns:
            df_new_table[col] = clean_num(df_new_table[col])
            
    # ล้างข้อมูลบัญชีเงินเดือนพนักงาน
    df_salary_all['เงินเดือน'] = clean_num(df_salary_all['เงินเดือน'])
    df_salary_all['POS_ID'] = clean_num(df_salary_all['POS_ID'])
    
    # กำจัดค่าว่างที่จำเป็น
    df_new_table = df_new_table.dropna(subset=['POS_ID', 'Min_Old', 'Min_New'])
    df_salary_all = df_salary_all.dropna(subset=['เงินเดือน', 'POS_ID'])
    
    return df_new_table, df_salary_all

try:
    df_new_table, df_salary_all = load_data()
except Exception as e:
    st.error(f"เกิดข้อผิดพลาดในการโหลดข้อมูล: {e}")
    st.stop()

# --- 3. INITIALIZE SESSION STATE ---
if 'snapshots' not in st.session_state:
    st.session_state.snapshots = []

# --- 4. SIDEBAR: PARAMETERS & DATA SELECTION ---
st.sidebar.header("⚙️ การตั้งค่าโมเดล & กลุ่มข้อมูล")

# สร้างตัวเลือกที่แสดงทั้ง ID และชื่อกลุ่ม (เช่น "3: สายวิชาการ (ป.เอก)")
# เรียงลำดับตาม POS_ID เพื่อให้หาลำดับเดิมได้ง่าย
df_options = df_new_table[['POS_ID', 'Type', 'Deg_Pos']].drop_duplicates().sort_values('POS_ID')
option_list = [
    f"{int(row['POS_ID'])}: {row['Type']} ({row['Deg_Pos']})" 
    for _, row in df_options.iterrows()
]

# ค้นหา Index ของ POS_ID = 3 เพื่อตั้งเป็นค่าเริ่มต้น
default_index = 0
for i, opt in enumerate(option_list):
    if opt.startswith("3:"):
        default_index = i
        break

selected_option = st.sidebar.selectbox(
    "เลือกกลุ่มบุคลากรเพื่อวิเคราะห์", 
    options=option_list,
    index=default_index
)

# ดึง POS_ID กลับมาเป็นตัวเลขเพื่อใช้ Filter ข้อมูล
selected_pos_id = int(selected_option.split(":")[0])

# ดึงข้อมูลจากตารางโครงสร้างตาม POS_ID ที่เลือก
pos_info = df_new_table[df_new_table['POS_ID'] == selected_pos_id].iloc[0]

# --- ตั้งค่าฐานเงินเดือนตามกลุ่มที่เลือก ---
default_b_old = float(pos_info['Min_Old'])
default_b_new = float(pos_info['Min_New'])
x_limit_max = float(pos_info['Max_New'])

b_old = st.sidebar.number_input("ฐานเดิม (B_old)", value=default_b_old, step=500.0)
b_new = st.sidebar.number_input("ฐานใหม่ (B_new)", value=default_b_new, step=500.0)
delta_b = b_new - b_old

# ปรับ S_max เริ่มต้นให้อยู่ที่ Max_New ของกลุ่มนั้น
s_max = st.sidebar.slider(
    "จุดตัดชายธง (S_max)", 
    min_value=int(b_new), 
    max_value=int(x_limit_max + 20000), 
    value=int(x_limit_max)
)
gamma = st.sidebar.slider("ความโค้ง (Gamma - γ)", min_value=0.1, max_value=5.0, value=1.0, step=0.1)

# --- 5. FUNCTIONS ---
def calculate_adj(salary, b_old_val, s_max_val, delta_b_val, gamma_val):
    # ปรับ Logic: พนักงานที่เงินเดือนต่ำกว่า b_old จะได้รับเงินชดเชยเต็มจำนวน delta_b
    # พนักงานที่เงินเดือนอยู่ระหว่าง b_old และ s_max จะได้รับตามสูตร Tapering
    if isinstance(salary, (int, float, np.float64)):
        if salary < b_old_val: return delta_b_val
    
    ratio = np.clip(1 - (salary - b_old_val) / (s_max_val - b_old_val), 0, 1)
    return delta_b_val * (ratio ** gamma_val)

def ceil_to_10(number):
    if number <= 0: return 0
    return math.ceil(number / 10) * 10

# --- 6. BUDGET CALCULATION ---
df_target = df_salary_all[df_salary_all['POS_ID'] == selected_pos_id].copy()
df_target['raw_adj'] = df_target['เงินเดือน'].apply(lambda x: calculate_adj(x, b_old, s_max, delta_b, gamma))
df_target['final_adj'] = df_target['raw_adj'].apply(ceil_to_10)
total_monthly_budget = df_target['final_adj'].sum()

# --- 7. MAIN DISPLAY: GRAPH WITH OVERLAY ---
st.title(f"📊 วิเคราะห์งบประมาณ: {pos_info['Type']}")
st.caption(f"กลุ่มตำแหน่ง: {pos_info['Deg_Pos']} (POS_ID: {selected_pos_id})")

# เตรียมเส้นกราฟ
s0_range = np.linspace(b_old, x_limit_max, 1000)
# vectorized calculation สำหรับกราฟ
r_adj = np.clip(1 - (s0_range - b_old) / (s_max - b_old), 0, 1)
current_adj = delta_b * (r_adj ** gamma)

fig = go.Figure()

# 1. Histogram (แกน Y ขวา)
fig.add_trace(go.Histogram(
    x=df_target['เงินเดือน'],
    name="จำนวนพนักงาน",
    nbinsx=40,
    marker_color='rgba(150, 150, 150, 0.3)',
    yaxis='y2'
))

# 2. Snapshots
for snap in st.session_state.snapshots:
    if snap['visible']:
        fig.add_trace(go.Scatter(x=snap['x'], y=snap['y'], name=f"Ref: {snap['name']}", line=dict(dash='dash', width=2), opacity=0.5))

# 3. Main Curve
fig.add_trace(go.Scatter(
    x=s0_range, y=current_adj, name="เงินชดเชย", 
    fill='tozeroy', line=dict(color='#0068c9', width=4)
))

fig.update_layout(
    xaxis=dict(title="เงินเดือนเดิม (บาท)", range=[b_old - 5000, x_limit_max + 5000]),
    yaxis=dict(title="เงินชดเชยส่วนต่าง (บาท)", side="left"),
    yaxis2=dict(title="จำนวนพนักงาน (คน)", overlaying="y", side="right", showgrid=False),
    template="plotly_white",
    legend=dict(yanchor="top", y=0.98, xanchor="right", x=0.85, bgcolor="rgba(255, 255, 255, 0.5)"),
    hovermode="x unified",
    height=550
)

st.plotly_chart(fig, use_container_width=True)

# --- 8. SUMMARY & SIMULATOR ---
c1, c2 = st.columns([1, 1])

with c1:
    st.subheader("💰 สรุปงบประมาณรายเดือน")
    m_col1, m_col2 = st.columns(2)
    m_col1.metric("จำนวนพนักงาน", f"{len(df_target):,.0f} คน")
    m_col2.metric("งบประมาณรวม", f"{total_monthly_budget:,.0f} บาท", delta=f"~{total_monthly_budget*12:,.0f} / ปี", delta_color="inverse")
    
    st.write(f"**โครงสร้างอ้างอิง:**")
    st.text(f"Min เดิม: {default_b_old:,.0f} | Min ใหม่: {default_b_new:,.0f} | Max ใหม่: {x_limit_max:,.0f}")

with c2:
    st.subheader("👤 ทดสอบรายบุคคล")
    test_sal = st.number_input("ใส่เงินเดือนปัจจุบัน:", value=float(df_target['เงินเดือน'].median() if not df_target.empty else b_old))
    res_adj = ceil_to_10(calculate_adj(test_sal, b_old, s_max, delta_b, gamma))
    st.metric("เงินเดือนที่จะได้รับใหม่", f"{test_sal + res_adj:,.0f} บาท", delta=f"เงินเพิ่ม {res_adj:,.0f}")

# --- 9. CAPTURE ---
if st.sidebar.button("➕ Capture กราฟปัจจุบัน"):
    st.session_state.snapshots.append({
        'id': str(uuid.uuid4())[:4],
        'name': f"γ={gamma:.1f}, Smax={s_max/1000:.0f}k",
        'x': s0_range, 'y': current_adj, 'visible': True
    })
    st.sidebar.success("บันทึกสำเร็จ")