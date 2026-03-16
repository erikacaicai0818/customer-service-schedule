import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
from streamlit_gsheets import GSheetsConnection
import pytz
import calendar
import os

# --- 1. 系统配置与时区 ---
china_tz = pytz.timezone('Asia/Shanghai')
def get_now():
    return datetime.now(china_tz)

st.set_page_config(page_title="客服部考勤计薪系统-云端版", layout="wide", page_icon="⚖️")

# 强制明亮风格 CSS
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #31333F; }
    .stMetric { background-color: #F0F2F6; padding: 10px; border-radius: 10px; }
    [data-testid="stMetricValue"] { color: #31333F; }
    </style>
    """, unsafe_allow_html=True)

# 核心常量
START_DATE = datetime(2026, 3, 1).date()
STAFF = ["郭战勇", "徐远远", "陈鹤舞", "都 娟", "陈君琳", "顾凌海"]
FIXED_HOUR = 8.5 

# 午休配置
LUNCH_CONFIG = {
    0: {"group": "A组", "start": time(11, 30), "end": time(13, 0)}, # 郭
    1: {"group": "B组", "start": time(13, 0), "end": time(14, 30)}, # 徐
    2: {"group": "A组", "start": time(11, 30), "end": time(13, 0)}, # 陈H
    3: {"group": "B组", "start": time(13, 0), "end": time(14, 30)}, # 都
    4: {"group": "A组", "start": time(11, 30), "end": time(13, 0)}, # 陈J
    5: {"group": "B组", "start": time(13, 0), "end": time(14, 30)}, # 顾
}

# --- 2. 数据库连接 (Google Sheets) ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_db():
    try:
        # ttl=0 确保不缓存，实时读取
        data = conn.read(ttl=0)
        df = data.dropna(how="all")
        df['date'] = pd.to_datetime(df['date']).dt.date
        return df
    except:
        # 如果读取失败（例如表空），返回初始结构
        return pd.DataFrame(columns=["id", "name", "type", "date", "start_t", "end_t", "hours", "reason", "status", "submit_time"])

def save_request(name, req_type, d, t1, t2, reason):
    df = load_db()
    h = round((datetime.combine(d, t2) - datetime.combine(d, t1)).total_seconds() / 3600, 1)
    new_id = int(df['id'].max() + 1) if not df.empty else 1001
    new_row = pd.DataFrame([{
        "id": new_id, "name": name, "type": req_type, "date": d.strftime('%Y-%m-%d'),
        "start_t": t1.strftime('%H:%M'), "end_t": t2.strftime('%H:%M'),
        "hours": h, "reason": reason, "status": "有效", "submit_time": get_now().strftime('%Y-%m-%d %H:%M')
    }])
    updated_df = pd.concat([df, new_row], ignore_index=True)
    conn.update(data=updated_df)

def withdraw_req(req_id):
    df = load_db()
    df.loc[df['id'] == req_id, 'status'] = "已撤回"
    conn.update(data=df)

# --- 3. 排班核心算法 (保持 V13 逻辑) ---
def is_working(name, date_obj):
    weekday = date_obj.weekday()
    if name == "郭战勇" and weekday == 2: return False
    if name == "徐远远" and weekday == 5: return False
    if name not in ["郭战勇", "徐远远"] and weekday == 6: return False
    return True

def is_late_yesterday(name, date_obj):
    yesterday = date_obj - timedelta(days=1)
    if yesterday < START_DATE: return False
    y_weekday = yesterday.weekday()
    y_working = [s for s in STAFF if is_working(s, yesterday)]
    if not y_working: return False
    y_seed = yesterday.day + yesterday.month
    y_late_num = 1 if y_weekday == 6 else 2
    y_late_team = [y_working[(y_seed + i) % len(y_working)] for i in range(y_late_num)]
    return name in y_late_team

def get_duty_type(name, date_obj):
    if date_obj < START_DATE: return "未开始"
    if not is_working(name, date_obj): return "休息"
    
    weekday = date_obj.weekday()
    working_staff = [s for s in STAFF if is_working(s, date_obj)]
    num_late = 1 if weekday == 6 else 2
    seed = date_obj.day + date_obj.month
    late_team = [working_staff[(seed + i) % len(working_staff)] for i in range(num_late)]
    
    if name in late_team: return "晚值班"
    if is_late_yesterday(name, date_obj): return "延迟班"
    return "早班"

# --- 4. 实时状态判定 ---
def get_status_ui(name, name_idx, dtype, now_dt, db_df):
    now_t, now_d = now_dt.time(), now_dt.date()
    # 检查数据库中有效的请假记录
    active = db_df[(db_df['name']==name) & (db_df['date']==now_d) & (db_df['status']=="有效")]
    for _, r in active.iterrows():
        st_t = datetime.strptime(str(r['start_t']), "%H:%M").time()
        en_t = datetime.strptime(str(r['end_t']), "%H:%M").time()
        if st_t <= now_t <= en_t: return f"🔴 {r['type']}中", "red"

    if dtype in ["休息", "未开始"]: return "😴 休息中", "grey"
    
    # 午休逻辑判定
    if dtype != "晚值班":
        l_range = (time(12,45), time(14,15)) if now_d.weekday()==6 else (LUNCH_CONFIG[name_idx]['start'], LUNCH_CONFIG[name_idx]['end'])
        if l_range[0] <= now_t <= l_range[1]: return f"🍱 午休中({l_range[0].strftime('%H:%M')})", "orange"

    if dtype == "晚值班":
        if now_t < time(12,30): return "⏳ 等待上班", "grey"
        if time(12,30) <= now_t <= time(19,0): return "🏢 在司值班", "green"
        if time(19,0) <= now_t <= time(20,0): return "🚗 通勤中", "blue"
        if time(20,0) <= now_t <= time(22,0): return "🏠 居家远程", "green"
    elif dtype == "延迟班":
        if time(10,0) <= now_t <= time(20,0): return "🏢 在司值班", "green"
    elif dtype == "早班":
        if time(9,0) <= now_t <= time(19,0): return "🏢 在司值班", "green"
    return "🌙 已下班", "red"

# --- 5. 界面 UI ---
now = get_now()
db_full = load_db() # 页面启动时加载一次数据库

st.title("🛡️ 客服部智能云端考勤系统")

# 侧边栏申请
with st.sidebar:
    st.header("📋 考勤申请提交")
    with st.form("sidebar_form", clear_on_submit=True):
        a_name = st.selectbox("人员姓名", STAFF)
        a_type = st.radio("申请类型", ["事假", "病假", "调休"], horizontal=True)
        a_date = st.date_input("日期", value=now.date())
        a_t1 = st.time_input("开始", value=time(9,0))
        a_t2 = st.time_input("结束", value=time(18,0))
        a_reason = st.text_input("事由备注")
        if st.form_submit_button("提交到云端"):
            save_request(a_name, a_type, a_date, a_t1, a_t2, a_reason)
            st.success("同步成功！")
            st.rerun()

tabs = st.tabs(["🟢 实时监控", "👤 个人月度表", "📅 周度全表", "💰 月度计薪汇总", "🔍 记录管理"])

# Tab 1: 实时监控
with tabs[0]:
    st.subheader(f"⏱️ 北京时间: {now.strftime('%H:%M:%S')}")
    cols = st.columns(6)
    on_duty = 0
    for i, name in enumerate(STAFF):
        dt = get_duty_type(name, now.date())
        txt, clr = get_status_ui(name, i, dt, now, db_full)
        if clr == "green": on_duty += 1
        with cols[i]:
            st.write(f"**{name}**")
            st.caption(dt)
            if clr == "green": st.success(txt)
            elif clr == "orange": st.warning(txt)
            elif clr == "red": st.error(txt)
            elif clr == "blue": st.info(txt)
            else: st.write(txt)
    st.info(f"当前在岗人数：`{on_duty}`")

# Tab 2: 个人月度表
with tabs[1]:
    st.subheader("👤 个人月度排班日历")
    i_c1, i_c2, i_c3 = st.columns([1,1,1])
    t_staff = i_c1.selectbox("查看员工", STAFF)
    t_year = i_c2.selectbox("年份", [2026, 2027])
    t_month = i_c3.selectbox("月份", range(1, 13), index=now.month-1)
    
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(t_year, t_month)
    db_v = db_full[db_full['status']=="有效"]
    
    # 日历头
    h_cols = st.columns(7)
    for idx, d_n in enumerate(["一","二","三","四","五","六","日"]):
        h_cols[idx].markdown(f"<center>周{d_n}</center>", unsafe_allow_html=True)
    
    s_idx = STAFF.index(t_staff)
    for week in weeks:
        cols = st.columns(7)
        for i, d in enumerate(week):
            if d.month == t_month:
                dtype = get_duty_type(t_staff, d)
                with cols[i]:
                    st.write(f"**{d.day}**")
                    if dtype == "休息": st.caption("休")
                    else:
                        st.write(dtype)
                        l_t = "12:45" if d.weekday()==6 else LUNCH_CONFIG[s_idx]['start'].strftime('%H:%M')
                        st.caption(f"🍱{l_t}")
                        day_l = db_v[(db_v['name']==t_staff) & (db_v['date']==d)]
                        for _, r in day_l.iterrows():
                            c = "red" if r['type']=="事假" else "blue"
                            st.markdown(f":{c}[{r['type']}-{r['hours']}h]")
            else: cols[i].write("")

# Tab 3: 周度全表
with tabs[2]:
    mon = now.date() - timedelta(days=now.weekday())
    w_dates = [mon + timedelta(days=i) for i in range(7)]
    w_res = []
    db_v = db_full[db_v['status']=="有效"] if 'db_v' not in locals() else db_v
    for name in STAFF:
        row = {"姓名": name}
        for d in w_dates:
            dt = get_duty_type(name, d)
            l_h = db_v[(db_v['name']==name) & (db_v['date']==d)]['hours'].sum()
            row[d.strftime("%m-%d\n%a")] = f"{dt}" + (f"\n(假:{l_h}h)" if l_h > 0 else "")
        w_res.append(row)
    st.dataframe(pd.DataFrame(w_res), use_container_width=True, hide_index=True)

# Tab 4: 月度计薪汇总 (核心逻辑：事假扣除，病假/调休不扣)
with tabs[3]:
    st.subheader("💰 月度计薪工时汇总")
    m_y = st.selectbox("筛选年份", [2026, 2027], key="my")
    m_m = st.selectbox("筛选月份", range(1, 13), index=now.month-1, key="mm")
    
    _, days_cnt = calendar.monthrange(m_y, m_m)
    m_dates = [datetime(m_y, m_m, d).date() for d in range(1, days_cnt+1) if datetime(m_y, m_m, d).date() >= START_DATE]
    
    m_summary = []
    for name in STAFF:
        wd = sum([1 for d in m_dates if is_working(name, d)])
        standard_h = round(wd * FIXED_HOUR, 1)
        
        recs = db_full[(db_full['name']==name) & (pd.to_datetime(db_full['date']).dt.month==m_m) & (pd.to_datetime(db_full['date']).dt.year==m_y) & (db_full['status']=="有效")]
        
        pers_h = round(recs[recs['type'] == "事假"]['hours'].sum(), 1)
        paid_h = round(recs[recs['type'].isin(["病假", "调休"])]['hours'].sum(), 1)
        final_h = round(max(0.0, standard_h - pers_h), 1)
        
        m_summary.append({
            "姓名": name, "出勤天数": wd, "理论总工时": f"{standard_h}h",
            "事假扣除": f"-{pers_h}h", "病假/调休(不扣)": f"{paid_h}h", "计薪总工时": f"{final_h}h"
        })
    st.table(pd.DataFrame(m_summary))

# Tab 5: 记录管理
with tabs[4]:
    st.subheader("🔍 云端流水管理")
    f_m = st.selectbox("按月查看", range(1, 13), index=now.month-1)
    df_show = db_full[pd.to_datetime(db_full['date']).dt.month == f_m].sort_values("date", ascending=False)
    
    if df_show.empty: st.info("本月暂无记录")
    else:
        for _, row in df_show.iterrows():
            c1, c2, c3 = st.columns([1, 5, 1])
            c1.code(row['id'])
            s_clr = "green" if row['status']=="有效" else "red"
            c2.markdown(f"**{row['name']}** | {row['date']} | {row['type']} ({row['hours']}h) | 理由: {row['reason']}")
            c2.caption(f"状态: :{s_clr}[{row['status']}]")
            if row['status'] == "有效":
                if c3.button("撤回", key=f"rev_{row['id']}"):
                    withdraw_req(row['id'])
                    st.rerun()
            st.divider()

if st.button("🔄 同步最新云端数据"):
    st.rerun()
