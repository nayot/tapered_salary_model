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

# --- 2. INITIALIZE SESSION STATE ---
if 'snapshots' not in st.session_state:
    st.session_state.snapshots = []

# --- 3. FUNCTIONS ---
def calculate_adj(salary, b_new_val, s_max_val, delta_b_val, gamma_val, max_new_val):
    """Canonical tapered adjustment — identical logic to budget_analysis."""
    salary = np.asarray(salary, dtype=float)
    # Zone 1: below B_new → lift to floor
    adj = np.where(salary < b_new_val, b_new_val - salary, 0.0)
    # Zone 2: taper between B_new and S_max
    denom = s_max_val - b_new_val if (s_max_val - b_new_val) > 0 else 1e-9
    ratio = np.clip(1.0 - (salary - b_new_val) / denom, 0.0, 1.0)
    adj = np.where(
        (salary >= b_new_val) & (salary <= s_max_val),
        delta_b_val * (ratio ** gamma_val),
        adj
    )
    # Zone 3: above S_max → 0 (already handled by initialization)
    # Cap so new salary never exceeds Max_New
    adj = np.minimum(adj, np.maximum(max_new_val - salary, 0.0))
    return np.where(adj < 0, 0.0, adj)


def ceil_to_10(num):
    return math.ceil(num / 10) * 10 if num > 0 else 0


# --- 4. SIDEBAR: PARAMETERS ---
st.sidebar.header("⚙️ การตั้งค่าโมเดล")

b_old   = st.sidebar.number_input("ฐานเดิม (B_old)",    value=31500, step=500)
b_new   = st.sidebar.number_input("ฐานใหม่ (B_new)",    value=35000, step=500)
max_new = st.sidebar.number_input("เพดานใหม่ (Max_New)", value=63410, step=500)
delta_b = b_new - b_old

s_max_min     = int(b_new) + 1
s_max_max     = max(int(max_new), s_max_min + 1)
s_max_default = max(s_max_min, min(int(b_new + 0.8 * (max_new - b_new)), s_max_max))
s_max = st.sidebar.slider(
    "จุดตัดชายธง (S_max)", min_value=s_max_min, max_value=s_max_max, value=s_max_default
)
gamma = st.sidebar.slider("ความโค้ง (Gamma - γ)", min_value=0.1, max_value=5.0, value=1.0, step=0.1)

# --- 5. SNAPSHOT CONTROLS ---
st.sidebar.markdown("---")
st.sidebar.subheader("📸 ระบบเปรียบเทียบ (Snapshots)")

if st.sidebar.button("➕ Capture กราฟปัจจุบัน"):
    snap_name = f"γ={gamma:.1f}, Smax={s_max/1000:.0f}k"
    x_snap = np.linspace(max(0, b_old - 5000), max_new + 5000, 1000)
    y_snap = calculate_adj(x_snap, b_new, s_max, delta_b, gamma, max_new)
    st.session_state.snapshots.append({
        'id': str(uuid.uuid4())[:4],
        'name': snap_name,
        'x': x_snap,
        'y': y_snap,
        'visible': True
    })
    st.sidebar.success(f"บันทึก {snap_name} แล้ว")

if st.session_state.snapshots:
    for i, snap in enumerate(st.session_state.snapshots):
        col_check, col_del = st.sidebar.columns([3, 1])
        snap['visible'] = col_check.checkbox(
            f"แสดง: {snap['name']}", value=snap['visible'], key=f"cap_{i}"
        )
        if col_del.button("🗑️", key=f"del_{i}"):
            st.session_state.snapshots.pop(i)
            st.rerun()
    if st.sidebar.button("🗑️ ล้างทั้งหมด"):
        st.session_state.snapshots = []
        st.rerun()

# --- 6. COMPUTE CURRENT CURVE ---
x_range     = np.linspace(max(0, b_old - 5000), max_new + 5000, 2000)
current_adj = calculate_adj(x_range, b_new, s_max, delta_b, gamma, max_new)

# --- 7. MAIN DISPLAY: GRAPH ---
st.title("📊 ระบบจำลองการปรับเงินเดือนชดเชย (Flexible Tapering)")

fig = go.Figure()

for snap in st.session_state.snapshots:
    if snap['visible']:
        fig.add_trace(go.Scatter(
            x=snap['x'], y=snap['y'],
            name=f"อ้างอิง: {snap['name']}",
            line=dict(dash='dash', width=2),
            opacity=0.6
        ))

fig.add_trace(go.Scatter(
    x=x_range, y=current_adj,
    name="โมเดลปัจจุบัน",
    fill='tozeroy',
    line=dict(color='#1f77b4', width=4)
))

fig.add_vline(
    x=b_new, line_dash="dot", line_color="green",
    annotation_text=f"B_new={b_new:,.0f}", annotation_position="top right"
)
fig.add_vline(
    x=s_max, line_dash="dot", line_color="red",
    annotation_text=f"S_max={s_max:,.0f}", annotation_position="top left"
)

fig.update_layout(
    xaxis_title="เงินเดือนเดิม (บาท)",
    yaxis_title="เงินชดเชยส่วนต่าง (บาท)",
    template="plotly_white",
    legend=dict(yanchor="top", y=0.98, xanchor="right", x=0.98, bgcolor="rgba(255,255,255,0.5)"),
    hovermode="x unified"
)
st.plotly_chart(fig, use_container_width=True)

z1, z2, z3 = st.columns(3)
z1.info(f"**โซน 1** (< {b_new:,.0f} บาท)\nปรับขึ้นสู่ฐานใหม่เต็มจำนวน")
z2.success(f"**โซน 2** ({b_new:,.0f} → {s_max:,.0f} บาท)\nTaper · δB = {delta_b:,.0f} · γ = {gamma}")
z3.warning(f"**โซน 3** (> {s_max:,.0f} บาท)\nไม่ปรับ | เพดาน Max_New = {max_new:,.0f}")

# --- 8. INDIVIDUAL SIMULATOR ---
st.divider()
st.subheader("👤 เครื่องมือจำลองรายบุคคล (Individual Simulator)")

input_col, _ = st.columns([1, 2])
with input_col:
    test_sal = st.number_input("ระบุเงินเดือนปัจจุบัน (บาท):", value=float(b_new), step=1000.0)

raw_adj_val = float(calculate_adj(test_sal, b_new, s_max, delta_b, gamma, max_new))
final_adj   = ceil_to_10(raw_adj_val)
new_salary  = test_sal + final_adj

m1, m2, m3 = st.columns(3)
m1.metric("เงินเดือนเดิม",             f"{test_sal:,.0f} บาท")
m2.metric("เงินชดเชย (ปัดเป็น 10)",   f"{final_adj:,.0f} บาท", delta=f"{final_adj:,.0f}")
m3.metric("เงินเดือนใหม่สุทธิ",        f"{new_salary:,.0f} บาท")

if raw_adj_val > 0:
    st.caption(
        f"💡 คำนวณจริงได้ {raw_adj_val:,.2f} บาท → ปัดเศษตามเงื่อนไขเป็น {final_adj:,.0f} บาท"
    )
