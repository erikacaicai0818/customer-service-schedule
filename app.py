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

st.set_page_config(page_title="客服部固定排班管理系统", layout="wide")

# 核心常量
START_DATE = datetime(2026, 3, 1).date() # 2026-03-01 是周日
STAFF = ["郭战勇", "徐远远", "陈鹤舞", "都 娟", "陈君琳", "顾凌海"]
# 为每个人分配一个永久固定的周中休息日 (0=周一, 5=周六)
FIXED_WEEKDAY_OFF = {
    "郭战勇": 0, "徐远远": 1, "陈鹤舞": 2, "都 娟": 3, "陈君琳": 4, "顾凌海": 5
}
DB_FILE = "duty_records_final_v7.csv"
FIXED_WORK_HOUR = 8.5 

# --- 2. 界面顶部：规则展示 ---
st.title("⚖️ 客服部固定周休排班系统")
with st.expander("📌 排班规则说明 (固定休息日版)", expanded=True):
    st.markdown(f"""
    1. **固定周中休息**：郭(一)、徐(二)、陈H(三)、都(四)、陈J(五)、顾(六) 每周休息日固定。
    2. **轮流值周日**：每3周轮值一次周日。值周日当周工作6天，不值周日当周工作5天。
    3. **工时对齐**：所有班次(早/延迟/晚)实际工时均为 **{FIXED_WORK_HOUR}h**。
    4. **绝对公平**：每3周累计工时均为 **136.0h**，每人休息天数完全一致。
    """)

# --- 3. 数据持久化逻辑 ---
if not os.path.exists(DB_FILE):
    pd.DataFrame(columns=["id", "name", "type", "date", "start_t", "end_t", "hours", "status"]).to_csv(DB_FILE, index=False)

def load_data():
    df = pd.read_csv(DB_FILE)
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df

# --- 4. 核心算法：固定周中 + 轮转周日 ---
def get_duty_type(name, date_obj):
    if date_obj < START_DATE: return "未开始"
    
    weekday = date_obj.weekday() # 0=周一, 6=周日
    name_idx = STAFF.index(name)
    
    # 判定周日轮值 (3周一循环)
    weeks_passed = (date_obj - START_DATE).days // 7
    cycle = weeks_passed % 3
    sun_pair_indices = [cycle * 2, cycle * 2 + 1]
    
    if weekday == 6: # 周日
        # 周日两人：一人早班，一人晚班
        if name_idx == sun_pair_indices[0]: return "早班"
        if name_idx == sun_pair_indices[1]: return "晚值班"
        return "休息"
    else:
        # 周一至周六：检查是否是该人固定的休息日
        if weekday == FIXED_WEEKDAY_OFF[name]:
            return "休息"
        
        # 晚班分配 (在岗的5人中轮流，确保覆盖)
        night_idx = (date_obj.day + date_obj.month) % 6
        if name_idx == night_idx and weekday != FIXED_WEEKDAY_OFF[name]:
            return "晚值班"
        
        # 延迟班分配 (逻辑简化：前一天是晚班的人)
        yesterday = date_obj - timedelta(days=1)
        if (yesterday.day + yesterday.month) % 6 == name_idx:
            return "延迟班"
            
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
    
    # 午休逻辑
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

# --- 5. 实时监控看板 ---
now = get_now()
st.subheader(f"⏱️ 实时监控面板 ({now.strftime('%H:%M:%S')})")
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

