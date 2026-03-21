import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta, date
from streamlit_gsheets import GSheetsConnection
import pytz
import calendar
import os

# --- 1. 系统配置与时区 ---
china_tz = pytz.timezone('Asia/Shanghai')

def get_now():
    return datetime.now(china_tz)

st.set_page_config(page_title="客服考勤管理系统 v18.7", layout="wide", page_icon="⚖️")

# 界面风格锁定
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
# 【关键更新】：根据要求调整了 陈鹤舞 与 都 娟 的排位顺序
STAFF = ["郭战勇", "徐远远", "陈君琳", "陈鹤舞", "都 娟", "顾凌海"]
FIXED_HOUR = 8.5 

# --- 2. 数据库逻辑 (Google Sheets) ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_db():
    try:
        data = conn.read(ttl=0)
        df = data.dropna(how="all")
        df['date'] = pd.to_datetime(df['date']).dt.date
        return df
    except Exception:
        return pd.DataFrame(columns=["id", "name", "type", "date", "start_t", "end_t", "hours", "reason", "status", "submit_time"])

def save_data_to_gsheets(new_row_dict):
    df = load_db()
    new_entry = {}
    for k, v in new_row_dict.items():
        if isinstance(v, (date, time, datetime)):
            new_entry[k] = v.strftime('%Y-%m-%d %H:%M:%S') if isinstance(v, datetime) else v.strftime('%Y-%m-%d') if isinstance(v, date) else v.strftime('%H:%M:%S')
        else:
            new_entry[k] = str(v)
    new_row_df = pd.DataFrame([new_entry])
    updated_df = pd.concat([df, new_row_df], ignore_index=True)
    for col in updated_df.columns:
        if col == 'hours': updated_df[col] = pd.to_numeric(updated_df[col], errors='coerce').fillna(0.0)
        elif col == 'id': updated_df[col] = pd.to_numeric(updated_df[col], errors='coerce').fillna(0).astype(int)
        else: updated_df[col] = updated_df[col].astype(str).replace(['nan', 'None', '<NA>', 'NaT'], '')
    conn.update(data=updated_df)

def withdraw_req(req_id):
    df = load_db()
    df.loc[df['id'].astype(str) == str(req_id), 'status'] = "已撤回"
    for col in df.columns:
        if col not in ['hours', 'id']:
            df[col] = df[col].astype(str).replace(['nan', 'None', '<NA>', 'NaT'], '')
    conn.update(data=df)

