import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import os
import pytz
import calendar

# --- 1. 系统配置 ---
china_tz = pytz.timezone('Asia/Shanghai')
def get_now():
    return datetime.now(china_tz)

st.set_page_config(page_title="客服部全功能智能管理系统", layout="wide", page_icon="🛡️")

# 核心常量
START_DATE = datetime(2026, 3, 1).date()
STAFF = ["郭战勇", "徐远远", "陈鹤舞", "都 娟", "陈君琳", "顾凌海"]
DB_FILE = "duty_database_v11.csv"
FIXED_HOUR = 8.5 

# 固定午休配置
LUNCH_CONFIG = {
    0: {"group": "A组", "start": time(11, 30), "end": time(13, 0)}, # 郭
    1: {"group": "B组", "start": time(13, 0), "end": time(14, 30)}, # 徐
    2: {"group": "A组", "start": time(11, 30), "end": time(13, 0)}, # 陈H
    3: {"group": "B组", "start": time(13, 0), "end": time(14, 30)}, # 都
    4: {"group": "A组", "start": time(11, 30), "end": time(13, 0)}, # 陈J
    5: {"group": "B组", "start": time(13, 0), "end": time(14, 30)}, # 顾
}

# --- 2. 数据库操作逻辑 ---
def load_db():
    if not os.path.exists(DB_FILE):
        df = pd.DataFrame(columns=["id", "name", "type", "date", "start_t", "end_t", "hours", "reason", "status", "submit_time"])
        df.to_csv(DB_FILE, index=False)
    df = pd.read_csv(DB_FILE)
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df

