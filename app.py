import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
from streamlit_gsheets import GSheetsConnection
import pytz
import calendar
import os

# --- 1. 系统配置 ---
china_tz = pytz.timezone('Asia/Shanghai')
def get_now():
    return datetime.now(china_tz)

st.set_page_config(page_title="客服考勤管理系统 v17", layout="wide", page_icon="⚖️")

# 界面风格锁定：明亮模式 + 日历美化
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #31333F; }
    .calendar-cell {
        background-color: #F0F7FF;
        border: 1px solid #CCE5FF;
        border-radius: 8px;
        padding: 8px;
        margin-bottom: 5px;
        min-height: 100px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.03);
    }
    .calendar-today { background-color: #FFF9DB; border: 1px solid #FFE066; }
    </style>
    """, unsafe_allow_html=True)

# 核心常量
START_DATE = datetime(2026, 3, 1).date()
STAFF = ["郭战勇", "徐远远", "陈鹤舞", "都 娟", "陈君琳", "顾凌海"]
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

# --- 2. 数据库连接与安全更新逻辑 ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_db():
    try:
        data = conn.read(ttl=0)
        df = data.dropna(how="all")
        df['date'] = pd.to_datetime(df['date']).dt.date
        return df
    except:
        return pd.DataFrame(columns=["id", "name", "type", "date", "start_t", "end_t", "hours", "reason", "status", "submit_time"])

def save_data_to_gsheets(new_row_dict):
    """通用的安全保存函数，强制转换所有数据为字符串以防止 UnsupportedOperationError"""
    df = load_db()
    # 转换日期和时间为字符串
    new_row_dict['date'] = str(new_row_dict['date'])
    new_row_dict['submit_time'] = str(new_row_dict['submit_time'])
    
    new_row_df = pd.DataFrame([new_row_dict])
    updated_df = pd.concat([df, new_row_df], ignore_index=True)
    
    # 核心修复：上传前确保 DataFrame 中没有 Python 对象，全是基础类型/字符串
    updated_df['date'] = updated_df['date'].astype(str)
    conn.update(data=updated_df)

def withdraw_req(req_id):
    df = load_db()
    df.loc[df['id'] == req_id, 'status'] = "已撤回"
    # 上传前转换日期列为字符串
    df['date'] = df['date'].astype(str)
    conn.update(data=df)

# --- 3. 排班核心算法 (做六休一) ---
def is_original_working(name, date_obj):
    weekday = date_obj.weekday()
    if name == "郭战勇" and weekday == 2: return False
    if name == "徐远远" and weekday == 5: return False
    if name not in ["郭战勇", "徐远远"] and weekday == 6: return False
    return True

def get_original_duty(name, date_obj):
    if date_obj < START_DATE: return "未开始"
    if not is_original_working(name, date_obj): return "休息"
    
    weekday = date_obj.weekday()
    working_staff = [s for s in STAFF if is_original_working(s, date_obj)]
    num_late = 1 if weekday == 6 else 2
    seed = date_obj.day + date_obj.month
    late_team = [working_staff[(seed + i) % len(working_staff)] for i in range(num_late)]
    
    if name in late_team: return "晚值班"
    
    yesterday = date_obj - timedelta(days=1)
    if yesterday >= START_DATE:
        yw = yesterday.weekday()
        yw_s = [s for s in STAFF if is_original_working(s, yesterday)]
        if yw_s:
            y_seed = yesterday.day + yesterday.month
            y_late = [yw_s[(y_seed + i) % len(yw_s)] for i in range(1 if yw==6 else 2)]
            if name in y_late: return "延迟班"
    return "早班"

def get_final_duty(name, date_obj, db_df):
    """核心：判定是否有全天换班"""
    orig_duty = get_original_duty(name, date_obj)
    # 查找当天的有效换班记录
    swaps = db_df[(db_df['date'] == date_obj) & (db_df['type'] == "换班") & (db_df['status'] == "有效")]
    for _, row in swaps.iterrows():
        applicant = row['name']
        target = row['reason'].replace("与", "").replace("换班", "").strip()
        if name == applicant: return get_original_duty(target, date_obj)
        if name == target: return get_original_duty(applicant, date_obj)
    return orig_duty

# --- 4. 实时状态判定 ---
def get_status_ui(name, name_idx, final_dtype, now_dt, db_df):
    now_t, now_d = now_dt.time(), now_dt.date()
    # 检查行政申请（不含换班）
    active = db_df[(db_df['name']==name) & (db_df['date']==now_d) & (db_df['status']=="有效") & (db_df['type'] != "换班")]
    for _, r in active.iterrows():
        st_t = datetime.strptime(str(r['start_t']), "%H:%M:%S").time()
        en_t = datetime.strptime(str(r['end_t']), "%H:%M:%S").time()
        if st_t <= now_t <= en_t: return f"🔴 {r['type']}中", "red"

    if final_dtype in ["休息", "未开始"]: return "😴 休息中", "grey"
    
    if final_dtype != "晚值班":
        l_range = (time(12,45), time(14,15)) if now_d.weekday()==6 else (LUNCH_CONFIG[name_idx]['start'], LUNCH_CONFIG[name_idx]['end'])
        if l_range[0] <= now_t <= l_range[1]: return f"🍱 午休中({l_range[0].strftime('%H:%M')})", "orange"

    if final_dtype == "晚值班":
        if now_t < time(12,30): return "⏳ 等待上班", "grey"
        if time(12,30) <= now_t <= time(19,0): return "🏢 在司值班", "green"
        if time(19,0) <= now_t <= time(20,0): return "🚗 通勤中", "blue"
        if time(20,0) <= now_t <= time(22,0): return "🏠 居家远程", "green"
    elif final_dtype == "延迟班":
        if time(10,0) <= now_t <= time(20,0): return "🏢 在司值班", "green"
    elif final_dtype == "早班":
        if time(9,0) <= now_t <= time(19,0): return "🏢 在司值班", "green"
    return "🌙 已下班", "red"

# --- 5. 界面布局 ---
now = get_now()
db_full = load_db()

st.title("🛡️ 客服部考勤与换班管理系统 v17")

with st.sidebar:
    # 模块一：行政请假申请
    st.header("📋 请假/调休申请")
    with st.form("leave_form", clear_on_submit=True):
        l_name = st.selectbox("人员姓名", STAFF, key="ln")
        l_type = st.radio("类型", ["事假", "病假", "调休"], horizontal=True, key="lt")
        l_date = st.date_input("日期", value=now.date(), key="ld")
        c1, c2 = st.columns(2)
        l_t1 = c1.time_input("开始", value=time(9,0), key="lt1")
        l_t2 = c2.time_input("结束", value=time(18,0), key="lt2")
        l_reason = st.text_input("具体事由", key="lr")
        if st.form_submit_button("提交行政申请"):
            h = round((datetime.combine(l_date, l_t2) - datetime.combine(l_date, l_t1)).total_seconds()/3600, 1)
            df = load_db()
            new_id = int(df['id'].max()+1) if not df.empty else 1001
            save_data_to_gsheets({
                "id": new_id, "name": l_name, "type": l_type, "date": l_date,
                "start_t": l_t1.strftime('%H:%M:%S'), "end_t": l_t2.strftime('%H:%M:%S'),
                "hours": h, "reason": l_reason, "status": "有效", "submit_time": get_now()
            })
            st.success("请假申请已同步云端")
            st.rerun()

    st.divider()
    
    # 模块二：换班申请（独立）
    st.header("🔄 全天换班申请")
    with st.form("swap_form", clear_on_submit=True):
        s_name = st.selectbox("申请人 (我)", STAFF, key="sn")
        target = st.selectbox("换班目标人 (对方)", [s for s in STAFF if s != s_name], key="st")
        s_date = st.date_input("换班日期", value=now.date(), key="sd")
        if st.form_submit_button("提交全天换班"):
            df = load_db()
            new_id = int(df['id'].max()+1) if not df.empty else 1001
            save_data_to_gsheets({
                "id": new_id, "name": s_name, "type": "换班", "date": s_date,
                "start_t": "00:00:00", "end_t": "23:59:59",
                "hours": 0.0, "reason": f"与 {target} 换班", "status": "有效", "submit_time": get_now()
            })
            st.success(f"换班成功！已调换 {s_name} 与 {target} 的班次")
            st.rerun()

# 标签页
tabs = st.tabs(["🟢 实时监控", "👤 个人月度表", "📅 周度全表", "💰 计薪汇总", "🔍 记录管理"])

# Tab 1: 实时监控
with tabs[0]:
    st.subheader(f"⏱️ 北京时间: {now.strftime('%H:%M:%S')}")
    cols = st.columns(6)
    on_duty = 0
    for i, name in enumerate(STAFF):
        f_dt = get_final_duty(name, now.date(), db_full)
        txt, clr = get_status_ui(name, i, f_dt, now, db_full)
        if clr == "green": on_duty += 1
        with cols[i]:
            st.write(f"**{name}**")
            st.caption(f_dt)
            if clr == "green": st.success(txt)
            elif clr == "orange": st.warning(txt)
            elif clr == "red": st.error(txt)
            elif clr == "blue": st.info(txt)
            else: st.write(txt)
    st.info(f"当前在岗办公人数：`{on_duty}` 名")

# Tab 2: 个人月度表 (UI 优化版)
with tabs[1]:
    st.subheader("👤 个人排班日历")
    i_c1, i_c2, i_c3 = st.columns(3)
    t_staff = i_c1.selectbox("查看客服", STAFF, key="is")
    t_year = i_c2.selectbox("年份", [2026, 2027], key="iy")
    t_month = i_c3.selectbox("月份", range(1, 13), index=now.month-1, key="im")
    
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(t_year, t_month)
    db_v = db_full[db_full['status']=="有效"]
    
    header_cols = st.columns(7)
    for idx, d_n in enumerate(["一","二","三","四","五","六","日"]):
        header_cols[idx].markdown(f"<center><b>周{d_n}</b></center>", unsafe_allow_html=True)
    
    s_idx = STAFF.index(t_staff)
    for week in weeks:
        cols = st.columns(7)
        for i, d in enumerate(week):
            if d.month == t_month:
                f_dt = get_final_duty(t_staff, d, db_full)
                is_today = "calendar-today" if d == now.date() else ""
                with cols[i]:
                    st.markdown(f"""
                        <div class="calendar-cell {is_today}">
                            <div style='font-size:1.1em; font-weight:bold;'>{d.day}</div>
                            <div style='color:#004085; margin-top:5px; font-weight:bold;'>{'休' if f_dt=='休息' else f_dt}</div>
                        </div>
                    """, unsafe_allow_html=True)
                    if f_dt != "休息":
                        l_t = "12:45" if d.weekday()==6 else LUNCH_CONFIG[s_idx]['start'].strftime('%H:%M')
                        st.caption(f"🍱{l_t}")
                        day_l = db_v[(db_v['name']==t_staff) & (db_v['date']==d) & (db_v['type'] != "换班")]
                        for _, r in day_l.iterrows():
                            c = "red" if r['type']=="事假" else "blue"
                            st.markdown(f":{c}[{r['type']}]")
            else: cols[i].write("")

# Tab 3: 周度全表
with tabs[2]:
    mon = now.date() - timedelta(days=now.weekday())
    w_dates = [mon + timedelta(days=i) for i in range(7)]
    w_res = []
    db_v = db_full[db_full['status']=="有效"]
    for name in STAFF:
        row = {"姓名": name}
        for d in w_dates:
            f_dt = get_final_duty(name, d, db_full)
            l_h = db_v[(db_v['name']==name) & (db_v['date']==d) & (db_v['type']!="换班")]['hours'].sum()
            row[d.strftime("%m-%d\n%a")] = f"{f_dt}" + (f"\n(假:{l_h}h)" if l_h > 0 else "")
        w_res.append(row)
    st.dataframe(pd.DataFrame(w_res), use_container_width=True, hide_index=True)

# Tab 4: 计薪汇总
with tabs[3]:
    st.subheader("💰 月度计薪汇总 (仅事假扣费)")
    m_y = st.selectbox("筛选年份", [2026, 2027], key="my")
    m_m = st.selectbox("筛选月份", range(1, 13), index=now.month-1, key="mm")
    _, d_cnt = calendar.monthrange(m_y, m_m)
    m_dates = [datetime(m_y, m_m, d).date() for d in range(1, d_cnt+1) if datetime(m_y, m_m, d).date() >= START_DATE]
    db_v = db_full[db_full['status']=="有效"]
    
    m_summary = []
    for name in STAFF:
        actual_work_days = sum([1 for d in m_dates if get_final_duty(name, d, db_full) != "休息"])
        standard_h = round(actual_work_days * FIXED_HOUR, 1)
        recs = db_v[(db_v['name']==name) & (pd.to_datetime(db_v['date']).dt.month==m_m) & (pd.to_datetime(db_v['date']).dt.year==m_y)]
        pers_h = round(recs[recs['type'] == "事假"]['hours'].sum(), 1)
        paid_h = round(recs[recs['type'].isin(["病假", "调休"])]['hours'].sum(), 1)
        final_h = round(max(0.0, standard_h - pers_h), 1)
        m_summary.append({
            "姓名": name, "实到天数": actual_work_days, "理论工时": f"{standard_h}h",
            "事假扣除": f"-{pers_h}h", "病假/调休(不扣)": f"{paid_h}h", "计薪总工时": f"{final_h}h"
        })
    st.table(pd.DataFrame(m_summary))

# Tab 5: 管理记录
with tabs[4]:
    st.subheader("🔍 流水管理")
    f_m = st.selectbox("按月查看记录", range(1, 13), index=now.month-1)
    df_show = db_full[pd.to_datetime(db_full['date']).dt.month == f_m].sort_values("date", ascending=False)
    for _, row in df_show.iterrows():
        c1, c2, c3 = st.columns([1, 5, 1])
        c1.code(row['id'])
        s_clr = "green" if row['status']=="有效" else "red"
        c2.markdown(f"**{row['name']}** | {row['date']} | {row['type']} | {row['reason']}")
        if row['status'] == "有效":
            if c3.button("撤回", key=f"rev_{row['id']}"):
                withdraw_req(row['id'])
                st.rerun()
        st.divider()

if st.button("🔄 同步最新云端数据"):
    st.rerun()