# --- 3. 核心排班算法 ---
def get_original_duty(name, date_obj):
    if date_obj < START_DATE: return "未开始"
    weekday = date_obj.weekday()
    days_diff = (date_obj - START_DATE).days

    if name == "郭战勇" and weekday == 2: return "休息"
    if name == "徐远远" and weekday == 5: return "休息"
    if name not in ["郭战勇", "徐远远"] and weekday == 6: return "休息"

    working_staff = []
    for s in STAFF:
        if s == "郭战勇" and weekday == 2: continue
        if s == "徐远远" and weekday == 5: continue
        if s not in ["郭战勇", "徐远远"] and weekday == 6: continue
        working_staff.append(s)
    
    shift_offset = (days_diff + (days_diff // 7)) % len(working_staff)
    rotated_staff = working_staff[shift_offset:] + working_staff[:shift_offset]
    current_staff_pos = rotated_staff.index(name)

    if weekday in [0, 1, 3, 4]: # 2早, 2延, 2晚
        if current_staff_pos < 2: return "早班"
        elif current_staff_pos < 4: return "延迟班"
        else: return "晚值班"
    elif weekday in [2, 5]: # 2早, 1延, 2晚
        if current_staff_pos < 2: return "早班"
        elif current_staff_pos < 3: return "延迟班"
        else: return "晚值班"
    elif weekday == 6: # 1早, 1晚
        if current_staff_pos < 1: return "早班"
        else: return "晚值班"
    return "早班"

def get_final_duty(name, date_obj, db_df):
    orig = get_original_duty(name, date_obj)
    if db_df.empty: return orig
    swaps = db_df[(db_df['date'] == date_obj) & (db_df['type'] == "换班") & (db_df['status'] == "有效")]
    for _, row in swaps.iterrows():
        applicant = row['name']
        target = str(row['reason']).replace("与", "").replace("换班", "").strip()
        if name == applicant: return get_original_duty(target, date_obj)
        if name == target: return get_original_duty(applicant, date_obj)
    return orig

# --- 4. 实时状态判定 ---
def get_status_ui(name, name_idx, final_dtype, now_dt, db_df):
    now_t, now_d = now_dt.time(), now_dt.date()
    if not db_df.empty:
        active = db_df[(db_df['name']==name) & (db_df['date']==now_d) & (db_df['status']=="有效") & (db_df['type'] != "换班")]
        for _, r in active.iterrows():
            try:
                st_t = datetime.strptime(str(r['start_t'])[:8], "%H:%M:%S").time()
                en_t = datetime.strptime(str(r['end_t'])[:8], "%H:%M:%S").time()
                if st_t <= now_t <= en_t: return f"🔴 {r['type']}中", "red"
            except: continue

    if final_dtype in ["休息", "未开始"]: return "😴 休息中", "grey"
    
    if final_dtype == "早班":
        if time(12,0) <= now_t <= time(13,30): return "🍱 午休中", "orange"
        if time(9,0) <= now_t <= time(19,0): return "🏢 在司值班", "green"
    elif final_dtype == "延迟班":
        if time(13,0) <= now_t <= time(14,30): return "🍱 午休中", "orange"
        if time(10,0) <= now_t <= time(20,0): return "🏢 在司值班", "green"
    elif final_dtype == "晚值班":
        if time(12,30) <= now_t <= time(19,0): return "🏢 在司值班", "green"
        if time(19,0) <= now_t <= time(20,0): return "🚗 通勤路上", "blue"
        if time(20,0) <= now_t <= time(22,0): return "🏠 居家远程", "green"
    return "🌙 已下班", "red"

# --- 5. 页面渲染 ---
now_beijing = get_now()
db_full = load_db()

st.title("🛡️ 客服部智能化管理系统 v18.7")

with st.sidebar:
    st.header("📋 行政与换班申请")
    with st.form("leave_form", clear_on_submit=True):
        l_name = st.selectbox("人员姓名", STAFF, key="ln")
        l_type = st.radio("类型", ["事假", "病假", "调休"], horizontal=True)
        l_date = st.date_input("日期", value=now_beijing.date())
        c1, c2 = st.columns(2)
        l_t1 = c1.time_input("开始", value=time(9,0))
        l_t2 = c2.time_input("结束", value=time(18,0))
        l_reason = st.text_input("备注信息")
        if st.form_submit_button("提交考勤申请"):
            h = round((datetime.combine(l_date, l_t2) - datetime.combine(l_date, l_t1)).total_seconds()/3600, 1)
            new_id = int(db_full['id'].max()+1) if not db_full.empty else 1001
            save_data_to_gsheets({"id": new_id, "name": l_name, "type": l_type, "date": l_date, "start_t": l_t1, "end_t": l_t2, "hours": h, "reason": l_reason, "status": "有效", "submit_time": now_beijing})
            st.rerun()
    
    with st.form("swap_form", clear_on_submit=True):
        s_name = st.selectbox("换班申请人 (我)", STAFF, key="sn")
        target = st.selectbox("换班目标人 (对方)", [s for s in STAFF if s != s_name])
        s_date = st.date_input("换班日期", value=now_beijing.date(), key="sd")
        if st.form_submit_button("提交换班申请"):
            new_id = int(db_full['id'].max()+1) if not db_full.empty else 1001
            save_data_to_gsheets({"id": new_id, "name": s_name, "type": "换班", "date": s_date, "start_t": "00:00:00", "end_t": "23:59:59", "hours": 0.0, "reason": f"与 {target} 换班", "status": "有效", "submit_time": now_beijing})
            st.rerun()

tabs = st.tabs(["🟢 实时监控", "👤 个人月度表", "📅 周度全表", "💰 计薪汇总", "🔍 记录管理"])

# Tab 1: 实时监控
with tabs[0]:
    st.subheader(f"⏱️ 北京时间: {now_beijing.strftime('%H:%M:%S')}")
    cols = st.columns(6)
    for i, name in enumerate(STAFF):
        f_dt = get_final_duty(name, now_beijing.date(), db_full)
        txt, clr = get_status_ui(name, i, f_dt, now_beijing, db_full)
        with cols[i]:
            st.write(f"**{name}**")
            st.caption(f_dt)
            if clr == "green": st.success(txt)
            elif clr == "orange": st.warning(txt)
            elif clr == "red": st.error(txt)
            elif clr == "blue": st.info(txt)
            else: st.write(txt)

# Tab 2: 个人月度表
with tabs[1]:
    st.subheader("👤 个人排班日历")
    i_c1, i_c2, i_c3 = st.columns(3)
    t_staff = i_c1.selectbox("查看客服", STAFF, key="is_p")
    t_year = i_c2.selectbox("统计年份", [2026, 2027], key="iy_p")
    t_month = i_c3.selectbox("统计月份", range(1, 13), index=now_beijing.month-1, key="im_p")
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(t_year, t_month)
    db_v = db_full[db_full['status']=="有效"] if not db_full.empty else pd.DataFrame()
    header_cols = st.columns(7)
    for idx, d_n in enumerate(["一","二","三","四","五","六","日"]): header_cols[idx].markdown(f"<center><b>周{d_n}</b></center>", unsafe_allow_html=True)
    for week in weeks:
        cols = st.columns(7)
        for i, d in enumerate(week):
            if d.month == t_month:
                f_dt = get_final_duty(t_staff, d, db_full)
                is_today = "calendar-today" if d == now_beijing.date() else ""
                with cols[i]:
                    st.markdown(f"<div class='calendar-cell {is_today}'><div style='font-size:1.1em; font-weight:bold;'>{d.day}</div><div style='color:#004085; margin-top:5px; font-weight:bold;'>{'休' if f_dt=='休息' else f_dt}</div></div>", unsafe_allow_html=True)
                    if f_dt != "休息":
                        if f_dt == "早班": l_t_str = "🍱 12:00"
                        elif f_dt == "延迟班": l_t_str = "🍱 13:00"
                        else: l_t_str = "🍱 无中午休"
                        st.caption(l_t_str)
                        if not db_v.empty:
                            day_l = db_v[(db_v['name']==t_staff) & (db_v['date']==d) & (db_v['type'] != "换班")]
                            for _, r in day_l.iterrows():
                                st.markdown(f":{'red' if r['type']=='事假' else 'blue'}[{r['type']}]")
            else: cols[i].write("")

# Tab 3: 周度全表
with tabs[2]:
    st.subheader("📅 周度班次与工时汇总")
    mon = now_beijing.date() - timedelta(days=now_beijing.weekday())
    w_dates = [mon + timedelta(days=i) for i in range(7)]
    w_res = []
    db_v = db_full[db_full['status']=="有效"] if not db_full.empty else pd.DataFrame()
    for name in STAFF:
        row = {"姓名": name}; theoretical = 0.0; deduct = 0.0
        for d in w_dates:
            f_dt = get_final_duty(name, d, db_full)
            theoretical += FIXED_HOUR if f_dt != "休息" else 0.0
            l_h = db_v[(db_v['name']==name) & (db_v['date']==d) & (db_v['type']=="事假")]['hours'].sum()
            deduct += l_h
            row[d.strftime("%m-%d\n%a")] = f"{f_dt}" + (f"\n(假:{round(l_h,1)}h)" if l_h > 0 else "")
        row["理论工时"] = f"{round(theoretical, 1)}h"; row["实到工时"] = f"{round(theoretical - deduct, 1)}h"
        w_res.append(row)
    st.dataframe(pd.DataFrame(w_res), use_container_width=True, hide_index=True)
    st.markdown("---")
    st.markdown("##### 📝 班次定义说明\n- **早班**: 09:00-19:00 (午休 12:00-13:30)\n- **延迟班**: 10:00-20:00 (午休 13:00-14:30)\n- **晚值班**: 12:30-19:00(在司) + 20:00-22:00(居家)")

# Tab 4: 计薪汇总
with tabs[3]:
    st.subheader("💰 月度计薪汇总")
    m_y = st.selectbox("年份", [2026, 2027], key="salary_y")
    m_m = st.selectbox("月份", range(1, 13), index=now_beijing.month-1, key="salary_m")
    curr_m_days = calendar.monthrange(m_y, m_m)[1]
    m_days = [datetime(m_y, m_m, d).date() for d in range(1, curr_m_days + 1) if datetime(m_y, m_m, d).date() >= START_DATE]
    m_summary = []
    for name in STAFF:
        act_days = sum([1 for d in m_days if get_final_duty(name, d, db_full) != "休息"])
        std_h = round(act_days * FIXED_HOUR, 1)
        pers_h = round(db_v[(db_v['name']==name) & (pd.to_datetime(db_v['date']).dt.month==m_m) & (db_v['type']=="事假")]['hours'].sum(), 1)
        m_summary.append({"姓名": name, "实到天数": act_days, "理论工时": f"{std_h}h", "事假扣除": f"-{pers_h}h", "计薪工时": f"{round(max(0.0, std_h - pers_h),1)}h"})
    st.table(pd.DataFrame(m_summary))

# Tab 5: 管理记录
with tabs[4]:
    st.subheader("🔍 流水记录中心")
    f_month = st.selectbox("查询月份", range(1, 13), index=now_beijing.month-1)
    if not db_full.empty:
        df_show = db_full.copy()
        df_show['month'] = pd.to_datetime(df_show['date']).dt.month
        df_show = df_show[df_show['month'] == f_month].sort_values("date", ascending=False)
        for _, r in df_show.iterrows():
            c1, c2, c3 = st.columns([1, 5, 1])
            c1.code(r['id'])
            rec_icon = "🔄" if r['type'] == "换班" else "📝"
            s_clr = "green" if r['status']=="有效" else "red"
            c2.markdown(f"{rec_icon} **{r['name']}** | {r['date']} | {r['type']} | {r['reason']}")
            if str(r['status']) == "有效":
                if c3.button("撤回", key=f"rev_{r['id']}"):
                    withdraw_req(r['id'])
                    st.rerun()
            st.divider()

if st.button("🔄 同步云端数据"): st.rerun()