def save_request(name, req_type, d, t1, t2, reason):
    df = load_db()
    h = round((datetime.combine(d, t2) - datetime.combine(d, t1)).total_seconds() / 3600, 1)
    new_id = int(df['id'].max() + 1) if not df.empty else 1001
    new_row = {
        "id": new_id, "name": name, "type": req_type, "date": d,
        "start_t": t1.strftime('%H:%M'), "end_t": t2.strftime('%H:%M'),
        "hours": h, "reason": reason, "status": "有效", "submit_time": get_now().strftime('%Y-%m-%d %H:%M')
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(DB_FILE, index=False)

def withdraw_req(req_id):
    df = load_db()
    df.loc[df['id'] == req_id, 'status'] = "已撤回"
    df.to_csv(DB_FILE, index=False)

# --- 3. 排班核心算法 ---
def get_duty_type(name, date_obj):
    if date_obj < START_DATE: return "未开始"
    weekday = date_obj.weekday()
    # 固定休息日判定
    if name == "郭战勇" and weekday == 2: return "休息"
    if name == "徐远远" and weekday == 5: return "休息"
    if name not in ["郭战勇", "徐远远"] and weekday == 6: return "休息"
    
    # 晚班分配 (每天2人，周日1人)
    working_s = [s for s in STAFF if is_working(s, date_obj)]
    num_late = 1 if weekday == 6 else 2
    seed = date_obj.day + date_obj.month
    late_team = [working_s[(seed + i) % len(working_s)] for i in range(num_late)]
    if name in late_team: return "晚值班"
    
    # 延迟班判定 (昨日晚班今日延迟)
    yest = date_obj - timedelta(days=1)
    if is_late_yesterday(name, yest): return "延迟班"
    return "早班"

def is_working(name, date_obj):
    weekday = date_obj.weekday()
    if name == "郭战勇" and weekday == 2: return False
    if name == "徐远远" and weekday == 5: return False
    if name not in ["郭战勇", "徐远远"] and weekday == 6: return False
    return True

def is_late_yesterday(name, yest):
    if yest < START_DATE: return False
    yw = yest.weekday()
    yw_s = [s for s in STAFF if is_working(s, yest)]
    if not yw_s: return False
    y_seed = yest.day + yest.month
    y_late = [yw_s[(y_seed + i) % len(yw_s)] for i in range(1 if yw==6 else 2)]
    return name in y_late

# --- 4. 实时监控逻辑 ---
def get_status(name, name_idx, dtype, now_dt):
    now_t, now_d = now_dt.time(), now_dt.date()
    recs = load_db()
    # 检查是否有正在进行的请假/调休
    active = recs[(recs['name']==name) & (recs['date']==now_d) & (recs['status']=="有效")]
    for _, r in active.iterrows():
        st_t = datetime.strptime(r['start_t'], "%H:%M").time()
        en_t = datetime.strptime(r['end_t'], "%H:%M").time()
        if st_t <= now_t <= en_t: return f"🔴 {r['type']}中", "red"

    if dtype in ["休息", "未开始"]: return "😴 休息中", "grey"
    
    # 午休判定
    if dtype != "晚值班":
        l_start, l_end = (time(12,45), time(14,15)) if now_d.weekday()==6 else (LUNCH_CONFIG[name_idx]['start'], LUNCH_CONFIG[name_idx]['end'])
        if l_start <= now_t <= l_end: return f"🍱 午休中({l_start.strftime('%H:%M')})", "orange"

    if dtype == "晚值班":
        if now_t < time(12, 30): return "⏳ 等待上班", "grey"
        if time(12,30) <= now_t <= time(19,0): return "🏢 在司值班", "green"
        if time(19,0) <= now_t <= time(20,0): return "🚗 通勤中", "blue"
        if time(20,0) <= now_t <= time(22,0): return "🏠 居家远程", "green"
    elif dtype == "延迟班":
        if time(10,0) <= now_t <= time(20,0): return "🏢 在司值班", "green"
    else:
        if time(9,0) <= now_t <= time(19,0): return "🏢 在司值班", "green"
    return "🌙 已下班", "red"

# --- 5. 界面布局 ---
now = get_now()
st.title("🎧 客服部全功能智能管理系统")

# 侧边栏：申请入口
with st.sidebar:
    st.header("📋 考勤申请中心")
    with st.form("apply_form", clear_on_submit=True):
        a_name = st.selectbox("选择人员", STAFF)
        a_type = st.radio("申请种类", ["请假", "调休"], horizontal=True)
        a_date = st.date_input("选择日期", value=now.date())
        col_t1, col_t2 = st.columns(2)
        a_t1 = col_t1.time_input("起始时间", value=time(9,0))
        a_t2 = col_t2.time_input("结束时间", value=time(18,0))
        a_reason = st.text_input("申请事由", placeholder="请简述原因")
        if st.form_submit_button("提交申请"):
            if a_date < START_DATE: st.error("日期超出范围")
            else:
                save_request(a_name, a_type, a_date, a_t1, a_t2, a_reason)
                st.success("申请已存入系统")
                st.rerun()

# 标签页设计
tab_real, tab_week, tab_month, tab_data = st.tabs(["实时监控", "周度排班表", "月度工时统计", "申请记录管理"])

# Tab 1: 实时监控
with tab_real:
    on_duty = 0
    status_cards = []
    for i, name in enumerate(STAFF):
        dt = get_duty_type(name, now.date())
        txt, clr = get_status(name, i, dt, now)
        if clr == "green": on_duty += 1
        status_cards.append((name, dt, txt, clr))
    
    st.markdown(f"### 当前北京时间：{now.strftime('%H:%M:%S')} | 在位人数：`{on_duty}`")
    cols = st.columns(6)
    for i, (n, d, t, c) in enumerate(status_cards):
        with cols[i]:
            st.write(f"**{n}**")
            st.caption(f"{d}")
            if c == "green": st.success(t)
            elif c == "orange": st.warning(t)
            elif c == "red": st.error(t)
            elif c == "blue": st.info(t)
            else: st.write(t)

# Tab 2: 周度排班
with tab_week:
    monday = now.date() - timedelta(days=now.weekday())
    w_dates = [monday + timedelta(days=i) for i in range(7)]
    db = load_db()
    db_v = db[db['status']=="有效"]
    
    w_data = []
    for name in STAFF:
        row = {"姓名": name}; total = 0.0
        for d in w_dates:
            dt = get_duty_type(name, d)
            h = FIXED_HOUR if dt != "休息" else 0.0
            l_h = db_v[(db_v['name']==name) & (db_v['date']==d)]['hours'].sum()
            total += (h - l_h)
            cell = f"{dt}"
            if dt != "休息":
                l_t = LUNCH_CONFIG[STAFF.index(name)]['start'].strftime('%H:%M') if d.weekday()!=6 else "12:45"
                cell += f"\n(休:{l_t})"
            if l_h > 0: cell += f"\n[-{l_h}h]"
            row[d.strftime("%m-%d\n%a")] = cell
        row["本周工时"] = round(total, 1)
        w_data.append(row)
    st.dataframe(pd.DataFrame(w_data), use_container_width=True, hide_index=True)

# Tab 3: 月度统计
with tab_month:
    st.subheader("📊 月度出勤汇总")
    c1, c2 = st.columns(2)
    s_y = c1.selectbox("年份", [2026, 2027], index=0)
    s_m = c2.selectbox("月份", range(1, 13), index=now.month-1)
    
    _, days = calendar.monthrange(s_y, s_m)
    m_dates = [datetime(s_y, s_m, d).date() for d in range(1, days+1) if datetime(s_y, s_m, d).date() >= START_DATE]
    
    m_data = []
    for name in STAFF:
        wd = sum([1 for d in m_dates if is_working(name, d)])
        plan = wd * FIXED_HOUR
        deduct = db_v[(db_v['name']==name) & (pd.to_datetime(db_v['date']).dt.month==s_m) & (pd.to_datetime(db_v['date']).dt.year==s_y)]['hours'].sum()
        m_data.append({"姓名": name, "应出勤天数": wd, "标准总工时": round(plan, 1), "扣除工时": round(deduct, 1), "实到计薪工时": round(plan-deduct, 1)})
    st.table(pd.DataFrame(m_data))

# Tab 4: 申请记录管理
with tab_data:
    st.subheader("🔍 历史记录查询与撤回")
    f_col1, f_col2 = st.columns(2)
    f_m = f_col1.selectbox("按月份筛选", range(1, 13), index=now.month-1, key="filter_m")
    f_n = f_col2.multiselect("按姓名筛选", STAFF, default=STAFF)
    
    records = load_db()
    # 筛选
    mask = (pd.to_datetime(records['date']).dt.month == f_m) & (records['name'].isin(f_n))
    filtered_df = records[mask].sort_values("date", ascending=False)
    
    if filtered_df.empty:
        st.info("该月份暂无申请记录")
    else:
        for _, row in filtered_df.iterrows():
            with st.container():
                c_id, c_main, c_btn = st.columns([1, 5, 1])
                c_id.code(row['id'])
                status_color = "green" if row['status']=="有效" else "red"
                c_main.markdown(f"**{row['name']}** | {row['date']} | {row['type']} ({row['hours']}h) | 原因: {row['reason']}")
                c_main.caption(f"状态: :{status_color}[{row['status']}] | 提交于: {row['submit_time']}")
                if row['status'] == "有效":
                    if c_btn.button("撤回", key=f"del_{row['id']}"):
                        withdraw_req(row['id'])
                        st.success(f"记录 {row['id']} 已撤回")
                        st.rerun()
                st.divider()

if st.button("🔄 刷新全站数据"):
    st.rerun()
