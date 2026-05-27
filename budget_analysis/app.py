import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import math
from datetime import date

st.set_page_config(page_title="BUU Salary Analysis", layout="wide")

# --- DATA LOADING ---
@st.cache_data
def load_data():
    try:
        df_new_table = pd.read_parquet("data/new_salary_table.parquet")
        df_salary_all = pd.read_parquet("data/salary_all_checked_posid.parquet")
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

# --- CONSTANTS ---
CURRENT_YEAR = date.today().year

GRP_MAP = {
    0: "0: ทั้งหมด (รวมทุกกลุ่ม)",
    1: "1: สายวิชาการ (อุดมศึกษา)",
    2: "2: สายวิชาการ (ต่ำกว่าอุดมศึกษา)",
    3: "3: สายสนับสนุน (ปฏิบัติการ)",
    4: "4: สายสนับสนุน (ปฏิบัติงาน)",
}

_repl_cache = {}
for _g, _deg_filter in [(1, 'เอก'), (2, 'เอก'), (3, 'ตรี'), (4, None)]:
    _cands = (
        df_new_table[df_new_table['GRP_ID'] == _g]
        if _deg_filter is None
        else df_new_table[(df_new_table['GRP_ID'] == _g) &
                          (df_new_table['Deg_Pos'].str.contains(_deg_filter, na=False))]
    )
    _row = _cands.loc[_cands['Min_New'].idxmin()]
    _repl_cache[_g] = {'POS_ID': float(_row['POS_ID']), 'Min_New': float(_row['Min_New'])}
REPLACEMENT_LOOKUP = _repl_cache


# --- SHARED FUNCTIONS ---
def ceil_to_10(num):
    return math.ceil(num / 10) * 10 if num > 0 else 0


def calculate_new_salary(salary, b_old_val, b_new_val, s_max_val, m_new_val, gamma_val):
    """Returns raw (unceiled) adjustment for a single salary. Used by tab 1."""
    db = b_new_val - b_old_val
    if salary < b_new_val:
        adj = b_new_val - salary
    elif b_new_val <= salary <= s_max_val:
        ratio = np.clip(1 - (salary - b_new_val) / (s_max_val - b_new_val), 0, 1)
        adj = db * (ratio ** gamma_val)
    else:
        adj = 0
    proposed = salary + adj
    if proposed > m_new_val:
        proposed = m_new_val
    return proposed - salary


def calculate_adjustment(emp_row, df_ref, pct_val, gamma_val):
    """Returns ceiled adjustment for a DataFrame row. Used by tab 2."""
    ref = df_ref[df_ref['POS_ID'] == emp_row['POS_ID']]
    if ref.empty:
        return 0
    ref = ref.iloc[0]
    b_old, b_new = ref['Min_Old'], ref['Min_New']
    m_old, m_new = ref['Max_Old'], ref['Max_New']
    s_max_val = b_old + (pct_val / 100) * (m_old - b_old)
    if s_max_val <= b_new:
        s_max_val = b_new + 1
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


def _calc_adj_vectorized(df_work, df_ref, pct_val, gamma_val):
    ref = df_ref[['POS_ID', 'Min_Old', 'Min_New', 'Max_Old', 'Max_New']].drop_duplicates('POS_ID')
    m = df_work[['เงินเดือน', 'POS_ID']].merge(ref, on='POS_ID', how='left')
    s = m['เงินเดือน'].to_numpy(float)
    b_old = m['Min_Old'].to_numpy(float);  b_new = m['Min_New'].to_numpy(float)
    m_old = m['Max_Old'].to_numpy(float);  m_new = m['Max_New'].to_numpy(float)
    delta_b = b_new - b_old
    s_max = b_old + (pct_val / 100.0) * (m_old - b_old)
    s_max = np.where(s_max <= b_new, b_new + 1.0, s_max)
    adj = np.where(s < b_new, b_new - s, 0.0)
    denom = np.where((s_max - b_new) == 0, 1e-9, s_max - b_new)
    ratio = np.clip(1.0 - (s - b_new) / denom, 0.0, 1.0)
    adj = np.where((s >= b_new) & (s <= s_max), delta_b * (ratio ** gamma_val), adj)
    adj = np.where(s + adj > m_new, m_new - s, adj)
    adj = np.where(adj < 0, 0.0, adj)
    return np.where(adj > 0, np.ceil(adj / 10.0) * 10.0, 0.0)


