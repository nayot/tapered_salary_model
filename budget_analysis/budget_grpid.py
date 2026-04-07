import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import math

# --- 1. SET PAGE CONFIG ---
st.set_page_config(
    page_title="Total Salary Analysis | BUU",
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

# --- 4. SIDEBAR: SELECTION ---
st.sidebar.header("⚙️ วิเคราะห์งบประมาณภาพรวม")

grp_options = {
    0: "0: ทั้งหมด (รวมทุกกลุ่ม)",
    1: "1: สายวิชาการ (อุดมศึกษา)",
    2: "2: สายวิชาการ (ต่ำกว่าอุดมศึกษา)",
    3: "3: สายสนับสนุน (ปฏิบัติการ)",
    4: "4: สายสนับสนุน (ปฏิบัติงาน)"
}
selected_grp_label = st.sidebar.selectbox("เลือกกลุ่มบุคลากรหลัก", options=list(grp_options.values()))
selected_grp_id = int(selected_grp_label.split(":")[0])

hiring_type = st.sidebar.selectbox(
    "เลือกแหล่งงบประมาณจ้าง",
    options=["ทั้งหมด", "เงินอุดหนุนรัฐบาล", "เงินรายได้ส่วนงาน"]
)

st.sidebar.divider()
s_max_pct = st.sidebar.slider("จุดตัดชายธง (% ของ Max_Old แต่ละตำแหน่ง)", 0, 120, 100)
gamma = st.sidebar.slider("ความโค้ง (Gamma - γ)", 0.1, 5.0, 1.0, 0.1)

# --- 5. LOGIC FUNCTIONS ---
def calculate_adjustment(emp_row, df_ref, pct_val, gamma_val):
    ref = df_ref[df_ref['POS_ID'] == emp_row['POS_ID']]
    if ref.empty: return 0
    
    ref = ref.iloc[0]
    b_old, b_new = ref['Min_Old'], ref['Min_New']
    m_old, m_new = ref['Max_Old'], ref['Max_New']
    
    s_max_val = b_old + (pct_val / 100) * (m_old - b_old)
    if s_max_val <= b_new: s_max_val = b_new + 1
    
    salary = emp_row['เงินเดือน']
    delta_b = b_new - b_old
    
    if salary < b_new:
        adj = b_new - salary
    elif b_new <= salary <= s_max_val:
        ratio = np.clip(1 - (salary - b_new) / (s_max_val - b_new), 0, 1)
        adj = delta_b * (ratio ** gamma_val)
    else:
        adj = 0
        
    proposed = salary + adj
    if proposed > m_new:
        adj = m_new - salary
        
    return math.ceil(adj / 10) * 10 if adj > 0 else 0

# --- 6. DATA FILTERING ---
# กรณีเลือก 0 (ทั้งหมด) ไม่ต้องกรอง GRP_ID
if selected_grp_id == 0:
    df_grp_emp = df_salary_all.copy()
else:
    df_grp_emp = df_salary_all[df_salary_all['GRP_ID'] == selected_grp_id].copy()

# กรองแหล่งเงิน
if "รัฐบาล" in hiring_type:
    df_grp_emp = df_grp_emp[df_grp_emp['ประเภทบุคลากร'].str.contains('รัฐบาล', na=False)]
elif "รายได้" in hiring_type:
    df_grp_emp = df_grp_emp[df_grp_emp['ประเภทบุคลากร'].str.contains('รายได้', na=False)]

# คำนวณเงินเพิ่ม
df_grp_emp['final_adj'] = df_grp_emp.apply(
    lambda row: calculate_adjustment(row, df_new_table, s_max_pct, gamma), axis=1
)

# Merge ข้อมูลชื่อตำแหน่ง (เพื่อป้องกัน KeyError: 'Type')
df_pos_info = df_new_table[['POS_ID', 'Type', 'Deg_Pos', 'GRP_ID']].drop_duplicates()
df_grp_emp = df_grp_emp.merge(df_pos_info, on=['POS_ID', 'GRP_ID'], how='left')

total_monthly = df_grp_emp['final_adj'].sum()

# --- 7. DISPLAY: METRICS ---
st.title(f"📊 วิเคราะห์งบประมาณ: {grp_options[selected_grp_id].split(': ')[1]}")
st.subheader(f"แหล่งงบประมาณ: {hiring_type}")

# เพิ่มแถวสรุปงบประมาณรายปี
c1, c2, c3 = st.columns(3)
c1.metric("พนักงานที่เข้าเงื่อนไข", f"{len(df_grp_emp):,.0f} คน")
c2.metric("งบประมาณรวม (รายเดือน)", f"{total_monthly:,.0f} บาท", 
          delta=f"รายปี: {total_monthly * 12:,.0f} บาท", delta_color="normal")
c3.metric("เฉลี่ยเงินเพิ่มต่อคน/เดือน", f"{(total_monthly/len(df_grp_emp) if len(df_grp_emp)>0 else 0):,.0f} บาท")

# --- 8. SUMMARY TABLE BY GROUP/POSITION ---
st.divider()

if selected_grp_id == 0:
    st.subheader("📋 สรุปงบประมาณแยกตามกลุ่มบุคลากร (รายปี)")
    summary_grp = df_grp_emp.groupby('GRP_ID').agg({
        'final_adj': ['count', 'sum']
    }).reset_index()
    summary_grp.columns = ['GRP_ID', 'จำนวนคน', 'งบรวม/เดือน']
    
    # คำนวณงบรายปีเพิ่ม
    summary_grp['งบรวม/ปี'] = summary_grp['งบรวม/เดือน'] * 12
    summary_grp['ชื่อกลุ่ม'] = summary_grp['GRP_ID'].map(lambda x: grp_options.get(x, "อื่นๆ"))
    
    # แสดงผลตารางสรุป
    st.table(summary_grp[['ชื่อกลุ่ม', 'จำนวนคน', 'งบรวม/เดือน', 'งบรวม/ปี']].style.format({
        'งบรวม/เดือน': '{:,.0f}', 
        'งบรวม/ปี': '{:,.0f}'
    }))

else:
    st.subheader("📋 รายละเอียดงบประมาณแยกตามตำแหน่ง (รายปี)")
    summary_pos = df_grp_emp.groupby(['Type', 'Deg_Pos']).agg({
        'final_adj': ['count', 'sum']
    }).reset_index()
    summary_pos.columns = ['ตำแหน่ง', 'ระดับ', 'จำนวนคน', 'งบรวม/เดือน']
    
    # คำนวณงบรายปีเพิ่ม
    summary_pos['งบรวม/ปี'] = summary_pos['งบรวม/เดือน'] * 12
    
    st.dataframe(summary_pos.style.format({
        'งบรวม/เดือน': '{:,.0f}', 
        'งบรวม/ปี': '{:,.0f}'
    }), use_container_width=True)

# --- ส่วนการพล็อต Box Plot คงเดิมตามที่คุณใช้งานอยู่ ---
# --- 8. SUMMARY TABLE BY GROUP/POSITION ---
st.divider()
if selected_grp_id == 0:
    st.subheader("📋 สรุปงบประมาณแยกตามกลุ่มบุคลากร (GRP_ID)")
    summary_grp = df_grp_emp.groupby('GRP_ID').agg({
        'final_adj': ['count', 'sum', 'mean']
    }).reset_index()
    summary_grp.columns = ['GRP_ID', 'จำนวนคน', 'งบประมาณรวม', 'เฉลี่ยต่อคน']
    # Map ชื่อกลุ่มกลับมาแสดง
    summary_grp['ชื่อกลุ่ม'] = summary_grp['GRP_ID'].map(lambda x: grp_options.get(x, "อื่นๆ"))
    st.table(summary_grp[['ชื่อกลุ่ม', 'จำนวนคน', 'งบประมาณรวม', 'เฉลี่ยต่อคน']].style.format({'งบประมาณรวม': '{:,.0f}', 'เฉลี่ยต่อคน': '{:,.0f}'}))
else:
    st.subheader("📋 รายละเอียดแยกตามตำแหน่งในกลุ่ม")
    summary_pos = df_grp_emp.groupby(['Type', 'Deg_Pos']).agg({
        'final_adj': ['count', 'sum', 'mean']
    }).reset_index()
    summary_pos.columns = ['ตำแหน่ง', 'ระดับ', 'จำนวนคน', 'งบรวม', 'เฉลี่ย/คน']
    st.dataframe(summary_pos.style.format({'งบรวม': '{:,.0f}', 'เฉลี่ย/คน': '{:,.0f}'}), use_container_width=True)

# --- 9. BOX PLOT ---
st.divider()
st.subheader("📊 การกระจายตัวของเงินเพิ่ม")
if not df_grp_emp.empty:
    # กำหนดแกน X: ถ้าเลือกทั้งหมดให้โชว์ตามกลุ่ม ถ้าเลือกรายกลุ่มให้โชว์ตามตำแหน่ง
    x_axis = 'Type' if selected_grp_id != 0 else 'GRP_ID'
    
    fig = go.Figure()
    fig.add_trace(go.Box(
        x=df_grp_emp[x_axis].map(lambda x: grp_options[x] if x_axis == 'GRP_ID' else x),
        y=df_grp_emp['final_adj'],
        marker_color='#0068c9',
        boxpoints='outliers'
    ))
    fig.update_layout(xaxis_title="กลุ่ม/ตำแหน่ง", yaxis_title="เงินเพิ่ม (บาท)", template="plotly_white", height=500)
    st.plotly_chart(fig, use_container_width=True)