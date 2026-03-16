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

st.set_page_config(page_title="客服部绝对公平排班系统", layout="wide", page_icon="⚖️")

# 核心常量
START_DATE = datetime(2026, 3, 1).date() # 2026-03-01 是周日
STAFF = ["郭战勇", "徐远远", "陈鹤舞", "都 娟", "陈君琳", "顾凌海"]
DB_FILE = "duty_records_final_v6.csv"
FIXED_WORK_HOUR = 8.5 # 所有人所有班次统一8.5小时

# --- 2. 班次与工时定义标注 ---
st.title("⚖️ 客服部绝对公平排班管理系统")
with st.expander("📖 班次说明与公平算法 (必读)", expanded=False):
    st.markdown(f"""
    ### 1. 班次定义 (工时全部对齐为 {FIXED_WORK_HOUR}h)
    *   **早班**: 09:00 - 19:00 (含1.5h休息)
    *   **延迟班**: 10:00 - 20:00 (含1.5h休息)
    *   **晚值班**: 12:30 - 19:00 (在司) + 20:00 - 22:00 (居家远程)
    *   **休息**: 当天不排班，工时为 0

    ### 2. 绝对公平算法说明
    *   **目标**: 确保每人在三周一个周期内，累计工时完全一致。
    *   **规则**: 
        *   周一至周六：每日5人在岗，1人轮休。
        *   周日：2人在岗（由本周轮值小组承担），4人休息。
        *   **周期**: 每3周为一个大循环。每人在这3周中会经历：**1次“6天工作周”和2次“5天工作周”**。
    *   **最终结果**: 任何人在连续3周后的总工时均为 **136.0小时**。
    """)

# --- 3. 数据持久化逻辑 ---
if not os.path.exists(DB_FILE):
    pd.DataFrame(columns=["id", "name", "type", "date", "start_t", "end_t", "hours", "status"]).to_csv(DB_FILE, index=False)

def load_data():
    df = pd.read_csv(DB_FILE)
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df

# --- 4. 绝对公平排班算法 ---
def get_duty_type(name, date_obj):
    if date_obj < START_DATE: return "未开始"
    
    # 计算从起点开始经过了多少周
    weeks_passed = (date_obj - START_DATE).days // 7
    weekday = date_obj.weekday() # 0=周一, 6=周日
    name_idx = STAFF.index(name)
    
    # 三周一个大循环
    week_cycle = weeks_passed % 3 
    
    # 逻辑：每周由一对组合负责周日值班
    # 第一周: 郭&徐, 第二周: 陈&都, 第三周: 陈君&顾
    sun_pair_idx = [week_cycle * 2, week_cycle * 2 + 1]
    
    if weekday == 6: # 周日
        return "晚值班" if name_idx in sun_pair_idx else "休息"
    else:
        # 周一至周六：每天必须有且仅有1人休息
        # 休息日轮转逻辑：确保每个人在周一到周六之间有一天休息
        # 这里使用确定性的偏移量，保证每天只有一个人休息
        off_day_map = (name_idx + (weeks_passed * 2)) % 6
        if weekday == off_day_map:
            # 如果这人这周要上周日，则他在周一到周六必须有休（保证做六休一）
            # 如果这人这周不上周日，他也在周一到周六休一天（保证做五休二）
            return "休息"
        
        # 晚班分配：每天1名晚班，按名字索引轮流
        night_idx = (date_obj.day + weeks_passed) % 6
        if name_idx == night_idx: return "晚值班"
        
        # 延迟班：前一天值晚班的人
        yesterday = date_obj - timedelta(days=1)
        if weekday > 0: # 周一没有延迟班（因为周日是晚值班逻辑）
            y_night_idx = (yesterday.day + weeks_passed) % 6
            if name_idx == y_night_idx: return "延迟班"

        return "早班"

# --- 5. 实时监控看板 ---
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
    
    # 午休逻辑 (早班/延迟班)
    if duty_type != "晚值班":
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

now = get_now()
st.subheader(f"⏱️ 实时监控看板 ({now.strftime('%H:%M:%S')})")
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

