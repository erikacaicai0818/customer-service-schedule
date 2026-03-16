import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import os
import pytz
import calendar

# --- 1. 系统基础配置 ---
china_tz = pytz.timezone('Asia/Shanghai')
def get_now():
    return datetime.now(china_tz)

st.set_page_config(page_title="客服部智能排班系统 v12", layout="wide", page_icon="🗓️")

# 核心常量
START_DATE = datetime(2026, 3, 1).date()
STAFF = ["郭战勇", "徐远远", "陈鹤舞", "都 娟", "陈君琳", "顾凌海"]
DB_FILE = "duty_database_v12.csv"
FIXED_HOUR = 8.5 

# 午休配置
LUNCH_CONFIG = {
    0: {"group": "A组", "start": time(11, 30), "end": time(13, 0)},
    1: {"group": "B组", "start": time(13, 0), "end": time(14, 30)},
    2: {"group": "A组", "start": time(11, 30), "end": time(13, 0)},
    3: {"group": "B组", "start": time(13, 0), "end": time(14, 30)},
    4: {"group": "A组", "start": time(11, 30), "end": time(13, 0)},
    5: {"group": "B组", "start": time(13, 0), "end": time(14, 30)},
}

# --- 2. 数据库逻辑 ---
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

# --- 3. 排班算法逻辑 ---
def get_duty_type(name, date_obj):
    if date_obj < START_DATE: return "未开始"
    weekday = date_obj.weekday()
    # 固定休息日
    if name == "郭战勇" and weekday == 2: return "休息"
    if name == "徐远远" and weekday == 5: return "休息"
    if name not in ["郭战勇", "徐远远"] and weekday == 6: return "休息"
    # 晚班分配
    working_s = [s for s in STAFF if is_working(s, date_obj)]
    num_late = 1 if weekday == 6 else 2
    seed = date_obj.day + date_obj.month
    late_team = [working_s[(seed + i) % len(working_s)] for i in range(num_late)]
    if name in late_team: return "晚值班"
    # 延迟班判定
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

# --- 4. 实时状态判定 ---
def get_status(name, name_idx, dtype, now_dt):
    now_t, now_d = now_dt.time(), now_dt.date()
    recs = load_db()
    active = recs[(recs['name']==name) & (recs['date']==now_d) & (recs['status']=="有效")]
    for _, r in active.iterrows():
        st_t = datetime.strptime(r['start_t'], "%H:%M").time()
        en_t = datetime.strptime(r['end_t'], "%H:%M").time()
        if st_t <= now_t <= en_t: return f"🔴 {r['type']}中", "red"
    if dtype in ["休息", "未开始"]: return "😴 休息中", "grey"
    if dtype != "晚值班":
        l_start, l_end = (time(12,45), time(14,15)) if now_d.weekday()==6 else (LUNCH_CONFIG[name_idx]['start'], LUNCH_CONFIG[name_idx]['end'])
        if l_start <= now_t <= l_end: return f"🍱 午休中({l_start.strftime('%H:%M')})", "orange"
    if dtype == "晚值班":
        if now_t < time(12,30): return "⏳ 等待上班", "grey"
        if time(12,30) <= now_t <= time(19,0): return "🏢 在司值班", "green"
        if time(19,0) <= now_t <= time(20,0): return "🚗 通勤中", "blue"
        if time(20,0) <= now_t <= time(22,0): return "🏠 居家远程", "green"
    elif dtype == "延迟班":
        if time(10,0) <= now_t <= time(20,0): return "🏢 在司值班", "green"
    else:
        if time(9,0) <= now_t <= time(19,0): return "🏢 在司值班", "green"
    return "🌙 已下班", "red"

# --- 5. 主页面 ---
now = get_now()
st.title("🛡️ 客服部智能综合管理系统")

# 侧边栏
with st.sidebar:
    st.header("📋 考勤申请")
    with st.form("sidebar_form", clear_on_submit=True):
        a_name = st.selectbox("人员", STAFF)
        a_type = st.radio("种类", ["请假", "调休"], horizontal=True)
        a_date = st.date_input("日期", value=now.date())
        a_t1 = st.time_input("开始时间", value=time(9,0))
        a_t2 = st.time_input("结束时间", value=time(18,0))
        a_reason = st.text_input("备注事由")
        if st.form_submit_button("提交申请"):
            if a_date < START_DATE: st.error("日期无效")
            else:
                save_request(a_name, a_type, a_date, a_t1, a_t2, a_reason)
                st.success("申请已保存")
                st.rerun()

# 标签页
tab_real, tab_ind, tab_week, tab_month, tab_data = st.tabs(["🔴 实时监控", "👤 个人月度表", "📅 周度全表", "📊 月度统计", "🔍 记录管理"])

# Tab 1: 实时
with tab_real:
    on_duty = 0
    st.markdown(f"#### 北京时间：{now.strftime('%H:%M:%S')} | 在位统计：")
    cols = st.columns(6)
    for i, name in enumerate(STAFF):
        dt = get_duty_type(name, now.date())
        txt, clr = get_status(name, i, dt, now)
        if clr == "green": on_duty += 1
        with cols[i]:
            st.write(f"**{name}**")
            st.caption(dt)
            if clr == "green": st.success(txt)
            elif clr == "orange": st.warning(txt)
            elif clr == "red": st.error(txt)
            elif clr == "blue": st.info(txt)
            else: st.write(txt)
    st.write(f"当前在岗人数：`{on_duty}`")

