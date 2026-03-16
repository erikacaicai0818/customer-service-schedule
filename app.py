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

st.set_page_config(page_title="客服部公平排班系统", layout="wide", page_icon="⚖️")

# 核心常量
START_DATE = datetime(2026, 3, 1).date()
STAFF = ["郭战勇", "徐远远", "陈鹤舞", "都 娟", "陈君琳", "顾凌海"]
DB_FILE = "duty_records_v4.csv"

# 统一工时标准：8.5小时
FIXED_WORK_HOUR = 8.5 

# --- 2. 界面顶部：班次定义标注 ---
st.title("⚖️ 客服部公平排班与考勤管理系统")

with st.expander("📝 查看班次定义与工时说明 (必看)", expanded=True):
    st.markdown("""
    | 班次名称 | 工作时间段 | 休息时间 | 实际工时 | 备注 |
    | :--- | :--- | :--- | :--- | :--- |
    | **早班** | 09:00 - 19:00 (在司) | 1.5小时 | 8.5h | 负责早间服务开场 |
    | **延迟班** | 10:00 - 20:00 (在司) | 1.5小时 | 8.5h | 晚值班次日使用，负责19-20点在司覆盖 |
    | **晚值班** | 12:30 - 19:00 (在司) + 20:00 - 22:00 (居家) | 无(在司期间已扣) | 8.5h | 负责20-22点居家值班 |
    | **休息** | - | - | 0h | 实行“做六休一”，轮流滚动 |
    """)
    st.info("💡 **公平性说明**：系统采用 6 天一循环的滚动算法。在一个周期内，每人的总工时和休息天数完全一致。")

# --- 3. 数据持久化 ---
if not os.path.exists(DB_FILE):
    pd.DataFrame(columns=["id", "name", "type", "date", "start_t", "end_t", "hours", "status"]).to_csv(DB_FILE, index=False)

def load_data():
    df = pd.read_csv(DB_FILE)
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df

