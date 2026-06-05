import io
import math
import os
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

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

# --- 3. CONSTANTS & REPLACEMENT LOOKUP ---
CURRENT_YEAR = date.today().year

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

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")


def ss_monthly_ceiling(year_ce: int) -> float:
    if year_ce <= 2028:
        return 875.0
    if year_ce <= 2031:
        return 1000.0
    return 1150.0


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


def _fund_totals_for_year(salaries_arr: np.ndarray, n_emp: int,
                           year_ce: int, ss_rate: float, pf_rate: float, bm_rate: float) -> dict:
    ceiling = ss_monthly_ceiling(year_ce)
    ss_annual = float(np.minimum(salaries_arr * ss_rate / 100.0, ceiling).sum()) * 12.0
    pf_annual = float((salaries_arr * pf_rate / 100.0).sum()) * 12.0
    wf_annual = n_emp * 10_000.0
    bm_annual = float((salaries_arr * bm_rate / 100.0).sum()) * 12.0
    return {
        'เงินสมทบประกันสังคมรายปี':    ss_annual,
        'เงินสมทบสำรองเลี้ยงชีพรายปี': pf_annual,
        'เงินสมทบสวัสดิการรายปี':       wf_annual,
        'เงินสมทบบูรพามั่นคงรายปี':     bm_annual,
    }


def project_budget(df_grp_emp, df_ref, pct_val, gamma_val,
                   annual_raise_pct, projection_years,
                   ss_rate, pf_rate, bm_rate):
    adj0 = df_grp_emp['final_adj'].to_numpy(float)
    sal0 = df_grp_emp['เงินเดือน'].to_numpy(float)
    new_sal0 = sal0 + adj0

    year0_adj   = float(adj0.sum()) * 12.0
    year0_total = float(new_sal0.sum()) * 12.0
    year0_funds = _fund_totals_for_year(new_sal0, len(df_grp_emp), CURRENT_YEAR,
                                         ss_rate, pf_rate, bm_rate)

    df_orig = df_grp_emp[['เงินเดือน', 'POS_ID', 'GRP_ID']].copy()
    df_orig['ret_year_ce'] = df_grp_emp['วันที่เกษียณอายุ'].dt.year - 543

    repl_salaries = np.array([], dtype=float)
    raise_factor  = 1.0 + annual_raise_pct / 100.0

    records = [{
        'ปีไทย (พ.ศ.)':       CURRENT_YEAR + 543,
        'จำนวนพนักงาน':       len(df_grp_emp),
        'เงินเพิ่มรายปี':      year0_adj,
        'เงินเดือนรวมรายปี':  year0_total,
        **year0_funds,
    }]

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

        adj_arr      = _calc_adj_vectorized(df_orig, df_ref, pct_val, gamma_val)
        annual_adj   = float(np.nansum(adj_arr)) * 12.0
        emp_salaries = df_orig['เงินเดือน'].to_numpy(float) + np.nansum(adj_arr) / max(len(df_orig), 1)

        # combine actual employees and replacements for fund calculations
        all_salaries = np.concatenate([
            df_orig['เงินเดือน'].to_numpy(float),
            repl_salaries,
        ])
        n_total = len(all_salaries)
        total_salary = float(all_salaries.sum()) * 12.0

        funds = _fund_totals_for_year(all_salaries, n_total, sim_year, ss_rate, pf_rate, bm_rate)

        records.append({
            'ปีไทย (พ.ศ.)':       sim_year + 543,
            'จำนวนพนักงาน':       n_total,
            'เงินเพิ่มรายปี':      annual_adj,
            'เงินเดือนรวมรายปี':  total_salary,
            **funds,
        })

    return pd.DataFrame(records)


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
s_max_pct = st.sidebar.slider("จุดตัดชายธง (% ของ Max_Old แต่ละตำแหน่ง)", 0, 120, 100)
gamma = st.sidebar.slider("ความโค้ง (Gamma - γ)", 0.1, 5.0, 1.0, 0.1)

