import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import os
import pytz
import calendar

# --- 1. 时区与配置 ---
china_tz = pytz.timezone('Asia/Shanghai')

def get_now():
    return datetime.now(china_tz)

st.set_page_config(page_title="客服部公平固定排班系统", layout="wide")

# 核心常量
START_DATE = datetime(2026, 3, 1).date()
STAFF = ["郭战勇", "徐远远", "陈鹤舞", "都 娟", "陈君琳", "顾凌海"]
DB_FILE = "duty_final_v8.csv"
FIXED_HOUR = 8.5 # 所有人每天都是8.5小时

# --- 2. 班次定义展示 ---
st.title("⚖️ 客服部绝对公平排班系统 (固定休息日版)")

with st.expander("📌 班次定义与工时规则", expanded=True):
    st.markdown(f"""
    | 班次名称 | 工作时间 (在司 + 居家) | 纯工时 | 休息安排 |
    | :--- | :--- | :--- | :--- |
    | **早班** | 09:00 - 19:00 (在司) | {FIXED_HOUR}h | 1.5h |
    | **延迟班** | 10:00 - 20:00 (在司) | {FIXED_HOUR}h | 1.5h |
    | **晚值班** | 12:30 - 19:00 (在司) + 20:00 - 22:00 (居家) | {FIXED_HOUR}h | 在司期间已扣除 |
    | **休息** | 不排班 | 0h | **战勇(三)、远远(六)、其余(日)** |
    """)
    st.success(f"⚖️ **绝对公平保证**：所有人每周均上班 6 天，每周总时长均为 {6 * FIXED_HOUR:.1f} 小时。")

# --- 3. 数据持久化 ---
if not os.path.exists(DB_FILE):
    pd.DataFrame(columns=["id", "name", "type", "date", "start_t", "end_t", "hours", "status"]).to_csv(DB_FILE, index=False)

def load_data():
    df = pd.read_csv(DB_FILE)
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df

# --- 4. 核心排班算法 ---
def get_duty_type(name, date_obj):
    if date_obj < START_DATE: return "未开始"
    
    weekday = date_obj.weekday() # 0=周一, 6=周日
    
    # A. 判定休息日
    if name == "郭战勇" and weekday == 2: return "休息"
    if name == "徐远远" and weekday == 5: return "休息"
    if name not in ["郭战勇", "徐远远"] and weekday == 6: return "休息"
    
    # B. 判定班次 (为了平衡，晚班在当天上班的人中轮流)
    # 找出当天所有上班的人
    working_staff = []
    for s in STAFF:
        if s == "郭战勇" and weekday == 2: continue
        if s == "徐远远" and weekday == 5: continue
        if s not in ["郭战勇", "徐远远"] and weekday == 6: continue
        working_staff.append(s)
    
    # 每天需要的人数：周日1个晚班，其余每天2个晚班
    num_late = 1 if weekday == 6 else 2
    
    # 根据日期轮转晚班位
    day_seed = date_obj.day + date_obj.month
    late_indices = [day_seed % len(working_staff), (day_seed + 1) % len(working_staff)]
    late_team = [working_staff[i] for i in late_indices[:num_late]]
    
    if name in late_team:
        return "晚值班"
    
    # 延迟班逻辑：如果昨天值了晚班，今天就是延迟班
    yesterday = date_obj - timedelta(days=1)
    # 重复昨天的晚班计算逻辑...
    y_weekday = yesterday.weekday()
    y_working = []
    for s in STAFF:
        if s == "郭战勇" and y_weekday == 2: continue
        if s == "徐远远" and y_weekday == 5: continue
        if s not in ["郭战勇", "徐远远"] and y_weekday == 6: continue
        y_working.append(s)
    
    if y_working:
        y_seed = yesterday.day + yesterday.month
        y_num_late = 1 if y_weekday == 6 else 2
        y_late_team = [y_working[i] for i in [y_seed % len(y_working), (y_seed + 1) % len(y_working)][:y_num_late]]
        if name in y_late_team:
            return "延迟班"

    return "早班"

