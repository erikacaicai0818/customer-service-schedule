import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import os
import pytz
import calendar

# --- 1. 时区与系统配置 ---
china_tz = pytz.timezone('Asia/Shanghai')

def get_now():
    return datetime.now(china_tz)

st.set_page_config(page_title="客服部全功能智能管理系统", layout="wide", page_icon="⚖️")

# 核心常量
START_DATE = datetime(2026, 3, 1).date()
STAFF = ["郭战勇", "徐远远", "陈鹤舞", "都 娟", "陈君琳", "顾凌海"]
DB_FILE = "duty_records_final_v5.csv"

# 统一工时标准：8.5小时
FIXED_WORK_HOUR = 8.5 

# --- 2. 界面顶部：班次定义 ---
st.title("⚖️ 客服部全功能智能管理系统")

with st.expander("📝 查看班次定义与工时规则", expanded=False):
    st.markdown(f"""
    | 班次名称 | 在司时间 | 居家时间 | 休息时间 | 实际工时 |
    | :--- | :--- | :--- | :--- | :--- |
    | **早班** | 09:00-19:00 | - | 1.5h | **{FIXED_WORK_HOUR:.1}h** |
    | **延迟班** | 10:00-20:00 | - | 1.5h | **{FIXED_WORK_HOUR:.1}h** |
    | **晚值班** | 12:30-19:00 | 20:00-22:00 | 在司已扣 | **{FIXED_WORK_HOUR:.1}h** |
    | **休息** | - | - | - | 0h |
    """)
    st.info("💡 **公平性**：全员实行 6 天一循环滚动。所有人月度/周度应出勤时长基本完全对齐。数据从 2026-03-01 起算。")

# --- 3. 数据处理逻辑 ---
if not os.path.exists(DB_FILE):
    pd.DataFrame(columns=["id", "name", "type", "date", "start_t", "end_t", "hours", "status"]).to_csv(DB_FILE, index=False)

def load_data():
    df = pd.read_csv(DB_FILE)
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df