st.sidebar.divider()
st.sidebar.subheader("📈 การพยากรณ์งบประมาณ")
annual_raise_pct = st.sidebar.slider("อัตราเพิ่มเงินเดือนรายปี (%)", 0.0, 10.0, 4.0, 0.5)
projection_years = st.sidebar.slider("จำนวนปีที่พยากรณ์", 1, 20, 10)

st.sidebar.divider()
st.sidebar.subheader("💰 งบประมาณเพิ่มเติม")

ss_include = st.sidebar.checkbox("รวมเงินสมทบประกันสังคม", value=True)
ss_rate = st.sidebar.number_input(
    "อัตราประกันสังคม (%)", min_value=0.0, max_value=15.0,
    value=5.0, step=0.5, disabled=not ss_include,
)

pf_include = st.sidebar.checkbox("รวมเงินสมทบกองทุนสำรองเลี้ยงชีพ", value=True)
pf_rate = st.sidebar.number_input(
    "อัตรากองทุนสำรองเลี้ยงชีพ (%)", min_value=0.0, max_value=15.0,
    value=5.0, step=0.5, disabled=not pf_include,
)

wf_include = st.sidebar.checkbox("รวมเงินสมทบกองทุนสวัสดิการ (10,000 บาท/คน/ปี)", value=True)

bm_include = st.sidebar.checkbox("รวมเงินสมทบกองทุนบูรพามั่นคง", value=True)
bm_rate = st.sidebar.number_input(
    "อัตรากองทุนบูรพามั่นคง (%)", min_value=0.0, max_value=5.0,
    value=0.5, step=0.1, disabled=not bm_include,
)

st.sidebar.divider()
show_fund_graphs = st.sidebar.checkbox("แสดงกราฟงบประมาณเพิ่มเติม", value=False)


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
df_grp_emp = df_grp_emp.merge(df_pos_info, on=['POS_ID', 'GRP_ID'], how='left')

total_monthly = df_grp_emp['final_adj'].sum()

# --- Year-0 additional fund calculations ---
new_salary_arr = (df_grp_emp['เงินเดือน'] + df_grp_emp['final_adj']).to_numpy(float)
n0 = len(df_grp_emp)
ceiling0 = ss_monthly_ceiling(CURRENT_YEAR)
year0_ss = float(np.minimum(new_salary_arr * ss_rate / 100.0, ceiling0).sum()) * 12.0
year0_pf = float((new_salary_arr * pf_rate / 100.0).sum()) * 12.0
year0_wf = n0 * 10_000.0
year0_bm = float((new_salary_arr * bm_rate / 100.0).sum()) * 12.0

year0_salary_total = float(new_salary_arr.sum()) * 12.0
year0_grand_total = (
    year0_salary_total
    + (year0_ss if ss_include else 0.0)
    + (year0_pf if pf_include else 0.0)
    + (year0_wf if wf_include else 0.0)
    + (year0_bm if bm_include else 0.0)
)

# --- 7. DISPLAY: METRICS ---
st.title(f"📊 วิเคราะห์งบประมาณ: {grp_options[selected_grp_id].split(': ')[1]}")
st.subheader(f"แหล่งงบประมาณ: {hiring_type}")

c1, c2, c3 = st.columns(3)
c1.metric("พนักงานที่เข้าเงื่อนไข", f"{n0:,.0f} คน")
c2.metric("งบประมาณรวม (รายเดือน)", f"{total_monthly:,.0f} บาท",
          delta=f"รายปี: {total_monthly * 12:,.0f} บาท", delta_color="normal")
c3.metric("เฉลี่ยเงินเพิ่มต่อคน/เดือน",
          f"{(total_monthly / n0 if n0 > 0 else 0):,.0f} บาท")

# --- 8. SUMMARY TABLE BY GROUP/POSITION ---
st.divider()

