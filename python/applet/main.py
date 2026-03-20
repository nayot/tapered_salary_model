
import streamlit as st
import numpy as np
import plotly.graph_objects as go
import uuid

def main():
    # --- การตั้งค่าหน้าจอ ---
    st.set_page_config(page_title="Salary Tapering Model", layout="wide")
    st.title("🛩️ Interactive Salary Tapering Model (ชายธง)")
    st.write("ปรับแต่งตัวแปรเพื่อจำลองการเลื่อนเงินเดือนและเปรียบเทียบ Scenario")
    
    # --- Initialize Session State สำหรับเก็บ Snapshots ---
    if 'snapshots' not in st.session_state:
        st.session_state.snapshots = [] # เก็บ List ของ dict {'id':..., 'name':..., 'x':..., 'y':..., 'gamma':...}
    
    # --- ส่วนของ Sidebar (Control Panel) ---
    st.sidebar.header("⚙️ ปรับแต่งตัวแปร (Parameters)")
    
    b_old = st.sidebar.number_input("ฐานเงินเดือนเดิม (B_old)", value=15000, step=500)
    b_new = st.sidebar.number_input("ฐานเงินเดือนใหม่ (B_new)", value=18000, step=500)
    s_max = st.sidebar.slider("จุดตัดชายธง (S_max)", min_value=int(b_new), max_value=50000, value=30000)
    gamma = st.sidebar.slider("ค่าความโค้ง (Gamma - γ)", min_value=0.1, max_value=5.0, value=1.0, step=0.1)
    
    delta_b = b_new - b_old
    
    # --- การคำนวณกราฟปัจจุบัน ---
    s0 = np.linspace(b_old, s_max + 5000, 500)
    
    def calculate_adj(salary, b_old_val, s_max_val, delta_b_val, gamma_val):
        # สูตร Model 2 (รับ parameter เพื่อใช้คำนวณ snapshot ได้)
        ratio = np.clip(1 - (salary - b_old_val) / (s_max_val - b_old_val), 0, 1)
        return delta_b_val * (ratio ** gamma_val)
    
    adj_values = calculate_adj(s0, b_old, s_max, delta_b, gamma)
    
    # --- ส่วนจัดการ Snapshots (Capture & Compare) ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("📸 จัดการเส้นเปรียบเทียบ (Snapshots)")
    
    # 1. ปุ่ม Capture กราฟปัจจุบัน
    if st.sidebar.button("➕ Capture current graph", help="บันทึกกราฟเส้นปัจจุบันไว้เพื่อเปรียบเทียบ"):
        snapshot_id = str(uuid.uuid4())[:8] # สร้าง ID สั้นๆ
        # เลือกชื่ออัตโนมัติตามค่า gamma หรือตั้งชื่อเองได้ในภายหลัง
        snapshot_name = st.sidebar.text_input(f"ชื่อ Snapshot ({snapshot_id}):", value=f"Gamma={gamma:.1f}, Smax={s_max}")
        
        # เก็บข้อมูลที่จำเป็นลงใน session_state
        st.session_state.snapshots.append({
            'id': snapshot_id,
            'name': snapshot_name,
            'x': s0, # เก็บ x และ y เพื่อใช้วาดกราฟได้ทันที
            'y': adj_values,
            'gamma': gamma,
            'visible': True # ตั้งค่าเริ่มต้นให้แสดงผล
        })
        st.success(f"Capture กราฟ '{snapshot_name}' เรียบร้อย!")
    
    # 2. ตารางแสดงและจัดการ Snapshots
    if st.session_state.snapshots:
        st.sidebar.write("### เส้นที่บันทึกไว้")
        
        # ใช้ st.data_editor เพื่อให้ผู้บริหารเลือกเปิด/ปิด หรือลบเส้นได้
        snapshots_df_display = []
        for i, snap in enumerate(st.session_state.snapshots):
            snapshots_df_display.append({
                'Index': i,
                'ชื่อเส้น': snap['name'],
                'แสดงผล': snap['visible'],
                'ลบ': False
            })
        
        edited_df = st.sidebar.data_editor(
            snapshots_df_display, 
            key="snapshot_editor",
            hide_index=True,
            column_config={
                'Index': None, # ซ่อนคอลัมน์ Index
                'ลบ': st.column_config.CheckboxColumn(required=True)
            }
        )
    
        # ปรับปรุงสถานะ visible และลบตามข้อมูลที่แก้ไขใน data_editor
        indices_to_delete = []
        for row in edited_df:
            idx = row['Index']
            st.session_state.snapshots[idx]['visible'] = row['แสดงผล']
            if row['ลบ']:
                indices_to_delete.append(idx)
        
        # ลบ snapshot (เรียงลำดับจากหลังมาหน้าเพื่อไม่ให้ index เพี้ยน)
        if indices_to_delete:
            for idx in sorted(indices_to_delete, reverse=True):
                del st.session_state.snapshots[idx]
            st.sidebar.warning("ลบ Snapshot ที่เลือกเรียบร้อย!")
            st.rerun() # สั่ง Re-run เพื่ออัปเดตกราฟทันที
    
    # 3. ปุ่มลบ Snapshots ทั้งหมด
    if st.sidebar.button("🗑️ ลบทั้งหมด", key="clear_all"):
        st.session_state.snapshots = []
        st.sidebar.warning("ลบ Snapshots ทั้งหมดเรียบร้อย!")
        st.rerun()
    
    # --- สร้างกราฟ Interactive ด้วย Plotly ---
    fig = go.Figure()
    
    # 1. วาดเส้น Snapshots (เส้นเปรียบเทียบ) ก่อนเพื่อให้เส้นปัจจุบันอยู่ด้านบน
    colors = ['#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b'] # List สีสำหรับเส้นเปรียบเทียบ
    color_idx = 0
    for snap in st.session_state.snapshots:
        if snap['visible']:
            color = colors[color_idx % len(colors)]
            fig.add_trace(go.Scatter(
                x=snap['x'], y=snap['y'],
                mode='lines',
                line=dict(color=color, width=2, dash='dash'), # เส้นประ
                name=f"เปรียบเทียบ: {snap['name']}"
            ))
            color_idx += 1
    
    # 2. วาดเส้นกราฟปัจจุบัน (เส้นหลัก)
    fig.add_trace(go.Scatter(
        x=s0, y=adj_values,
        mode='lines',
        line=dict(color='#1f77b4', width=4),
        name='กราฟปัจจุบัน',
        fill='tozeroy', # ระบายสีใต้กราฟเฉพาะเส้นปัจจุบัน
        fillcolor='rgba(31, 119, 180, 0.2)' # สีโปร่งแสง
    ))
    
    fig.update_layout(
        title=f"กราฟเปรียบเทียบการปรับเงินเดือน (ปัจจุบัน γ = {gamma})",
        xaxis_title="เงินเดือนปัจจุบัน (บาท)",
        yaxis_title="เงินที่ได้รับการปรับเพิ่ม (บาท)",
        hovermode="x unified",
        template="plotly_white",
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01) # ปรับตำแหน่ง Legend
    )
    
    # แสดงกราฟ
    st.plotly_chart(fig, use_container_width=True)
    
    # --- ส่วนสรุปผล (Insights) ---
    # ... (ส่วนนี้คงเดิมจาก Code แก้ไขล่าสุด) ...
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"**ส่วนต่างแรกบรรจุ:** {delta_b:,.0f} บาท")
    with col2:
        if gamma < 1:
            st.warning("💡 **Scenario:** เน้นรักษาคนเก่า (งบประมาณสูง)")
        elif gamma > 1:
            st.success("💡 **Scenario:** ประหยัดงบประมาณ (เน้นคนบรรจุใหม่)")
        else:
            st.info("💡 **Scenario:** แบบเส้นตรง (สมดุล)")

if __name__ == "__main__":
    main()
