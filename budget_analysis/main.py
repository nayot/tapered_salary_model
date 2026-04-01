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
    try:
        df_new_table = pd.read_parquet("data/new_salary_table.parquet")
        df_salary_all = pd.read_parquet("data/salary_all_posid.parquet")
    except Exception as e:
        st.error(f"ไม่พบไฟล์ข้อมูลหรือไฟล์เสียหาย: {e}")
        st.stop()
    
    # ฟังก์ชันช่วยล้างข้อมูลตัวเลข (ป้องกันเครื่องหมาย , และเว้นวรรค)
    def clean_num(series):
        if series.dtype == 'object' or series.dtype == 'string':
            series = series.str.replace(',', '').str.strip()
        return pd.to_numeric(series, errors='coerce')

    # ล้างข้อมูลตารางโครงสร้าง (Columns: POS_ID, Type, Deg_Pos, Min_Old, Min_New, Max_Old, Max_New)
    for col in ['Min_Old', 'Min_New', 'Max_Old', 'Max_New', 'POS_ID']:
        if col in df_new_table.columns:
            df_new_table[col] = clean_num(df_new_table[col])
            
    # ล้างข้อมูลบัญชีเงินเดือนพนักงาน
    df_salary_all['เงินเดือน'] = clean_num(df_salary_all['เงินเดือน'])
    df_salary_all['POS_ID'] = clean_num(df_salary_all['POS_ID'])
    
    # กำจัดค่าว่างในคอลัมน์สำคัญ
    df_new_table = df_new_table.dropna(subset=['POS_ID', 'Min_Old', 'Min_New', 'Max_Old'])
    df_salary_all = df_salary_all.dropna(subset=['เงินเดือน', 'POS_ID'])
    
    return df_new_table, df_salary_all

df_new_table, df_salary_all = load_data()

# --- 3. INITIALIZE SESSION STATE ---
if 'snapshots' not in st.session_state:
    st.session_state.snapshots = []

# --- 4. SIDEBAR: PARAMETERS & DATA SELECTION ---
st.sidebar.header("⚙️ การตั้งค่าโมเดล & กลุ่มข้อมูล")

# สร้างตัวเลือกแสดงผล (ID: Type (Deg))
df_options = df_new_table[['POS_ID', 'Type', 'Deg_Pos']].drop_duplicates().sort_values('POS_ID')
option_list = [
    f"{int(row['POS_ID'])}: {row['Type']} ({row['Deg_Pos']})" 
    for _, row in df_options.iterrows()
]

# Default POS_ID = 3
default_index = 0
for i, opt in enumerate(option_list):
    if opt.startswith("3:"):
        default_index = i
        break

selected_option = st.sidebar.selectbox("เลือกกลุ่มบุคลากรเพื่อวิเคราะห์", options=option_list, index=default_index)
selected_pos_id = int(selected_option.split(":")[0])

# ดึงค่าจากตารางโครงสร้าง
pos_info = df_new_table[df_new_table['POS_ID'] == selected_pos_id].iloc[0]

min_old_val = float(pos_info['Min_Old'])
min_new_val = float(pos_info['Min_New'])
max_old_val = float(pos_info['Max_Old'])
range_old = max_old_val - min_old_val

# Sidebar Inputs
b_old = st.sidebar.number_input("ฐานเดิม (B_old)", value=min_old_val, step=500.0)
b_new = st.sidebar.number_input("ฐานใหม่ (B_new)", value=min_new_val, step=500.0)
delta_b = b_new - b_old

# Logic S_max (%): 0% = b_old, 100% = max_old
s_max_pct = st.sidebar.slider(
    "จุดตัดชายธง (% ของช่วงเงินเดิม)", 
    min_value=0, max_value=120, value=100,
    help="0% คือ Min_Old, 100% คือ Max_Old"
)
s_max = b_old + (s_max_pct / 100) * range_old

# ป้องกัน s_max ต่ำกว่า b_new
if s_max <= b_new:
    s_max = b_new + 0.01

gamma = st.sidebar.slider("ความโค้ง (Gamma - γ)", min_value=0.1, max_value=5.0, value=1.0, step=0.1)

# --- 5. FUNCTIONS ---
def calculate_adj(salary, b_old_val, b_new_val, s_max_val, gamma_val):
    delta_b_val = b_new_val - b_old_val
    
    # 1. Guarantee Min_New (ช้อนคนเงินเดือนต่ำกว่าฐานใหม่)
    if salary < b_new_val:
        return b_new_val - salary

    # 2. Tapering Zone (เริ่มตั้งแต่ b_new_val เป็นต้นไป)
    if b_new_val <= salary <= s_max_val:
        ratio = np.clip(1 - (salary - b_new_val) / (s_max_val - b_new_val), 0, 1)
        return delta_b_val * (ratio ** gamma_val)

    return 0

