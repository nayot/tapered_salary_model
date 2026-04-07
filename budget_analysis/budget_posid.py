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
        st.error(f"ไม่พบไฟล์ข้อมูล: {e}")
        st.stop()
    
    def clean_num(series):
        if series.dtype == 'object' or series.dtype == 'string':
            series = series.str.replace(',', '').str.strip()
        return pd.to_numeric(series, errors='coerce')

    for col in ['Min_Old', 'Min_New', 'Max_Old', 'Max_New', 'POS_ID', 'GRP_ID']:
        if col in df_new_table.columns:
            df_new_table[col] = clean_num(df_new_table[col])
            
    df_salary_all['เงินเดือน'] = clean_num(df_salary_all['เงินเดือน'])
    df_salary_all['POS_ID'] = clean_num(df_salary_all['POS_ID'])
    df_salary_all['GRP_ID'] = clean_num(df_salary_all['GRP_ID'])
    
    return df_new_table.dropna(subset=['POS_ID', 'Min_Old', 'Min_New', 'Max_Old', 'Max_New']), df_salary_all

df_new_table, df_salary_all = load_data()

# --- 3. INITIALIZE SESSION STATE ---
if 'snapshots' not in st.session_state:
    st.session_state.snapshots = []

# --- 4. SIDEBAR: SELECTION & CONTROLS ---
st.sidebar.header("⚙️ การตั้งค่าการวิเคราะห์")

# ข้อ 1: เลือก GRP_ID ก่อน
grp_map = {
    1: "1: สายวิชาการ (อุดมศึกษา)",
    2: "2: สายวิชาการ (ต่ำกว่าอุดมศึกษา)",
    3: "3: สายสนับสนุน (ปฏิบัติการ)",
    4: "4: สายสนับสนุน (ปฏิบัติงาน)"
}
selected_grp_label = st.sidebar.selectbox("เลือกกลุ่มบุคลากรหลัก (GRP_ID)", options=list(grp_map.values()))
selected_grp_id = int(selected_grp_label.split(":")[0])

# เลือกประเภทการจ้าง
hiring_type = st.sidebar.selectbox(
    "เลือกแหล่งงบประมาณจ้าง",
    options=["ทั้งหมด", "เงินอุดหนุนรัฐบาล", "เงินรายได้ส่วนงาน"]
)

# ข้อ 1: เลือกเฉพาะ POS_ID ที่อยู่ใน GRP_ID นั้นๆ
df_grp_filtered = df_new_table[df_new_table['GRP_ID'] == selected_grp_id]
pos_options = [
    f"{int(row['POS_ID'])}: {row['Type']} ({row['Deg_Pos']})" 
    for _, row in df_grp_filtered[['POS_ID', 'Type', 'Deg_Pos']].drop_duplicates().sort_values('POS_ID').iterrows()
]

if not pos_options:
    st.warning("ไม่พบข้อมูลตำแหน่งในกลุ่มนี้")
    st.stop()

selected_pos_label = st.sidebar.selectbox("เลือกตำแหน่งย่อย (POS_ID)", options=pos_options)
selected_pos_id = int(selected_pos_label.split(":")[0])

# ข้อ 2: ดึงค่า Min/Max จากตารางโดยตรง (ไม่ต้องให้ผู้ใช้เลือกเอง)
pos_info = df_new_table[df_new_table['POS_ID'] == selected_pos_id].iloc[0]
b_old = float(pos_info['Min_Old'])
b_new = float(pos_info['Min_New'])
m_old = float(pos_info['Max_Old'])
m_new = float(pos_info['Max_New'])
delta_b = b_new - b_old

st.sidebar.divider()
s_max_pct = st.sidebar.slider("จุดตัดชายธง (% ของช่วงเงินเดิม)", 0, 120, 100)
s_max = b_old + (s_max_pct / 100) * (m_old - b_old)
if s_max <= b_new: s_max = b_new + 1

gamma = st.sidebar.slider("ความโค้ง (Gamma - γ)", 0.1, 5.0, 1.0, 0.1)