# --- 5. 实时监控显示 ---
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
    
    # 午休逻辑
    if duty_type != "晚值班":
        lunch = (time(11,30), time(13,0)) if name_idx % 2 == 0 else (time(13,0), time(14,30))
        if lunch[0] <= now_t <= lunch[1]: return "🍱 午休中", "orange"

    if duty_type == "晚值班":
        if time(12,30) <= now_t <= time(19,0): return "🏢 在司值班", "green"
        if time(19,0) <= now_t <= time(20,0): return "🚗 通勤中", "blue"
        if time(20,0) <= now_t <= time(22,0): return "🏠 居家远程", "green"
    elif duty_type == "延迟班":
        if time(10,0) <= now_t <= time(20,0): return "🏢 在司值班", "green"
    else:
        if time(9,0) <= now_t <= time(19,0): return "🏢 在司值班", "green"
    return "🌙 已下班", "red"

now = get_now()
st.subheader(f"⏱️ 实时状态监控 ({now.strftime('%H:%M:%S')})")
st_cols = st.columns(6)
for i, name in enumerate(STAFF):
    dtype = get_duty_type(name, now.date())
    txt, clr = get_current_status(name, i, dtype, now)
    with st_cols[i]:
        st.write(f"**{name}**")
        if clr == "green": st.success(txt)
        elif clr == "orange": st.warning(txt)
        elif clr == "red": st.error(txt)
        elif clr == "blue": st.info(txt)
        else: st.caption(txt)

# --- 6. 行政管理 ---
with st.sidebar:
    st.header("⚙️ 考勤行政")
    with st.form("req", clear_on_submit=True):
        n = st.selectbox("人员", STAFF)
        t = st.radio("类型", ["请假", "调休"])
        d = st.date_input("日期", value=now.date())
        t1 = st.time_input("开始", value=time(9,0))
        t2 = st.time_input("结束", value=time(18,0))
        if st.form_submit_button("提交申请"):
            df = load_data()
            h = round((datetime.combine(d, t2) - datetime.combine(d, t1)).total_seconds()/3600, 1)
            new_id = int(df['id'].max()+1) if not df.empty else 1
            pd.concat([df, pd.DataFrame([[new_id, n, t, d, str(t1), str(t2), h, "有效"]], columns=df.columns)]).to_csv(DB_FILE, index=False)
            st.success("已存入")
    
    st.divider()
    if st.button("撤回最后一条记录"):
        df = load_data()
        if not df.empty:
            df.iloc[-1, df.columns.get_loc('status')] = "已撤回"
            df.to_csv(DB_FILE, index=False)
            st.rerun()

# --- 7. 数据分析 ---
st.divider()
t_week, t_month = st.tabs(["📊 周度工时统计", "📅 月度汇总统计"])

with t_week:
    monday = now.date() - timedelta(days=now.weekday())
    week_dates = [monday + timedelta(days=i) for i in range(7)]
    
    week_res = []
    db_v = load_data()
    db_v = db_v[db_v['status']=="有效"]
    
    for name in STAFF:
        row = {"姓名": name}
        total_w = 0.0
        for d_obj in week_dates:
            dt = get_duty_type(name, d_obj)
            day_h = FIXED_HOUR if dt != "休息" else 0.0
            l_h = db_v[(db_v['name']==name) & (db_v['date']==d_obj)]['hours'].sum()
            total_w += (day_h - l_h)
            row[d_obj.strftime("%m-%d\n%a")] = f"{dt}" + (f"\n(-{l_h})" if l_h > 0 else "")
        row["本周工时"] = round(total_w, 1)
        week_res.append(row)
    st.dataframe(pd.DataFrame(week_res), hide_index=True)

with t_month:
    sel_m = st.selectbox("选择月份", range(1, 13), index=now.month-1)
    _, d_cnt = calendar.monthrange(2026, sel_m)
    m_dates = [datetime(2026, sel_m, d).date() for d in range(1, d_cnt+1) if datetime(2026, sel_m, d).date() >= START_DATE]
    
    m_res = []
    for name in STAFF:
        work_days = sum([1 for d in m_dates if get_duty_type(name, d) != "休息"])
        plan_h = work_days * FIXED_HOUR
        deduct = db_v[(db_v['name']==name) & (pd.to_datetime(db_v['date']).dt.month==sel_m)]['hours'].sum()
        m_res.append({"姓名": name, "出勤天数": work_days, "理论工时": round(plan_h, 1), "扣除": round(deduct, 1), "实到工时": round(plan_h-deduct, 1)})
    st.table(pd.DataFrame(m_res))

if st.button("🔄 刷新系统"):
    st.rerun()
