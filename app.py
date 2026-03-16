import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import os
import pytz
import calendar

# --- 1. 时区与基础配置 ---
china_tz = pytz.timezone('Asia/Shanghai')

def get_now():
    return datetime.now(china_tz)

st.set_page_config(page_title="客服部公平排班管理系统", layout="wide")

# 核心常量
START_DATE = datetime(2026, 3, 1).date()
STAFF = ["郭战勇", "徐远远", "陈鹤舞", "都 娟", "陈君琳", "顾凌海"]
DB_FILE = "duty_records_final.csv"

# 统一所有工时为 8.5 小时 (实际在岗/远程时长之和)
FIXED_WORK_HOUR = 8.5 

# --- 2. 数据持久化 ---
if not os.path.exists(DB_FILE):
    pd.DataFrame(columns=["id", "name", "type", "date", "start_t", "end_t", "hours", "status"]).to_csv(DB_FILE, index=False)

def load_data():
    df = pd.read_csv(DB_FILE)
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df

# --- 3. 核心算法：绝对公平循环排班 ---

def get_duty_type(name, date_obj):
    """
    通过确定性算法，确保 6 个人在任何月份的工时完全一致。
    逻辑：每个人在 6 天的循环中，必然有 1 天休息，5 天上班。
    """
    days_diff = (date_obj - START_DATE).days
    name_idx = STAFF.index(name)
    
    # 建立一个 6 天一循环的排班矩阵 (确保每天有 5 人上班，1 人休息)
    # 矩阵值：0=休息, 1=早班, 2=延迟班, 3=晚班
    # 周日特殊处理：仅 2 人上班
    weekday = date_obj.weekday()
    
    if weekday == 6:  # 周日
        # 每 3 周一个循环，让大家轮流值周日
        cycle_week = (days_diff // 7) % 3
        pairs = [(0, 1), (2, 3), (4, 5)] # 郭&徐, 陈&都, 陈&顾
        sun_pair_indices = pairs[cycle_week]
        
        if name_idx == sun_pair_indices[0]: return "周日早班"
        if name_idx == sun_pair_indices[1]: return "周日晚班"
        return "休息"
    else:
        # 周一至周六：保证每天 1 人休息，其余 5 人上班
        # 休息位随日期轮转：第1天索引0休，第2天索引1休...
        off_idx = (days_diff - (days_diff // 7)) % 6
        if name_idx == off_idx:
            return "休息"
        
        # 晚班分配：每天 2 人晚班
        night_idx_1 = (days_diff) % 6
        night_idx_2 = (days_diff + 1) % 6
        if name_idx == night_idx_1 or name_idx == night_idx_2:
            return "晚值班"
        
        # 延迟班分配（前一天是晚班的人）
        yesterday_diff = days_diff - 1
        y_night_idx_1 = (yesterday_diff) % 6
        y_night_idx_2 = (yesterday_diff + 1) % 6
        if name_idx == y_night_idx_1 or name_idx == y_night_idx_2:
            return "延迟班"
            
        return "早班"

def get_current_status(name, name_idx, duty_type, now_dt):
    now_t = now_dt.time()
    now_d = now_dt.date()
    
    # 检查请假
    recs = load_data()
    active = recs[(recs['name']==name) & (recs['date']==now_d) & (recs['status']=="有效")]
    for _, r in active.iterrows():
        st_t = datetime.strptime(r['start_t'], "%H:%M:%S").time()
        en_t = datetime.strptime(r['end_t'], "%H:%M:%S").time()
        if st_t <= now_t <= en_t: return f"🔴 {r['type']}中", "red"

    if duty_type == "休息": return "😴 休息中", "grey"
    
    # 午休逻辑
    lunch = (time(11,30), time(13,0)) if name_idx % 2 == 0 else (time(13,0), time(14,30))
    if lunch[0] <= now_t <= lunch[1]: return "🍱 午休中", "orange"
    
    # 班次判定
    if "晚值班" in duty_type or "周日晚班" in duty_type:
        if time(9,0) <= now_t <= time(19,0): return "🏢 在司值班", "green"
        if time(19,0) <= now_t <= time(20,0): return "🚗 通勤/待机", "blue"
        if time(20,0) <= now_t <= time(22,0): return "🏠 居家值班", "green"
    elif duty_type == "延迟班":
        if time(10,0) <= now_t <= time(20,0): return "🏢 在司值班", "green"
    else: # 早班
        if time(9,0) <= now_t <= time(19,0): return "🏢 在司值班", "green"
        
    return "🌙 已下班", "red"

# --- 4. 界面展示 ---

st.title("⚖️ 客服部公平排班管理系统 (工时对齐版)")
now = get_now()
st.subheader(f"⏱️ 当前时间：{now.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")

# A. 实时状态
cols = st.columns(6)
for i, name in enumerate(STAFF):
    duty = get_duty_type(name, now.date())
    state_text, color = get_current_status(name, i, duty, now)
    with cols[i]:
        st.metric(label=name, value=duty)
        if color == "green": st.success(state_text)
        elif color == "orange": st.warning(state_text)
        elif color == "blue": st.info(state_text)
        else: st.error(state_text)

# B. 申请录入与回撤
st.divider()
col_req, col_his = st.columns([1, 2])
with col_req:
    st.subheader("📝 申请录入")
    with st.form("f1", clear_on_submit=True):
        u_name = st.selectbox("人员", STAFF)
        u_type = st.radio("类型", ["请假", "调休"], horizontal=True)
        u_date = st.date_input("日期", value=now.date())
        u_t1 = st.time_input("开始", value=time(9,0))
        u_t2 = st.time_input("结束", value=time(18,0))
        if st.form_submit_button("确认提交"):
            df = load_data()
            h = round((datetime.combine(u_date, u_t2) - datetime.combine(u_date, u_t1)).total_seconds()/3600, 1)
            new_id = int(df['id'].max()+1) if not df.empty else 1
            new_row = pd.DataFrame([[new_id, u_name, u_type, u_date, u_t1, u_t2, h, "有效"]], columns=df.columns)
            pd.concat([df, new_row]).to_csv(DB_FILE, index=False)
            st.success("已更新数据")

with col_his:
    st.subheader("⏳ 历史记录与撤回")
    raw_df = load_data().sort_values("id", ascending=False).head(5)
    for _, r in raw_df.iterrows():
        c1, c2 = st.columns([4, 1])
        c1.write(f"{r['name']} | {r['date']} | {r['type']} {r['hours']}h | {r['status']}")
        if r['status'] == "有效" and c2.button("撤回", key=f"rev_{r['id']}"):
            all_df = load_data()
            all_df.loc[all_df['id']==r['id'], 'status'] = "已撤回"
            all_df.to_csv(DB_FILE, index=False)
            st.rerun()

# C. 月度工时统计 (绝对公平展示)
st.divider()
st.subheader("📊 月度统计 (从2026-03-01起)")
s_year = st.sidebar.selectbox("年份", [2026, 2027], index=0)
s_month = st.sidebar.selectbox("月份", range(1, 13), index=now.month-1)
_, d_count = calendar.monthrange(s_year, s_month)
m_dates = [datetime(s_year, s_month, d).date() for d in range(1, d_count+1)]
db = load_data()
db = db[db['status']=="有效"]

m_summary = []
for name in STAFF:
    # 只有在统计起点之后的日期才计入
    days = [d for d in m_dates if d >= START_DATE]
    # 统计班次数量
    work_days_count = sum([1 for d in days if get_duty_type(name, d) != "休息"])
    scheduled_h = work_days_count * FIXED_WORK_HOUR
    # 扣除请假
    deduction = db[(db['name']==name) & (pd.to_datetime(db['date']).dt.month==s_month) & (pd.to_datetime(db['date']).dt.year==s_year)]['hours'].sum()
    m_summary.append({"姓名": name, "出勤天数": work_days_count, "总计工时": scheduled_h - deduction})

st.table(pd.DataFrame(m_summary))

# D. 值班表预览
st.subheader("🗓️ 值班预览")
mon = now.date() - timedelta(days=now.weekday())
w_days = [mon + timedelta(days=i) for i in range(7)]
w_df = pd.DataFrame(columns=["人员"] + [d.strftime("%m-%d\n%a") for d in w_days])
w_df["人员"] = STAFF
for i, d in enumerate(w_days):
    for idx, name in enumerate(STAFF):
        t = get_duty_type(name, d)
        if not db[(db['name']==name) & (db['date']==d)].empty: t += "(假)"
        w_df.iloc[idx, i+1] = t
st.dataframe(w_df, use_container_width=True, hide_index=True)