if selected_grp_id == 0:
    st.subheader("📋 สรุปงบประมาณแยกตามกลุ่มบุคลากร (รายปี)")
    summary_grp = df_grp_emp.groupby('GRP_ID').agg({'final_adj': ['count', 'sum']}).reset_index()
    summary_grp.columns = ['GRP_ID', 'จำนวนคน', 'งบรวม/เดือน']
    summary_grp['งบรวม/ปี'] = summary_grp['งบรวม/เดือน'] * 12
    summary_grp['ชื่อกลุ่ม'] = summary_grp['GRP_ID'].map(lambda x: grp_options.get(x, "อื่นๆ"))
    st.table(summary_grp[['ชื่อกลุ่ม', 'จำนวนคน', 'งบรวม/เดือน', 'งบรวม/ปี']].style.format({
        'งบรวม/เดือน': '{:,.0f}',
        'งบรวม/ปี': '{:,.0f}'
    }))
else:
    st.subheader("📋 รายละเอียดงบประมาณแยกตามตำแหน่ง (รายปี)")
    summary_pos = df_grp_emp.groupby(['Type', 'Deg_Pos']).agg({'final_adj': ['count', 'sum']}).reset_index()
    summary_pos.columns = ['ตำแหน่ง', 'ระดับ', 'จำนวนคน', 'งบรวม/เดือน']
    summary_pos['งบรวม/ปี'] = summary_pos['งบรวม/เดือน'] * 12
    st.dataframe(summary_pos.style.format({
        'งบรวม/เดือน': '{:,.0f}',
        'งบรวม/ปี': '{:,.0f}'
    }), use_container_width=True)

st.divider()
if selected_grp_id == 0:
    st.subheader("📋 สรุปงบประมาณแยกตามกลุ่มบุคลากร (GRP_ID)")
    summary_grp2 = df_grp_emp.groupby('GRP_ID').agg({'final_adj': ['count', 'sum', 'mean']}).reset_index()
    summary_grp2.columns = ['GRP_ID', 'จำนวนคน', 'งบประมาณรวม', 'เฉลี่ยต่อคน']
    summary_grp2['ชื่อกลุ่ม'] = summary_grp2['GRP_ID'].map(lambda x: grp_options.get(x, "อื่นๆ"))
    st.table(summary_grp2[['ชื่อกลุ่ม', 'จำนวนคน', 'งบประมาณรวม', 'เฉลี่ยต่อคน']].style.format(
        {'งบประมาณรวม': '{:,.0f}', 'เฉลี่ยต่อคน': '{:,.0f}'}
    ))
else:
    st.subheader("📋 รายละเอียดแยกตามตำแหน่งในกลุ่ม")
    summary_pos2 = df_grp_emp.groupby(['Type', 'Deg_Pos']).agg({'final_adj': ['count', 'sum', 'mean']}).reset_index()
    summary_pos2.columns = ['ตำแหน่ง', 'ระดับ', 'จำนวนคน', 'งบรวม', 'เฉลี่ย/คน']
    st.dataframe(summary_pos2.style.format({'งบรวม': '{:,.0f}', 'เฉลี่ย/คน': '{:,.0f}'}), use_container_width=True)

# --- 9. FUND BREAKDOWN TABLE (Year 0 snapshot) ---
st.divider()
st.subheader("💰 สรุปงบประมาณรวมปีปัจจุบัน (แยกรายกองทุน)")

breakdown_rows = [
    {"รายการ": "เงินเดือน (หลังปรับ)", "รายเดือน (บาท)": year0_salary_total / 12, "รายปี (บาท)": year0_salary_total},
]
if ss_include:
    breakdown_rows.append({"รายการ": "เงินสมทบประกันสังคม", "รายเดือน (บาท)": year0_ss / 12, "รายปี (บาท)": year0_ss})
if pf_include:
    breakdown_rows.append({"รายการ": "เงินสมทบกองทุนสำรองเลี้ยงชีพ", "รายเดือน (บาท)": year0_pf / 12, "รายปี (บาท)": year0_pf})
if wf_include:
    breakdown_rows.append({"รายการ": "เงินสมทบกองทุนสวัสดิการ", "รายเดือน (บาท)": None, "รายปี (บาท)": year0_wf})
if bm_include:
    breakdown_rows.append({"รายการ": "เงินสมทบกองทุนบูรพามั่นคง", "รายเดือน (บาท)": year0_bm / 12, "รายปี (บาท)": year0_bm})