# --- 5. UPDATED FUNCTIONS ---
def calculate_new_salary(salary, b_old_val, b_new_val, s_max_val, m_new_val, gamma_val):
    db = b_new_val - b_old_val
    
    # 1. คำนวณเงินเพิ่ม (Adjustment) ตามโซน
    if salary < b_new_val:
        # ข้อ 4: ถ้าไม่ถึง Min_New ให้ปรับขึ้นไปที่ Min_New
        adj = b_new_val - salary
    elif b_new_val <= salary <= s_max_val:
        # โซน Tapering
        ratio = np.clip(1 - (salary - b_new_val) / (s_max_val - b_new_val), 0, 1)
        adj = db * (ratio ** gamma_val)
    else:
        adj = 0

    proposed_salary = salary + adj
    
    # ข้อ 3: ตรวจสอบไม่ให้เกิน Max_New
    if proposed_salary > m_new_val:
        proposed_salary = m_new_val
        
    return proposed_salary - salary # คืนค่าเป็นเงินที่เพิ่มขึ้น

def ceil_to_10(num):
    return math.ceil(num / 10) * 10 if num > 0 else 0

# --- 6. DATA FILTERING & CALCULATION ---
df_target = df_salary_all[df_salary_all['POS_ID'] == selected_pos_id].copy()

if "รัฐบาล" in hiring_type:
    df_target = df_target[df_target['ประเภทบุคลากร'].str.contains('รัฐบาล', na=False)]
elif "รายได้" in hiring_type:
    df_target = df_target[df_target['ประเภทบุคลากร'].str.contains('รายได้', na=False)]

df_target['raw_adj'] = df_target['เงินเดือน'].apply(
    lambda x: calculate_new_salary(x, b_old, b_new, s_max, m_new, gamma)
)
df_target['final_adj'] = df_target['raw_adj'].apply(ceil_to_10)
total_monthly = df_target['final_adj'].sum()

# --- 7. DISPLAY ---
st.title(f"📊 วิเคราะห์งบประมาณ: {pos_info['Type']}")
st.subheader(f"กลุ่ม: {grp_map[selected_grp_id]} | แหล่งเงิน: {hiring_type}")

col_info1, col_info2, col_info3 = st.columns(3)
col_info1.info(f"**ฐานเงินเดือนเดิม:**\n\n{b_old:,.0f} - {m_old:,.0f}")
col_info2.success(f"**ฐานเงินเดือนใหม่:**\n\n{b_new:,.0f} - {m_new:,.0f}")
col_info3.warning(f"**จุดตัดเยียวยา ({s_max_pct}%):**\n\n{s_max:,.0f} บาท")

# กราฟ
s0_range = np.linspace(b_new, m_new, 1000)
# จำลองการคำนวณเงินเพิ่มสำหรับวาดเส้นกราฟ
current_adj_graph = [calculate_new_salary(x, b_old, b_new, s_max, m_new, gamma) for x in s0_range]

fig = go.Figure()
fig.add_trace(go.Histogram(x=df_target['เงินเดือน'], name="พนักงาน", nbinsx=40, marker_color='rgba(150,150,150,0.3)', yaxis='y2'))
fig.add_trace(go.Scatter(x=s0_range, y=current_adj_graph, name="เงินชดเชย", fill='tozeroy', line=dict(color='#0068c9', width=4)))

fig.update_layout(
    xaxis=dict(title="เงินเดือนเดิม (บาท)", range=[b_new - 5000, m_new + 5000]),
    yaxis=dict(title="เงินเพิ่ม (บาท)", side="left"),
    yaxis2=dict(title="จำนวนคน", overlaying="y", side="right", showgrid=False),
    template="plotly_white", hovermode="x unified", height=500
)
st.plotly_chart(fig, use_container_width=True)

# --- 8. SUMMARY ---
c1, c2 = st.columns(2)
with c1:
    st.subheader("💰 สรุปงบประมาณ")
    st.metric("งบประมาณรวม/เดือน", f"{total_monthly:,.0f} บาท", delta=f"{len(df_target)} คน")
    
    df_guarantee = df_target[df_target['เงินเดือน'] < b_new]
    df_max_hit = df_target[(df_target['เงินเดือน'] + df_target['final_adj']) >= m_new]
    st.write(f"- ปรับเข้าสู่ฐานใหม่ ({len(df_guarantee)} คน): **{df_guarantee['final_adj'].sum():,.0f}** บาท")
    st.write(f"- พนักงานที่เงินเดือนแตะเพดานใหม่: **{len(df_max_hit)}** คน")

with c2:
    st.subheader("👤 ทดลองคำนวณ")
    test_sal = st.number_input("เงินเดือนปัจจุบัน:", value=float(b_new))
    res_adj = ceil_to_10(calculate_new_salary(test_sal, b_old, b_new, s_max, m_new, gamma))
    st.metric("เงินเดือนใหม่", f"{test_sal + res_adj:,.0f} บาท", delta=f"เพิ่ม {res_adj:,.0f}")