# --- 4. 核心算法：循环排班 ---
def get_duty_type(name, date_obj):
    if date_obj < START_DATE: return "未开始"
    days_diff = (date_obj - START_DATE).days
    name_idx = STAFF.index(name)
    weekday = date_obj.weekday()
    
    if weekday == 6: # 周日 2 人制
        cycle_week = (days_diff // 7) % 3
        pairs = [(0, 1), (2, 3), (4, 5)] 
        sun_pair = pairs[cycle_week]
        if name_idx == sun_pair[0]: return "早班"
        if name_idx == sun_pair[1]: return "晚值班"
        return "休息"
    else:
        # 周一至周六：每天1人休息 (6天轮转)
        off_idx = (days_diff - (days_diff // 7)) % 6
        if name_idx == off_idx: return "休息"
        
        # 晚班分配
        night_idx = (days_diff) % 6
        if name_idx == night_idx: return "晚值班"
        
        # 延迟班分配
        yesterday_diff = days_diff - 1
        y_night_idx = (yesterday_diff) % 6
        if name_idx == y_night_idx: return "延迟班"
            
        return "早班"

def get_current_status(name, name_idx, duty_type, now_dt):
    now_t = now_dt.time()
    now_d = now_dt.date()
    recs = load_data()
    active = recs[(recs['name']==name) & (recs['date']==now_d) & (recs['status']=="有效")]
    for _, r in active.iterrows():
        st_t = datetime.strptime(str(r['start_t']), "%H:%M:%S").time()
        en_t = datetime.strptime(str(r['end_t']), "%H:%M:%S").time()
        if st_t <= now_t <= en_t: return f"🔴 {r['type']}中", "red"

    if duty_type in ["休息", "未开始"]: return "😴 休息中", "grey"
    if "晚值班" not in duty_type:
        lunch = (time(11,30), time(13,0)) if name_idx % 2 == 0 else (time(13,0), time(14,30))
        if lunch[0] <= now_t <= lunch[1]: return "🍱 午休中", "orange"
    
    if duty_type == "晚值班":
        if time(12,30) <= now_t <= time(19,0): return "🏢 在司值班", "green"
        if time(19,0) <= now_t <= time(20,0): return "🚗 通勤路上", "blue"
        if time(20,0) <= now_t <= time(22,0): return "🏠 居家远程", "green"
    elif duty_type == "延迟班":
        if time(10,0) <= now_t <= time(20,0): return "🏢 在司值班", "green"
    else:
        if time(9,0) <= now_t <= time(19,0): return "🏢 在司值班", "green"
    return "🌙 已下班", "red"

# --- 5. 实时监控展示 ---
now = get_now()
st.subheader(f"⏱️ 实时状态看板 ({now.strftime('%H:%M:%S')})")
st_cols = st.columns(6)
for i, name in enumerate(STAFF):
    dt_type = get_duty_type(name, now.date())
    txt, clr = get_current_status(name, i, dt_type, now)
    with st_cols[i]:
        st.write(f"**{name}**")
        if clr == "green": st.success(txt)
        elif clr == "orange": st.warning(txt)
        elif clr == "red": st.error(txt)
        elif clr == "blue": st.info(txt)
        else: st.caption(txt)

st.divider()

# --- 6. 申请录入与管理 ---
with st.sidebar:
    st.header("⚙️ 行政管理")
    with st.form("req_form", clear_on_submit=True):
        u_name = st.selectbox("人员", STAFF)
        u_type = st.radio("类型", ["请假", "调休"], horizontal=True)
        u_date = st.date_input("日期", value=now.date())
        u_t1 = st.time_input("开始", value=time(9,0))
        u_t2 = st.time_input("结束", value=time(18,0))
        if st.form_submit_button("提交申请"):
            df = load_data()
            h = round((datetime.combine(u_date, u_t2) - datetime.combine(u_date, u_t1)).total_seconds()/3600, 1)
            new_id = int(df['id'].max()+1) if not df.empty else 1
            new_row = pd.DataFrame([[new_id, u_name, u_type, u_date, str(u_t1), str(u_t2), h, "有效"]], columns=df.columns)
            pd.concat([df, new_row]).to_csv(DB_FILE, index=False)
            st.success("申请成功")

    st.divider()
    st.subheader("🗑️ 撤回申请")
    all_recs = load_data()
    valid_recs = all_recs[all_recs['status']=="有效"].sort_values("id", ascending=False).head(5)
    for _, r in valid_recs.iterrows():
        if st.button(f"撤回 ID:{r['id']} {r['name']}", use_container_width=True):
            all_recs.loc[all_recs['id']==r['id'], 'status'] = "已撤回"
            all_recs.to_csv(DB_FILE, index=False)
            st.rerun()

# --- 7. 周度/月度 筛选与工时统计 ---
st.subheader("🗓️ 周度/月度 考勤分析")
tab_week, tab_month = st.tabs(["按周筛选查看", "按月汇总统计"])

with tab_week:
    c1, c2 = st.columns(2)
    s_m_w = c1.selectbox("选择月份 ", range(1, 13), index=now.month-1, key="week_m")
    _, d_cnt = calendar.monthrange(2026, s_m_w)
    m_dates = [datetime(2026, s_m_w, d).date() for d in range(1, d_cnt+1)]
    
    # 将月份日期切分为周
    weeks = []
    temp_week = []
    for d in m_dates:
        temp_week.append(d)
        if d.weekday() == 6 or d == m_dates[-1]:
            weeks.append(temp_week)
            temp_week = []
    
    week_opts = [f"第{i+1}周 ({w[0].strftime('%m/%d')} - {w[-1].strftime('%m/%d')})" for i, w in enumerate(weeks)]
    sel_w_idx = c2.selectbox("选择周数", range(len(week_opts)), format_func=lambda x: week_opts[x])
    
    target_week = weeks[sel_w_idx]
    week_stats = []
    db = load_data()
    db_valid = db[db['status']=="有效"]

    # 构建周表数据
    week_table_data = []
    for name in STAFF:
        row = {"姓名": name}
        w_total_h = 0.0
        for d_obj in target_week:
            d_str = d_obj.strftime("%m-%d\n%a")
            d_type = get_duty_type(name, d_obj)
            
            # 计算该天工时
            day_h = FIXED_WORK_HOUR if d_type != "休息" else 0.0
            day_l = db_valid[(db_valid['name']==name) & (db_valid['date']==d_obj)]
            l_h = day_l['hours'].sum()
            day_h = round(max(0.0, day_h - l_h), 1)
            
            w_total_h += day_h
            # 表格文字显示
            cell_txt = d_type
            if l_h > 0: cell_txt += f"\n(假-{l_h}h)"
            row[d_str] = cell_txt
        
        row["本周工时"] = round(w_total_h, 1)
        week_table_data.append(row)
    
    st.dataframe(pd.DataFrame(week_table_data), use_container_width=True, hide_index=True)

with tab_month:
    s_m_m = st.selectbox("选择统计月份", range(1, 13), index=now.month-1, key="month_m")
    _, d_cnt_m = calendar.monthrange(2026, s_m_m)
    m_dates_m = [datetime(2026, s_m_m, d).date() for d in range(1, d_cnt_m+1)]
    
    m_summary = []
    for name in STAFF:
        valid_days = [d for d in m_dates_m if d >= START_DATE]
        work_days = sum([1 for d in valid_days if get_duty_type(name, d) != "休息"])
        plan_h = work_days * FIXED_WORK_HOUR
        deduct = db_valid[(db_valid['name']==name) & (pd.to_datetime(db_valid['date']).dt.month==s_m_m)]['hours'].sum()
        m_summary.append({
            "姓名": name, 
            "出勤天数": work_days, 
            "应到工时": round(plan_h, 1),
            "请假扣除": round(deduct, 1),
            "本月实到工时": round(plan_h - deduct, 1)
        })
    
    st.table(pd.DataFrame(m_summary))

# --- 8. 刷新按钮 ---
if st.button("🔄 刷新系统数据"):
    st.rerun()