def project_budget(df_grp_emp, df_ref, pct_val, gamma_val, annual_raise_pct, projection_years):
    year0_adj   = float(df_grp_emp['final_adj'].sum()) * 12.0
    year0_total = float((df_grp_emp['เงินเดือน'] + df_grp_emp['final_adj']).sum()) * 12.0
    df_orig = df_grp_emp[['เงินเดือน', 'POS_ID', 'GRP_ID']].copy()
    df_orig['ret_year_ce'] = df_grp_emp['วันที่เกษียณอายุ'].dt.year - 543
    repl_salaries = np.array([], dtype=float)
    raise_factor  = 1.0 + annual_raise_pct / 100.0
    records = [{'ปีไทย (พ.ศ.)':      CURRENT_YEAR + 543,
                'จำนวนพนักงาน':      len(df_grp_emp),
                'เงินเพิ่มรายปี':     year0_adj,
                'เงินเดือนรวมรายปี': year0_total}]
    for yr_offset in range(1, projection_years + 1):
        sim_year = CURRENT_YEAR + yr_offset
        df_orig = df_orig.copy()
        df_orig['เงินเดือน'] *= raise_factor
        repl_salaries = repl_salaries * raise_factor
        mask_retiring = df_orig['ret_year_ce'] == sim_year
        retirees_grp  = df_orig.loc[mask_retiring, 'GRP_ID'].to_numpy()
        df_orig = df_orig[~mask_retiring].reset_index(drop=True)
        if len(retirees_grp) > 0:
            new_sal = np.array([REPLACEMENT_LOOKUP[int(g)]['Min_New'] for g in retirees_grp])
            repl_salaries = np.concatenate([repl_salaries, new_sal])
        adj_arr    = _calc_adj_vectorized(df_orig, df_ref, pct_val, gamma_val)
        annual_adj = float(np.nansum(adj_arr)) * 12.0
        total_salary = float(
            df_orig['เงินเดือน'].sum() + np.nansum(adj_arr) + repl_salaries.sum()
        ) * 12.0
        records.append({'ปีไทย (พ.ศ.)':      sim_year + 543,
                        'จำนวนพนักงาน':      len(df_orig) + len(repl_salaries),
                        'เงินเพิ่มรายปี':     annual_adj,
                        'เงินเดือนรวมรายปี': total_salary})
    return pd.DataFrame(records)


# --- SIDEBAR ---
st.sidebar.header("⚙️ การตั้งค่าการวิเคราะห์")

selected_grp_label = st.sidebar.selectbox(
    "เลือกกลุ่มบุคลากรหลัก",
    options=list(GRP_MAP.values())
)
selected_grp_id = int(selected_grp_label.split(":")[0])

hiring_type = st.sidebar.selectbox(
    "เลือกแหล่งงบประมาณจ้าง",
    options=["ทั้งหมด", "เงินอุดหนุนรัฐบาล", "เงินรายได้ส่วนงาน"]
)

st.sidebar.divider()
st.sidebar.subheader("📍 รายตำแหน่ง (Tab 1)")

if selected_grp_id == 0:
    selected_pos_id = None
    pos_info = None
    st.sidebar.info("เลือกกลุ่ม 1–4 เพื่อดูการวิเคราะห์รายตำแหน่ง")
else:
    df_grp_filtered = df_new_table[df_new_table['GRP_ID'] == selected_grp_id]
    pos_options = [
        f"{int(row['POS_ID'])}: {row['Type']} ({row['Deg_Pos']})"
        for _, row in df_grp_filtered[['POS_ID', 'Type', 'Deg_Pos']]
            .drop_duplicates().sort_values('POS_ID').iterrows()
    ]
    if pos_options:
        selected_pos_label = st.sidebar.selectbox("เลือกตำแหน่งย่อย (POS_ID)", options=pos_options)
        selected_pos_id = int(selected_pos_label.split(":")[0])
        pos_info = df_new_table[df_new_table['POS_ID'] == selected_pos_id].iloc[0]
    else:
        selected_pos_id = None
        pos_info = None
        st.sidebar.warning("ไม่พบข้อมูลตำแหน่งในกลุ่มนี้")

st.sidebar.divider()
st.sidebar.subheader("🔧 พารามิเตอร์ Tapering (ใช้ร่วมกัน)")
s_max_pct = st.sidebar.slider("จุดตัดชายธง (% ของช่วงเงินเดิม)", 0, 120, 100)
gamma = st.sidebar.slider("ความโค้ง (Gamma - γ)", 0.1, 5.0, 1.0, 0.1)