# --- 6. 申请录入与回撤 ---
with st.sidebar:
    st.header("⚙️ 考勤行政管理")
    with st.form("req_form", clear_on_submit=True):
        u_name = st.selectbox("人员选择", STAFF)
        u_type = st.radio("申请种类", ["请假", "调休"], horizontal=True)
        u_date = st.date_input("申请日期", value=now.date())
        u_t1 = st.time_input("开始时间", value=time(9,0))
        u_t2 = st.time_input("结束时间", value=time(18,0))
        if st.form_submit_button("提交申请"):
            df = load_data()
            h = round((datetime.combine(u_date, u_t2) - datetime.combine(u_date, u_t1)).total_seconds()/3600, 1)
            new_id = int(df['id'].max()+1) if not df.empty else 1
            new_row = pd.DataFrame([[new_id, u_name, u_type, u_date, str(u_t1), str(u_t2), h, "有效"]], columns=df.columns)
            pd.concat([df, new_row]).to_csv(DB_FILE, index=False)
            st.success("申请成功")

    st.divider()
    st.subheader("🗑️ 记录回撤")
    all_recs = load_data()
    valid_recs = all_recs[all_recs['status']=="有效"].sort_values("id", ascending=False).head(5)
    for _, r in valid_recs.iterrows():
        if st.button(f"撤回 ID:{r['id']} {r['name']}", use_container_width=True):
            all_recs.loc[all_recs['id']==r['id'], 'status'] = "已撤回"
            all_recs.to_csv(DB_FILE, index=False)
            st.rerun()

# --- 7. 周/月度 工时深度统计 ---
st.subheader("🗓️ 工时与排班数据中心")
tab_week, tab_month = st.tabs(["周度排班与统计 (核心公平性)", "月度工时统计汇总"])

with tab_week:
    c1, c2 = st.columns(2)
    s_m_w = c1.selectbox("月份筛选", range(1, 13), index=now.month-1, key="w_m")
    _, d_cnt = calendar.monthrange(2026, s_m_w)
    m_dates = [datetime(2026, s_m_w, d).date() for d in range(1, d_cnt+1)]
    weeks = []
    temp_week = []
    for d in m_dates:
        temp_week.append(d)
        if d.weekday() == 6 or d == m_dates[-1]:
            weeks.append(temp_week)
            temp_week = []
    week_opts = [f"第{i+1}周 ({w[0].strftime('%m/%d')} - {w[-1].strftime('%m/%d')})" for i, w in enumerate(weeks)]
    sel_w_idx = c2.selectbox("周选择", range(len(week_opts)), format_func=lambda x: week_opts[x])
    
    target_week = weeks[sel_w_idx]
    db_valid = load_data()[load_data()['status']=="有效"]
    week_table = []
    for name in STAFF:
        row = {"姓名": name}
        w_total_h = 0.0
        for d_obj in target_week:
            d_str = d_obj.strftime("%m-%d\n%a")
            d_type = get_duty_type(name, d_obj)
            day_h = FIXED_WORK_HOUR if d_type != "休息" else 0.0
            l_h = db_valid[(db_valid['name']==name) & (db_valid['date']==d_obj)]['hours'].sum()
            final_h = round(max(0.0, day_h - l_h), 1)
            w_total_h += final_h
            row[d_str] = f"{d_type}" + (f"\n(-{l_h}h)" if l_h > 0 else "")
        row["本周工时"] = round(w_total_h, 1)
        week_table.append(row)
    st.dataframe(pd.DataFrame(week_table), use_container_width=True, hide_index=True)
    st.caption("注：由于每周总班次无法被6整除，每周会有2人工作6天(51h)，4人工作5天(42.5h)，系统会自动在三周内轮换，确保三周累计工时绝对一致。")

with tab_month:
    s_m_m = st.selectbox("月份汇总筛选", range(1, 13), index=now.month-1, key="m_m")
    _, d_cnt_m = calendar.monthrange(2026, s_m_m)
    m_dates_m = [datetime(2026, s_m_m, d).date() for d in range(1, d_cnt_m+1)]
    m_summary = []
    for name in STAFF:
        valid_days = [d for d in m_dates_m if d >= START_DATE]
        work_days = sum([1 for d in valid_days if get_duty_type(name, d) != "休息"])
        plan_h = work_days * FIXED_WORK_HOUR
        deduct = db_valid[(db_valid['name']==name) & (pd.to_datetime(db_valid['date']).dt.month==s_m_m) & (pd.to_datetime(db_valid['date']).dt.year==2026)]['hours'].sum()
        m_summary.append({
            "姓名": name, "出勤天数": work_days, "理论工时": round(plan_h, 1), "扣除工时": round(deduct, 1), "实到总工时": round(plan_h - deduct, 1)
        })
    st.table(pd.DataFrame(m_summary))

# --- 8. 刷新按钮 ---
if st.button("🔄 刷新系统数据"):
    st.rerun()