# --- 4. 核心算法：循环排班 ---
def get_duty_type(name, date_obj):
    days_diff = (date_obj - START_DATE).days
    name_idx = STAFF.index(name)
    weekday = date_obj.weekday()
    
    # 周日特殊处理 (2人上班)
    if weekday == 6:
        cycle_week = (days_diff // 7) % 3
        pairs = [(0, 1), (2, 3), (4, 5)] # 轮流值周日
        sun_pair = pairs[cycle_week]
        if name_idx == sun_pair[0]: return "早班"
        if name_idx == sun_pair[1]: return "晚值班"
        return "休息"
    else:
        # 周一至周六：每天1人休息 (6天一轮转)
        off_idx = (days_diff - (days_diff // 7)) % 6
        if name_idx == off_idx: return "休息"
        
        # 晚班分配：每天1-2人晚班 (确保覆盖)
        night_idx = (days_diff) % 6
        if name_idx == night_idx: return "晚值班"
        
        # 延迟班分配 (昨天是晚班的人)
        yesterday_diff = days_diff - 1
        y_night_idx = (yesterday_diff) % 6
        if name_idx == y_night_idx: return "延迟班"
            
        return "早班"

def get_current_status(name, name_idx, duty_type, now_dt):
    now_t = now_dt.time()
    now_d = now_dt.date()
    
    # 请假判定
    recs = load_data()
    active = recs[(recs['name']==name) & (recs['date']==now_d) & (recs['status']=="有效")]
    for _, r in active.iterrows():
        st_t = datetime.strptime(r['start_t'], "%H:%M:%S").time()
        en_t = datetime.strptime(r['end_t'], "%H:%M:%S").time()
        if st_t <= now_t <= en_t: return f"🔴 {r['type']}中", "red"

    if duty_type == "休息": return "😴 休息中", "grey"
    
    # 午休逻辑判定 (早班和延迟班)
    if "晚值班" not in duty_type:
        lunch = (time(11,30), time(13,0)) if name_idx % 2 == 0 else (time(13,0), time(14,30))
        if lunch[0] <= now_t <= lunch[1]: return "🍱 午休中", "orange"
    
    # 状态判定
    if duty_type == "晚值班":
        if time(12,30) <= now_t <= time(19,0): return "🏢 在司值班", "green"
        if time(19,0) <= now_t <= time(20,0): return "🚗 通勤/待机", "blue"
        if time(20,0) <= now_t <= time(22,0): return "🏠 居家值班", "green"
    elif duty_type == "延迟班":
        if time(10,0) <= now_t <= time(20,0): return "🏢 在司值班", "green"
    elif duty_type == "早班":
        if time(9,0) <= now_t <= time(19,0): return "🏢 在司值班", "green"
        
    return "🌙 已下班", "red"

# --- 5. 页面主体 ---

now = get_now()
st.subheader(f"⏱️ 实时状态监控 (北京时间: {now.strftime('%H:%M:%S')})")

# 实时看板
st_cols = st.columns(6)
for i, name in enumerate(STAFF):
    dt_type = get_duty_type(name, now.date())
    txt, clr = get_current_status(name, i, dt_type, now)
    with st_cols[i]:
        st.write(f"**{name}**")
        st.caption(f"班次: {dt_type}")
        if clr == "green": st.success(txt)
        elif clr == "orange": st.warning(txt)
        elif clr == "red": st.error(txt)
        else: st.info(txt)

st.divider()

# 侧边栏：操作与统计
with st.sidebar:
    st.header("⚙️ 考勤管理")
    with st.form("leave_form", clear_on_submit=True):
        u_name = st.selectbox("选择员工", STAFF)
        u_type = st.radio("申请种类", ["请假", "调休"], horizontal=True)
        u_date = st.date_input("申请日期", value=now.date())
        u_t1 = st.time_input("起始时间", value=time(9,0))
        u_t2 = st.time_input("结束时间", value=time(18,0))
        if st.form_submit_button("提交申请"):
            df = load_data()
            h = round((datetime.combine(u_date, u_t2) - datetime.combine(u_date, u_t1)).total_seconds()/3600, 1)
            new_id = int(df['id'].max()+1) if not df.empty else 1
            new_row = pd.DataFrame([[new_id, u_name, u_type, u_date, u_t1, u_t2, h, "有效"]], columns=df.columns)
            pd.concat([df, new_row]).to_csv(DB_FILE, index=False)
            st.success("申请成功！")

# 月度统计
st.subheader("📊 月度工时汇总")
s_month = st.sidebar.selectbox("选择月份", range(1, 13), index=now.month-1)
_, d_count = calendar.monthrange(2026, s_month)
m_dates = [datetime(2026, s_month, d).date() for d in range(1, d_count+1)]
db = load_data()
db = db[db['status']=="有效"]

summary = []
for name in STAFF:
    # 过滤掉统计起点之前的日期
    valid_dates = [d for d in m_dates if d >= START_DATE]
    work_days = sum([1 for d in valid_dates if get_duty_type(name, d) != "休息"])
    total_h = work_days * FIXED_WORK_HOUR
    # 扣除请假/调休
    deduct = db[(db['name']==name) & (pd.to_datetime(db['date']).dt.month==s_month)]['hours'].sum()
    summary.append({"姓名": name, "出勤天数": work_days, "实际计薪工时": total_h - deduct})

st.table(pd.DataFrame(summary))

# 历史回撤
st.divider()
st.subheader("⏳ 历史记录回撤")
history_df = load_data().sort_values("id", ascending=False).head(10)
for _, r in history_df.iterrows():
    if r['date'] < START_DATE: continue
    c1, c2 = st.columns([5, 1])
    c1.write(f"ID:{r['id']} | {r['name']} | {r['date']} | {r['type']} {r['hours']}h | 状态: {r['status']}")
    if r['status'] == "有效" and c2.button("撤回", key=f"btn_{r['id']}"):
        all_db = load_data()
        all_db.loc[all_db['id']==r['id'], 'status'] = "已撤回"
        all_db.to_csv(DB_FILE, index=False)
        st.rerun()

# 周表预览
st.divider()
st.subheader("🗓️ 周值班预览")
monday = now.date() - timedelta(days=now.weekday())
w_days = [monday + timedelta(days=i) for i in range(7)]
w_df = pd.DataFrame(columns=["人员"] + [d.strftime("%m-%d\n%a") for d in w_days])
w_df["人员"] = STAFF
for i, d in enumerate(w_days):
    for idx, name in enumerate(STAFF):
        t = get_duty_type(name, d)
        if not db[(db['name']==name) & (db['date']==d)].empty: t = f"⚠️ {t}(假)"
        w_df.iloc[idx, i+1] = t
st.dataframe(w_df, use_container_width=True, hide_index=True)