breakdown_rows.append({"รายการ": "รวมทั้งหมด", "รายเดือน (บาท)": None, "รายปี (บาท)": year0_grand_total})

breakdown_df = pd.DataFrame(breakdown_rows)
st.dataframe(
    breakdown_df.style.format({"รายเดือน (บาท)": lambda v: f"{v:,.0f}" if v is not None and not (isinstance(v, float) and math.isnan(v)) else "—",
                                "รายปี (บาท)": '{:,.0f}'}),
    use_container_width=True, hide_index=True,
)

# --- 10. BOX PLOT ---
st.divider()
st.subheader("📊 การกระจายตัวของเงินเพิ่ม")
if not df_grp_emp.empty:
    x_axis = 'Type' if selected_grp_id != 0 else 'GRP_ID'
    fig = go.Figure()
    fig.add_trace(go.Box(
        x=df_grp_emp[x_axis].map(lambda x: grp_options[x] if x_axis == 'GRP_ID' else x),
        y=df_grp_emp['final_adj'],
        marker_color='#0068c9',
        boxpoints='outliers'
    ))
    fig.update_layout(xaxis_title="กลุ่ม/ตำแหน่ง", yaxis_title="เงินเพิ่ม (บาท)",
                      template="plotly_white", height=500)
    st.plotly_chart(fig, use_container_width=True)

# --- 11. BUDGET PROJECTION ---
st.divider()
st.subheader("📈 การพยากรณ์งบประมาณในอนาคต")