def ceil_to_10(number):
    return math.ceil(number / 10) * 10 if number > 0 else 0

# --- 6. BUDGET CALCULATION ---
df_target = df_salary_all[df_salary_all['POS_ID'] == selected_pos_id].copy()
df_target['raw_adj'] = df_target['เงินเดือน'].apply(
    lambda x: calculate_adj(x, b_old, b_new, s_max, gamma)
)
df_target['final_adj'] = df_target['raw_adj'].apply(ceil_to_10)
total_monthly = df_target['final_adj'].sum()

# --- 7. MAIN DISPLAY: GRAPH ---
st.title(f"📊 วิเคราะห์งบประมาณ: {pos_info['Type']}")
st.caption(f"ระดับ: {pos_info['Deg_Pos']} | จุดตัด ({s_max_pct}%): {s_max:,.0f} บาท")

# กราฟเริ่มที่ B_new และจบที่ Max_Old ตามโจทย์
s0_range = np.linspace(b_new, max_old_val, 1000)
r_adj_graph = np.clip(1 - (s0_range - b_new) / (s_max - b_new), 0, 1)
current_adj_graph = delta_b * (r_adj_graph ** gamma)

fig = go.Figure()

# 1. Histogram (พนักงานทุกคนในกลุ่ม)
fig.add_trace(go.Histogram(
    x=df_target['เงินเดือน'], name="จำนวนพนักงาน",
    nbinsx=40, marker_color='rgba(150, 150, 150, 0.3)', yaxis='y2'
))

# 2. Snapshots (ประวัติ)
for snap in st.session_state.snapshots:
    if snap['visible']:
        fig.add_trace(go.Scatter(x=snap['x'], y=snap['y'], name=f"Ref: {snap['name']}", line=dict(dash='dash', width=2), opacity=0.5))

# 3. Main Tapering Curve
fig.add_trace(go.Scatter(
    x=s0_range, y=current_adj_graph, name="เงินชดเชยเยียวยา", 
    fill='tozeroy', line=dict(color='#0068c9', width=4)
))

fig.update_layout(
    xaxis=dict(title="เงินเดือนเดิม (บาท)", range=[b_new - 3000, max_old_val + 2000]),
    yaxis=dict(title="เงินชดเชย (บาท)", side="left"),
    yaxis2=dict(title="จำนวนพนักงาน (คน)", overlaying="y", side="right", showgrid=False),
    template="plotly_white", hovermode="x unified", height=550
)

st.plotly_chart(fig, use_container_width=True)

# --- 8. SUMMARY & SIMULATOR ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("💰 สรุปงบประมาณ")
    m1, m2 = st.columns(2)
    m1.metric("จำนวนพนักงาน", f"{len(df_target):,.0f} คน")
    m2.metric("งบประมาณรายเดือน", f"{total_monthly:,.0f} บาท", delta=f"~{total_monthly*12:,.0f} / ปี", delta_color="inverse")
    
    # แยกส่วนประกอบงบประมาณ
    df_guarantee = df_target[df_target['เงินเดือน'] < b_new]
    df_taper = df_target[df_target['เงินเดือน'] >= b_new]
    st.write(f"- ส่วน Guarantee ฐานใหม่ ({len(df_guarantee)} คน): **{df_guarantee['final_adj'].sum():,.0f}** บาท")
    st.write(f"- ส่วนชดเชยเยียวยา ({len(df_taper)} คน): **{df_taper['final_adj'].sum():,.0f}** บาท")

with col2:
    st.subheader("👤 ทดสอบรายบุคคล")
    test_sal = st.number_input("เงินเดือนปัจจุบัน:", value=float(b_new))
    res_adj = ceil_to_10(calculate_adj(test_sal, b_old, b_new, s_max, gamma))
    st.metric("เงินเดือนใหม่", f"{test_sal + res_adj:,.0f} บาท", delta=f"เพิ่ม {res_adj:,.0f}")

# --- 9. CAPTURE SNAPSHOT ---
if st.sidebar.button("➕ Capture กราฟปัจจุบัน"):
    st.session_state.snapshots.append({
        'id': str(uuid.uuid4())[:4],
        'name': f"γ={gamma:.1f}, Smax={s_max_pct}%",
        'x': s0_range, 'y': current_adj_graph, 'visible': True
    })
    st.sidebar.success("บันทึก Snapshot แล้ว")