# --- 6. 行政管理：请假/调休与回撤 ---
with st.sidebar:
    st.header("⚙️ 考勤行政管理")
    with st.form("req_form", clear_on_submit=True):
        u_name = st.selectbox("人员选择", STAFF)
        u_type = st.radio("申请种类", ["请假", "调休"], horizontal=True)
        u_date = st.date_input("日期", value=now.date())
        u_t1 = st.time_input("开始", value=time(9,0))
        u_t2 = st.time_input("结束", value=time(18,0))
        if st.form_submit_button("提交申请"):
            df = load_data()
            h = round((datetime.combine(u_date, u_t2) - datetime.combine(u_date, u_t1)).total_seconds()/3600, 1)
            new_id = int(df['id'].max()+1) if not df.empty else 1
            new_row = pd.DataFrame([[new_id, u_name, u_type, u_date, str(u_t1), str(u_t2), h, "有效"]], columns=df.columns)
            pd.concat([df, new_row]).to_csv(DB_FILE, index=False)
            st.success("记录已保存")

    st.divider()
    st.subheader("🗑️ 最近申请撤回")
    all_recs = load_data()
    valid_recs = all_recs[all_recs['status']=="有效"].sort_values("id", ascending=False).head(5)
    for _, r in valid_recs.iterrows():
        if st.button(f"撤销 {r['name']} {r['date']}", key=f"rev_{r['id']}", use_container_width=True):
            all_recs.loc[all_recs['id']==r['id'], 'status'] = "已撤回"
            all_recs.to_csv(DB_FILE, index=False)
            st.rerun()

# --- 7. 周/月度 数据中心 ---
st.subheader("🗓️ 工时数据统计中心")
tab_w, tab_m = st.tabs(["周度排班预览", "月度汇总统计"])

with tab_w:
    c1, c2 = st.columns(2)
    s_m_w = c1.selectbox("月份", range(1, 13), index=now.month-1, key="wm")
    _, d_cnt = calendar.monthrange(2026, s_m_w)
    m_dates = [datetime(2026, s_m_w, d).date() for d in range(1, d_cnt+1)]
    weeks = []
    temp = []
    for d in m_dates:
        temp.append(d)
        if d.weekday() == 6 or d == m_dates[-1]:
            weeks.append(temp); temp = []
    opts = [f"第{i+1}周 ({w[0].strftime('%m/%d')}-{w[-1].strftime('%m/%d')})" for i, w in enumerate(weeks)]
    sel_idx = c2.selectbox("周数", range(len(opts)), format_func=lambda x: opts[x])
    
    target_week = weeks[sel_idx]
    db_v = load_data()[load_data()['status']=="有效"]
    week_table = []
    for name in STAFF:
        row = {"姓名": name}
        w_h = 0.0
        for d_obj in target_week:
            d_str = d_obj.strftime("%m-%d\n%a")
            d_type = get_duty_type(name, d_obj)
            day_h = FIXED_WORK_HOUR if d_type != "休息" else 0.0
            l_h = db_v[(db_v['name']==name) & (db_v['date']==d_obj)]['hours'].sum()
            final_h = round(max(0.0, day_h - l_h), 1)
            w_h += final_h
            row[d_str] = d_type + (f"\n(-{l_h}h)" if l_h > 0 else "")
        row["本周实到"] = round(w_h, 1)
        week_table.append(row)
    st.dataframe(pd.DataFrame(week_table), use_container_width=True, hide_index=True)

with tab_m:
    s_m_m = st.selectbox("选择月份汇总", range(1, 13), index=now.month-1, key="mm")
    _, d_cnt_m = calendar.monthrange(2026, s_m_m)
    m_summary = []
    for name in STAFF:
        dates_m = [datetime(2026, s_m_m, d).date() for d in range(1, d_cnt_m+1) if datetime(2026, s_m_m, d).date() >= START_DATE]
        work_days = sum([1 for d in dates_m if get_duty_type(name, d) != "休息"])
        plan_h = work_days * FIXED_WORK_HOUR
        deduct = db_v[(db_v['name']==name) & (pd.to_datetime(db_v['date']).dt.month==s_m_m)]['hours'].sum()
        m_summary.append({
            "姓名": name, "出勤天数": work_days, "理论总工时": round(plan_h, 1), "请假扣除": round(deduct, 1), "实到总工时": round(plan_h - deduct, 1)
        })
    st.table(pd.DataFrame(m_summary))

if st.button("🔄 刷新全站数据"):
    st.rerun()