if not df_grp_emp.empty:
    proj_df = project_budget(
        df_grp_emp, df_new_table, s_max_pct, gamma,
        annual_raise_pct, projection_years,
        ss_rate if ss_include else 0.0,
        pf_rate if pf_include else 0.0,
        bm_rate if bm_include else 0.0,
    )

    # grand total column (wf always computed; only add if checked)
    proj_df['งบประมาณรวมทั้งหมดรายปี'] = (
        proj_df['เงินเดือนรวมรายปี']
        + proj_df['เงินสมทบประกันสังคมรายปี']
        + proj_df['เงินสมทบสำรองเลี้ยงชีพรายปี']
        + (proj_df['เงินสมทบสวัสดิการรายปี'] if wf_include else 0)
        + proj_df['เงินสมทบบูรพามั่นคงรายปี']
    )

    year0_adj_val   = proj_df['เงินเพิ่มรายปี'].iloc[0]
    year0_total_val = proj_df['เงินเดือนรวมรายปี'].iloc[0]
    year0_grand_val = proj_df['งบประมาณรวมทั้งหมดรายปี'].iloc[0]

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
    fig_proj.add_trace(go.Scatter(
        x=proj_df['ปีไทย (พ.ศ.)'], y=proj_df['งบประมาณรวมทั้งหมดรายปี'],
        mode='lines+markers', name='งบประมาณรวมทั้งหมด',
        yaxis='y2', line=dict(color='#d62728', width=3), marker=dict(size=7),
        hovertemplate='%{x}: %{y:,.0f} บาท<extra>รวมทั้งหมด</extra>'
    ))

    if show_fund_graphs:
        fund_traces = [
            ('เงินสมทบประกันสังคมรายปี',    ss_include,  '#29b09d', 'ประกันสังคม'),
            ('เงินสมทบสำรองเลี้ยงชีพรายปี', pf_include,  '#8b5cf6', 'สำรองเลี้ยงชีพ'),
            ('เงินสมทบสวัสดิการรายปี',       wf_include,  '#ef4444', 'สวัสดิการ'),
            ('เงินสมทบบูรพามั่นคงรายปี',     bm_include,  '#f59e0b', 'บูรพามั่นคง'),
        ]
        for col, included, color, label in fund_traces:
            if included:
                fig_proj.add_trace(go.Scatter(
                    x=proj_df['ปีไทย (พ.ศ.)'], y=proj_df[col],
                    mode='lines+markers', name=label,
                    yaxis='y1', line=dict(color=color, width=2, dash='dash'), marker=dict(size=5),
                    hovertemplate=f'%{{x}}: %{{y:,.0f}} บาท<extra>{label}</extra>'
                ))

    fig_proj.update_layout(
        xaxis_title='ปีงบประมาณ (พ.ศ.)',
        yaxis=dict(title=dict(text='เงินเพิ่มรายปี (บาท)', font=dict(color='#0068c9'))),
        yaxis2=dict(title=dict(text='งบรวมรายปี (บาท)', font=dict(color='#ff8c00')),
                    overlaying='y', side='right'),
        template='plotly_white', height=450, hovermode='x unified',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
    )
    st.plotly_chart(fig_proj, use_container_width=True)

    # --- Projection summary table ---
    st.subheader("📋 ตารางสรุปการพยากรณ์งบประมาณ")
    tbl = proj_df.copy()
    tbl['Δ เงินเพิ่ม']    = tbl['เงินเพิ่มรายปี']           - year0_adj_val
    tbl['Δ เงินเดือนรวม'] = tbl['เงินเดือนรวมรายปี']        - year0_total_val
    tbl['Δ รวมทั้งหมด']   = tbl['งบประมาณรวมทั้งหมดรายปี'] - year0_grand_val

    display_cols = ['ปีไทย (พ.ศ.)', 'จำนวนพนักงาน',
                    'เงินเพิ่มรายปี', 'Δ เงินเพิ่ม',
                    'เงินเดือนรวมรายปี', 'Δ เงินเดือนรวม']
    fmt = {
        'เงินเพิ่มรายปี':     '{:,.0f}',
        'Δ เงินเพิ่ม':        '{:+,.0f}',
        'เงินเดือนรวมรายปี': '{:,.0f}',
        'Δ เงินเดือนรวม':    '{:+,.0f}',
    }
    if ss_include:
        display_cols.append('เงินสมทบประกันสังคมรายปี')
        fmt['เงินสมทบประกันสังคมรายปี'] = '{:,.0f}'
    if pf_include:
        display_cols.append('เงินสมทบสำรองเลี้ยงชีพรายปี')
        fmt['เงินสมทบสำรองเลี้ยงชีพรายปี'] = '{:,.0f}'
    if wf_include:
        display_cols.append('เงินสมทบสวัสดิการรายปี')
        fmt['เงินสมทบสวัสดิการรายปี'] = '{:,.0f}'
    if bm_include:
        display_cols.append('เงินสมทบบูรพามั่นคงรายปี')
        fmt['เงินสมทบบูรพามั่นคงรายปี'] = '{:,.0f}'
    display_cols += ['งบประมาณรวมทั้งหมดรายปี', 'Δ รวมทั้งหมด']
    fmt['งบประมาณรวมทั้งหมดรายปี'] = '{:,.0f}'
    fmt['Δ รวมทั้งหมด'] = '{:+,.0f}'

    st.dataframe(
        tbl[display_cols].style.format(fmt),
        use_container_width=True, hide_index=True
    )

    # --- 12. EXPORT BUTTONS ---
    st.divider()
    st.subheader("⬇ ส่งออกข้อมูล")

    def build_xlsx(proj_tbl: pd.DataFrame, bd_df: pd.DataFrame) -> bytes:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            proj_tbl[display_cols].to_excel(writer, sheet_name='พยากรณ์งบประมาณ', index=False)
            bd_df.to_excel(writer, sheet_name='สรุปงบประมาณปีปัจจุบัน', index=False)
        return buf.getvalue()

    def build_pdf(proj_tbl: pd.DataFrame, bd_df: pd.DataFrame) -> bytes:
        from fpdf import FPDF
        from fpdf.enums import XPos, YPos

        font_regular = os.path.join(FONT_DIR, "Sarabun-Regular.ttf")
        font_bold    = os.path.join(FONT_DIR, "Sarabun-Bold.ttf")

        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_font("Sarabun", style="",  fname=font_regular)
        pdf.add_font("Sarabun", style="B", fname=font_bold)

        def fmt_num(v):
            if v is None or (isinstance(v, float) and math.isnan(v)):
                return "—"
            return f"{v:,.0f}"

        def draw_table(headers: list, rows: list[list], col_widths: list,
                        title: str, font_size: int = 9):
            pdf.add_page()
            pdf.set_font("Sarabun", "B", 13)
            pdf.cell(0, 10, title, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(2)

            # header row
            pdf.set_font("Sarabun", "B", font_size)
            pdf.set_fill_color(52, 120, 198)
            pdf.set_text_color(255, 255, 255)
            for h, w in zip(headers, col_widths):
                pdf.cell(w, 7, str(h), border=1, align="C", fill=True)
            pdf.ln()
            pdf.set_text_color(0, 0, 0)

            pdf.set_font("Sarabun", "", font_size)
            for i, row in enumerate(rows):
                pdf.set_fill_color(240, 245, 255) if i % 2 == 0 else pdf.set_fill_color(255, 255, 255)
                for val, w in zip(row, col_widths):
                    pdf.cell(w, 6, str(val), border=1, fill=True)
                pdf.ln()

        # --- Page 1: breakdown table ---
        bd_headers = list(bd_df.columns)
        bd_rows = []
        for _, r in bd_df.iterrows():
            bd_rows.append([
                r['รายการ'],
                fmt_num(r['รายเดือน (บาท)']),
                fmt_num(r['รายปี (บาท)']),
            ])
        draw_table(bd_headers, bd_rows, [90, 45, 45],
                   f"สรุปงบประมาณรวมปีปัจจุบัน ({CURRENT_YEAR + 543})", font_size=10)

        # --- Page 2+: projection table ---
        proj_disp = proj_tbl[display_cols].copy()
        # shorten column names for PDF
        short_names = {
            'ปีไทย (พ.ศ.)':                  'ปี',
            'จำนวนพนักงาน':                   'จำนวน',
            'เงินเพิ่มรายปี':                 'เงินเพิ่ม/ปี',
            'Δ เงินเพิ่ม':                    'Δ เพิ่ม',
            'เงินเดือนรวมรายปี':              'เงินเดือนรวม/ปี',
            'Δ เงินเดือนรวม':                 'Δ เดือนรวม',
            'เงินสมทบประกันสังคมรายปี':       'ประกัน สังคม',
            'เงินสมทบสำรองเลี้ยงชีพรายปี':   'สำรอง เลี้ยงชีพ',
            'เงินสมทบสวัสดิการรายปี':         'สวัสดิการ',
            'เงินสมทบบูรพามั่นคงรายปี':       'บูรพา มั่นคง',
            'งบประมาณรวมทั้งหมดรายปี':        'รวมทั้งหมด/ปี',
            'Δ รวมทั้งหมด':                   'Δ รวม',
        }
        proj_headers = [short_names.get(c, c) for c in display_cols]
        n_cols = len(display_cols)
        usable_width = 267  # A4 landscape usable mm
        col_w = [18, 14] + [int((usable_width - 32) / (n_cols - 2))] * (n_cols - 2)

        proj_rows = []
        for _, r in proj_disp.iterrows():
            row_vals = []
            for c in display_cols:
                v = r[c]
                if c in ('ปีไทย (พ.ศ.)', 'จำนวนพนักงาน'):
                    row_vals.append(str(int(v)))
                elif c.startswith('Δ'):
                    row_vals.append(f"{v:+,.0f}")
                else:
                    row_vals.append(fmt_num(v))
            proj_rows.append(row_vals)

        draw_table(proj_headers, proj_rows, col_w,
                   "ตารางสรุปการพยากรณ์งบประมาณ", font_size=8)

        return bytes(pdf.output())

    xlsx_bytes = build_xlsx(tbl, breakdown_df)
    pdf_bytes  = build_pdf(tbl, breakdown_df)

    col_xl, col_pdf = st.columns(2)
    with col_xl:
        st.download_button(
            "⬇ ดาวน์โหลด Excel (.xlsx)", xlsx_bytes,
            file_name="budget_forecast.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with col_pdf:
        st.download_button(
            "⬇ ดาวน์โหลด PDF", pdf_bytes,
            file_name="budget_forecast.pdf",
            mime="application/pdf",
        )