# Tab 2: 个人月度表 (新功能)
with tab_ind:
    st.subheader("👤 个人月度值班日历")
    i_col1, i_col2, i_col3 = st.columns([1, 1, 2])
    target_staff = i_col1.selectbox("选择要查看的员工", STAFF, index=0)
    target_year = i_col2.selectbox("年份 ", [2026, 2027], index=0)
    target_month = i_col3.selectbox("月份 ", range(1, 13), index=now.month-1)
    
    # 构建日历逻辑
    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdatescalendar(target_year, target_month)
    db_recs = load_db()
    db_v = db_recs[db_recs['status']=="有效"]
    
    # 表头
    week_header = st.columns(7)
    days_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    for i, d_name in enumerate(days_cn): week_header[i].button(d_name, disabled=True, use_container_width=True)
    
    # 填充日历
    staff_idx = STAFF.index(target_staff)
    total_m_hours = 0.0
    for week in month_days:
        cols = st.columns(7)
        for i, d_date in enumerate(week):
            if d_date.month == target_month:
                dtype = get_duty_type(target_staff, d_date)
                # 计算工时
                day_h = FIXED_HOUR if dtype != "休息" else 0.0
                day_l = db_v[(db_v['name']==target_staff) & (db_v['date']==d_date)]
                l_h = day_l['hours'].sum()
                final_h = round(max(0.0, day_h - l_h), 1)
                total_m_hours += final_h
                
                # 样式
                with cols[i]:
                    with st.container():
                        st.write(f"**{d_date.day}**")
                        if dtype == "休息":
                            st.caption(":grey[休]")
                        else:
                            st.write(f"**{dtype}**")
                            # 显示对应午休
                            l_t = "12:45" if d_date.weekday()==6 else LUNCH_CONFIG[staff_idx]['start'].strftime('%H:%M')
                            st.caption(f"🍱 {l_t}")
                            if l_h > 0: st.markdown(f":red[假-{l_h}h]")
            else:
                cols[i].write("")
    st.divider()
    st.info(f"💡 **{target_staff}** 在 {target_year}年{target_month}月 的预计实到总工时为：**{round(total_m_hours, 1)}** 小时")

# Tab 3: 周度全表
with tab_week:
    monday = now.date() - timedelta(days=now.weekday())
    w_dates = [monday + timedelta(days=i) for i in range(7)]
    db_v = load_db()[load_db()['status']=="有效"]
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
                l_t = LUNCH_CONFIG[STAFF.index(name)]['start'].strftime('%H:%M') if d.weekday()==6 else "12:45"
                cell += f"\n(休:{l_t})"
            if l_h > 0: cell += f"\n[-{l_h}h]"
            row[d.strftime("%m-%d\n%a")] = cell
        row["本周工时"] = round(total, 1)
        w_data.append(row)
    st.dataframe(pd.DataFrame(w_data), use_container_width=True, hide_index=True)

# Tab 4: 月度统计
with tab_month:
    st.subheader("📊 月度出勤汇总")
    m_y = st.selectbox("选择年份", [2026, 2027], index=0, key="my")
    m_m = st.selectbox("选择月份", range(1, 13), index=now.month-1, key="mm")
    _, days = calendar.monthrange(m_y, m_m)
    m_dates = [datetime(m_y, m_m, d).date() for d in range(1, days+1) if datetime(m_y, m_m, d).date() >= START_DATE]
    m_summary = []
    for name in STAFF:
        wd = sum([1 for d in m_dates if is_working(name, d)])
        plan = wd * FIXED_HOUR
        deduct = db_v[(db_v['name']==name) & (pd.to_datetime(db_v['date']).dt.month==m_m) & (pd.to_datetime(db_v['date']).dt.year==m_y)]['hours'].sum()
        m_summary.append({"姓名": name, "应出勤天数": wd, "标准工时": round(plan, 1), "扣除工时": round(deduct, 1), "实到计薪工时": round(plan-deduct, 1)})
    st.table(pd.DataFrame(m_summary))

# Tab 5: 管理记录
with tab_data:
    st.subheader("🔍 历史记录中心")
    f_m = st.selectbox("按月份查看", range(1, 13), index=now.month-1, key="fm")
    recs = load_db()
    filtered = recs[pd.to_datetime(recs['date']).dt.month == f_m].sort_values("date", ascending=False)
    for _, row in filtered.iterrows():
        c1, c2, c3 = st.columns([1, 5, 1])
        c1.code(row['id'])
        c2.markdown(f"**{row['name']}** | {row['date']} | {row['type']} ({row['hours']}h) | 原因: {row['reason']}")
        if row['status'] == "有效":
            if c3.button("撤回", key=f"btn_{row['id']}"):
                withdraw_req(row['id'])
                st.rerun()
        else:
            c3.write(":red[已撤回]")
        st.divider()

if st.button("🔄 刷新系统"):
    st.rerun()