st.sidebar.divider()
st.sidebar.subheader("🏛️ ภาพรวม (Tab 2)")
faculty_options = sorted(df_salary_all['สังกัดคณะ'].dropna().unique().tolist())
selected_faculties = st.sidebar.multiselect(
    "เลือกสังกัดคณะ",
    options=faculty_options,
    default=faculty_options,
    placeholder="เลือกคณะ/หน่วยงาน..."
)
if not selected_faculties:
    selected_faculties = faculty_options

st.sidebar.divider()
st.sidebar.subheader("📈 การพยากรณ์งบประมาณ")
annual_raise_pct = st.sidebar.slider("อัตราเพิ่มเงินเดือนรายปี (%)", 0.0, 10.0, 4.0, 0.5)
projection_years = st.sidebar.slider("จำนวนปีที่พยากรณ์", 1, 20, 10)


# --- TABS ---
tab1, tab2 = st.tabs(["📍 วิเคราะห์รายตำแหน่ง (POS_ID)", "📊 วิเคราะห์ภาพรวม (GRP_ID)"])


# ====== TAB 1: budget_posid ======
with tab1:
    if selected_grp_id == 0:
        st.warning("กรุณาเลือกกลุ่มบุคลากร (1–4) จาก Sidebar เพื่อดูการวิเคราะห์รายตำแหน่ง")
    elif pos_info is None:
        st.warning("ไม่พบข้อมูลตำแหน่งในกลุ่มนี้")
    else:
        b_old = float(pos_info['Min_Old'])
        b_new = float(pos_info['Min_New'])
        m_old = float(pos_info['Max_Old'])
        m_new = float(pos_info['Max_New'])
        s_max = b_old + (s_max_pct / 100) * (m_old - b_old)
        if s_max <= b_new:
            s_max = b_new + 1

        st.title(f"📊 วิเคราะห์งบประมาณ: {pos_info['Type']}")
        st.subheader(f"กลุ่ม: {GRP_MAP[selected_grp_id]} | แหล่งเงิน: {hiring_type}")

        col_info1, col_info2, col_info3 = st.columns(3)
        col_info1.info(f"**ฐานเงินเดือนเดิม:**\n\n{b_old:,.0f} – {m_old:,.0f}")
        col_info2.success(f"**ฐานเงินเดือนใหม่:**\n\n{b_new:,.0f} – {m_new:,.0f}")
        col_info3.warning(f"**จุดตัดเยียวยา ({s_max_pct}%):**\n\n{s_max:,.0f} บาท")

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

        s0_range = np.linspace(b_new, m_new, 1000)
        adj_graph = [calculate_new_salary(x, b_old, b_new, s_max, m_new, gamma) for x in s0_range]

        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=df_target['เงินเดือน'], name="พนักงาน", nbinsx=40,
            marker_color='rgba(150,150,150,0.3)', yaxis='y2'
        ))
        fig.add_trace(go.Scatter(
            x=s0_range, y=adj_graph, name="เงินชดเชย",
            fill='tozeroy', line=dict(color='#0068c9', width=4)
        ))
        fig.update_layout(
            xaxis=dict(title="เงินเดือนเดิม (บาท)", range=[b_new - 5000, m_new + 5000]),
            yaxis=dict(title="เงินเพิ่ม (บาท)", side="left"),
            yaxis2=dict(title="จำนวนคน", overlaying="y", side="right", showgrid=False),
            template="plotly_white", hovermode="x unified", height=500
        )
        st.plotly_chart(fig, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("💰 สรุปงบประมาณ")
            st.metric("งบประมาณรวม/เดือน", f"{total_monthly:,.0f} บาท", delta=f"{len(df_target)} คน")
            df_guarantee = df_target[df_target['เงินเดือน'] < b_new]
            df_max_hit   = df_target[(df_target['เงินเดือน'] + df_target['final_adj']) >= m_new]
            st.write(f"- ปรับเข้าสู่ฐานใหม่ ({len(df_guarantee)} คน): **{df_guarantee['final_adj'].sum():,.0f}** บาท")
            st.write(f"- พนักงานที่เงินเดือนแตะเพดานใหม่: **{len(df_max_hit)}** คน")
        with c2:
            st.subheader("👤 ทดลองคำนวณ")
            test_sal = st.number_input("เงินเดือนปัจจุบัน:", value=float(b_new))
            res_adj  = ceil_to_10(calculate_new_salary(test_sal, b_old, b_new, s_max, m_new, gamma))
            st.metric("เงินเดือนใหม่", f"{test_sal + res_adj:,.0f} บาท", delta=f"เพิ่ม {res_adj:,.0f}")


# ====== TAB 2: budget_grpid ======
with tab2:
    if selected_grp_id == 0:
        df_grp_emp = df_salary_all.copy()
    else:
        df_grp_emp = df_salary_all[df_salary_all['GRP_ID'] == selected_grp_id].copy()

    if "รัฐบาล" in hiring_type:
        df_grp_emp = df_grp_emp[df_grp_emp['ประเภทบุคลากร'].str.contains('รัฐบาล', na=False)]
    elif "รายได้" in hiring_type:
        df_grp_emp = df_grp_emp[df_grp_emp['ประเภทบุคลากร'].str.contains('รายได้', na=False)]

    if len(selected_faculties) < len(faculty_options):
        df_grp_emp = df_grp_emp[df_grp_emp['สังกัดคณะ'].isin(selected_faculties)]

    df_grp_emp['final_adj'] = df_grp_emp.apply(
        lambda row: calculate_adjustment(row, df_new_table, s_max_pct, gamma), axis=1
    )

    df_pos_info = df_new_table[['POS_ID', 'Type', 'Deg_Pos', 'GRP_ID']].drop_duplicates()
    df_grp_emp  = df_grp_emp.merge(df_pos_info, on=['POS_ID', 'GRP_ID'], how='left')

    total_monthly = df_grp_emp['final_adj'].sum()

    st.title(f"📊 วิเคราะห์งบประมาณ: {GRP_MAP[selected_grp_id].split(': ')[1]}")
    st.subheader(f"แหล่งงบประมาณ: {hiring_type}")

    c1, c2, c3 = st.columns(3)
    c1.metric("พนักงานที่เข้าเงื่อนไข", f"{len(df_grp_emp):,.0f} คน")
    c2.metric("งบประมาณรวม (รายเดือน)", f"{total_monthly:,.0f} บาท",
              delta=f"รายปี: {total_monthly * 12:,.0f} บาท", delta_color="normal")
    c3.metric("เฉลี่ยเงินเพิ่มต่อคน/เดือน",
              f"{(total_monthly / len(df_grp_emp) if len(df_grp_emp) > 0 else 0):,.0f} บาท")

    st.divider()

    if selected_grp_id == 0:
        st.subheader("📋 สรุปงบประมาณแยกตามกลุ่มบุคลากร (รายปี)")
        sg = df_grp_emp.groupby('GRP_ID').agg({'final_adj': ['count', 'sum']}).reset_index()
        sg.columns = ['GRP_ID', 'จำนวนคน', 'งบรวม/เดือน']
        sg['งบรวม/ปี'] = sg['งบรวม/เดือน'] * 12
        sg['ชื่อกลุ่ม'] = sg['GRP_ID'].map(lambda x: GRP_MAP.get(x, "อื่นๆ"))
        st.table(sg[['ชื่อกลุ่ม', 'จำนวนคน', 'งบรวม/เดือน', 'งบรวม/ปี']].style.format({
            'งบรวม/เดือน': '{:,.0f}', 'งบรวม/ปี': '{:,.0f}'
        }))
    else:
        st.subheader("📋 รายละเอียดงบประมาณแยกตามตำแหน่ง (รายปี)")
        sp = df_grp_emp.groupby(['Type', 'Deg_Pos']).agg({'final_adj': ['count', 'sum']}).reset_index()
        sp.columns = ['ตำแหน่ง', 'ระดับ', 'จำนวนคน', 'งบรวม/เดือน']
        sp['งบรวม/ปี'] = sp['งบรวม/เดือน'] * 12
        st.dataframe(sp.style.format({'งบรวม/เดือน': '{:,.0f}', 'งบรวม/ปี': '{:,.0f}'}),
                     use_container_width=True)

    st.divider()

    if selected_grp_id == 0:
        st.subheader("📋 สรุปงบประมาณแยกตามกลุ่มบุคลากร (GRP_ID)")
        sg2 = df_grp_emp.groupby('GRP_ID').agg({'final_adj': ['count', 'sum', 'mean']}).reset_index()
        sg2.columns = ['GRP_ID', 'จำนวนคน', 'งบประมาณรวม', 'เฉลี่ยต่อคน']
        sg2['ชื่อกลุ่ม'] = sg2['GRP_ID'].map(lambda x: GRP_MAP.get(x, "อื่นๆ"))
        st.table(sg2[['ชื่อกลุ่ม', 'จำนวนคน', 'งบประมาณรวม', 'เฉลี่ยต่อคน']].style.format({
            'งบประมาณรวม': '{:,.0f}', 'เฉลี่ยต่อคน': '{:,.0f}'
        }))
    else:
        st.subheader("📋 รายละเอียดแยกตามตำแหน่งในกลุ่ม")
        sp2 = df_grp_emp.groupby(['Type', 'Deg_Pos']).agg({'final_adj': ['count', 'sum', 'mean']}).reset_index()
        sp2.columns = ['ตำแหน่ง', 'ระดับ', 'จำนวนคน', 'งบรวม', 'เฉลี่ย/คน']
        st.dataframe(sp2.style.format({'งบรวม': '{:,.0f}', 'เฉลี่ย/คน': '{:,.0f}'}),
                     use_container_width=True)

    st.divider()
    st.subheader("📊 การกระจายตัวของเงินเพิ่ม")
    if not df_grp_emp.empty:
        x_axis = 'Type' if selected_grp_id != 0 else 'GRP_ID'
        fig2 = go.Figure()
        fig2.add_trace(go.Box(
            x=df_grp_emp[x_axis].map(lambda x: GRP_MAP.get(x, str(x)) if x_axis == 'GRP_ID' else x),
            y=df_grp_emp['final_adj'],
            marker_color='#0068c9',
            boxpoints='outliers'
        ))
        fig2.update_layout(xaxis_title="กลุ่ม/ตำแหน่ง", yaxis_title="เงินเพิ่ม (บาท)",
                           template="plotly_white", height=500)
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.subheader("📈 การพยากรณ์งบประมาณในอนาคต")
    if not df_grp_emp.empty:
        proj_df    = project_budget(df_grp_emp, df_new_table, s_max_pct, gamma,
                                    annual_raise_pct, projection_years)
        year0_adj   = proj_df['เงินเพิ่มรายปี'].iloc[0]
        year0_total = proj_df['เงินเดือนรวมรายปี'].iloc[0]

        fig_proj = go.Figure()
        fig_proj.add_trace(go.Scatter(
            x=proj_df['ปีไทย (พ.ศ.)'], y=proj_df['เงินเพิ่มรายปี'],
            mode='lines+markers', name='เงินเพิ่มรายปี',
            yaxis='y1', line=dict(color='#0068c9', width=3), marker=dict(size=7),
            hovertemplate='%{x}: %{y:,.0f} บาท<extra>เงินเพิ่ม</extra>'
        ))
        fig_proj.add_trace(go.Scatter(
            x=proj_df['ปีไทย (พ.ศ.)'], y=proj_df['เงินเดือนรวมรายปี'],
            mode='lines+markers', name='เงินเดือนรวมรายปี',
            yaxis='y2', line=dict(color='#ff8c00', width=3, dash='dot'), marker=dict(size=7),
            hovertemplate='%{x}: %{y:,.0f} บาท<extra>เงินเดือนรวม</extra>'
        ))
        fig_proj.update_layout(
            xaxis_title='ปีงบประมาณ (พ.ศ.)',
            yaxis=dict(title=dict(text='เงินเพิ่มรายปี (บาท)', font=dict(color='#0068c9'))),
            yaxis2=dict(title=dict(text='เงินเดือนรวมรายปี (บาท)', font=dict(color='#ff8c00')),
                        overlaying='y', side='right'),
            template='plotly_white', height=450, hovermode='x unified',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
        )
        st.plotly_chart(fig_proj, use_container_width=True)

        st.subheader("📋 ตารางสรุปการพยากรณ์งบประมาณ")
        tbl = proj_df.copy()
        tbl['Δ เงินเพิ่ม']    = tbl['เงินเพิ่มรายปี']    - year0_adj
        tbl['Δ เงินเดือนรวม'] = tbl['เงินเดือนรวมรายปี'] - year0_total
        st.dataframe(
            tbl[['ปีไทย (พ.ศ.)', 'จำนวนพนักงาน',
                 'เงินเพิ่มรายปี', 'Δ เงินเพิ่ม',
                 'เงินเดือนรวมรายปี', 'Δ เงินเดือนรวม']]
            .style.format({
                'เงินเพิ่มรายปี':     '{:,.0f}',
                'Δ เงินเพิ่ม':        '{:+,.0f}',
                'เงินเดือนรวมรายปี': '{:,.0f}',
                'Δ เงินเดือนรวม':    '{:+,.0f}',
            }),
            use_container_width=True, hide_index=True
        )
