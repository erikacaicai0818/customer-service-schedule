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

st.set_page_config(page_title="客服考勤综合管理系统 v20.0", layout="wide", page_icon="⚖️")

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
STAFF = ["郭战勇", "徐远远", "陈君琳", "陈鹤舞", "都 娟", "顾凌海"]
FIXED_HOUR = 8.5 

# --- 【配置：柠檬账号负责人名单】 ---
LEMON_BACKUP_LIST = {
    0: ["顾凌海", "都 娟"],   # 周一
    1: ["郭战勇", "都 娟"],   # 周二
    2: ["陈鹤舞", "陈君琳"],  # 周三
    3: ["顾凌海", "陈君琳"],  # 周四
    4: ["郭战勇", "都 娟"],   # 周五
    5: ["顾凌海", "郭战勇"],  # 周六
    6: ["郭战勇"]             # 周日
}

# --- 【配置：电话接线负责人名单】 ---
PHONE_DUTY_MAP = {
    0: "郭战勇", # 周一
    1: "陈鹤舞", # 周二
    2: "徐远远", # 周三
    3: "都 娟",   # 周四
    4: "顾凌海", # 周五
    5: "陈君琳", # 周六
    6: "徐远远"  # 周日
}

# 基础班次模板
BASE_DUTY_MAP = {
    "郭战勇": ["早班", "早班", "休息", "晚值班", "早班", "晚值班", "早班"],
    "徐远远": ["延迟班", "延迟班", "延迟班", "晚值班", "晚值班", "休息", "晚值班"],
    "陈鹤舞": ["延迟班", "早班", "早班", "早班", "晚值班", "晚值班", "休息"],
    "陈君琳": ["晚值班", "延迟班", "晚值班", "延迟班", "延迟班", "早班", "休息"],
    "都 娟": ["晚值班", "晚值班", "晚值班", "延迟班", "延迟班", "延迟班", "休息"],
    "顾凌海": ["早班", "晚值班", "早班", "早班", "早班", "早班", "休息"]
}

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
        else: new_entry[k] = str(v)
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
        if col not in ['hours', 'id']: df[col] = df[col].astype(str).replace(['nan', 'None', '<NA>', 'NaT'], '')
    conn.update(data=df)

# --- 3. 核心算法 ---
def get_original_duty(name, date_obj):
    if date_obj < START_DATE: return "未开始"
    weekday = date_obj.weekday()
    return BASE_DUTY_MAP.get(name, ["休息"]*7)[weekday]

def get_final_duty_after_swap(name, date_obj, db_df):
    orig = get_original_duty(name, date_obj)
    if db_df.empty: return orig
    swaps = db_df[(db_df['date'] == date_obj) & (db_df['type'] == "换班") & (db_df['status'] == "有效")]
    for _, row in swaps.iterrows():
        applicant = row['name']
        target = str(row['reason']).replace("与", "").replace("换班", "").strip()
        if name == applicant: return get_original_duty(target, date_obj)
        if name == target: return get_original_duty(applicant, date_obj)
    return orig

def get_status_ui(name, final_dtype, now_dt, db_df):
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
        if time(19,0) <= now_t <= time(20,0): return "🚗 通勤中", "blue"
        if time(20,0) <= now_t <= time(22,0): return "🏠 居家远程", "green"
    return "🌙 已下班", "red"

# --- 4. 界面渲染 ---
now_beijing = get_now()
db_full = load_db()

st.title("🛡️ 客服管理系统 v20.0 (电话接线与多周筛选版)")

with st.sidebar:
    st.header("📋 提交申请")
    with st.form("leave_form", clear_on_submit=True):
        l_name = st.selectbox("人员姓名", STAFF, key="ln")
        l_type = st.radio("类型", ["事假", "病假", "调休"], horizontal=True)
        l_date = st.date_input("日期", value=now_beijing.date())
        c1, c2 = st.columns(2)
        l_t1 = c1.time_input("开始时间", value=time(9,0))
        l_t2 = c2.time_input("结束时间", value=time(18,0))
        l_reason = st.text_input("备注事由")
        if st.form_submit_button("确认行政申请"):
            h = round((datetime.combine(l_date, l_t2) - datetime.combine(l_date, l_t1)).total_seconds()/3600, 1)
            new_id = int(db_full['id'].max()+1) if not db_full.empty else 1001
            save_data_to_gsheets({"id": new_id, "name": l_name, "type": l_type, "date": l_date, "start_t": l_t1, "end_t": l_t2, "hours": h, "reason": l_reason, "status": "有效", "submit_time": now_beijing})
            st.rerun()
    with st.form("swap_form", clear_on_submit=True):
        s_name = st.selectbox("申请人", STAFF, key="sn")
        target = st.selectbox("目标人", [s for s in STAFF if s != s_name])
        s_date = st.date_input("日期 ", value=now_beijing.date())
        if st.form_submit_button("提交全天换班"):
            new_id = int(db_full['id'].max()+1) if not db_full.empty else 1001
            save_data_to_gsheets({"id": new_id, "name": s_name, "type": "换班", "date": s_date, "start_t": "00:00:00", "end_t": "23:59:59", "hours": 0.0, "reason": f"与 {target} 换班", "status": "有效", "submit_time": now_beijing})
            st.rerun()

tabs = st.tabs(["🟢 实时监控", "👤 个人月度表", "📅 周度全表", "💰 计薪汇总", "🔍 记录管理"])

# Tab 1: 实时监控
with tabs[0]:
    st.subheader(f"⏱️ 实时看板 ({now_beijing.strftime('%H:%M:%S')})")
    cols = st.columns(6)
    for i, name in enumerate(STAFF):
        f_dt = get_final_duty_after_swap(name, now_beijing.date(), db_full)
        txt, clr = get_status_ui(name, f_dt, now_beijing, db_full)
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
    st.subheader("👤 个人出勤日历")
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
                f_dt = get_final_duty_after_swap(t_staff, d, db_full)
                orig_dt = get_original_duty(t_staff, d)
                is_today = "calendar-today" if d == now_beijing.date() else ""
                
                # 标注逻辑
                star = "⭐" if t_staff in LEMON_BACKUP_LIST.get(d.weekday(), []) else ""
                phone = "📞" if t_staff == PHONE_DUTY_MAP.get(d.weekday()) else ""
                
                with cols[i]:
                    disp = f"{f_dt}"
                    if f_dt != orig_dt: disp = f"🔄{f_dt}"
                    st.markdown(f"<div class='calendar-cell {is_today}'><div style='font-size:1.1em; font-weight:bold;'>{d.day} {star}{phone}</div><div style='color:#004085; margin-top:5px; font-weight:bold;'>{'休' if f_dt=='休息' else disp}</div></div>", unsafe_allow_html=True)
                    if f_dt != "休息":
                        l_t = "12:00" if f_dt == "早班" else "13:00" if f_dt == "延迟班" else "无休"
                        st.caption(f"🍱{l_t}")
                        if not db_v.empty:
                            day_l = db_v[(db_v['name']==t_staff) & (db_v['date']==d) & (db_v['type'] != "换班")]
                            for _, r in day_l.iterrows():
                                st.markdown(f":{'red' if r['type']=='事假' else 'blue'}[{r['type']}]")
            else: cols[i].write("")

# --- Tab 3: 周度全表 (新增周筛选器) ---
with tabs[2]:
    st.subheader("📅 周度排班追踪表")
    
    # 周筛选器
    c_m, c_w = st.columns(2)
    sel_month = c_m.selectbox("选择月份 ", range(1, 13), index=now_beijing.month-1, key="sel_m_tab3")
    
    # 计算选中月份的所有周
    _, days_in_month = calendar.monthrange(2026, sel_month)
    month_dates = [date(2026, sel_month, d) for d in range(1, days_in_month + 1)]
    weeks = []
    current_week = []
    for d in month_dates:
        current_week.append(d)
        if d.weekday() == 6 or d.day == days_in_month:
            weeks.append(current_week)
            current_week = []
    
    week_options = [f"第{i+1}周 ({w[0].strftime('%m/%d')} - {w[-1].strftime('%m/%d')})" for i, w in enumerate(weeks)]
    sel_week_idx = c_w.selectbox("选择周数 ", range(len(week_options)), format_func=lambda x: week_options[x], key="sel_w_tab3")
    
    target_week_dates = weeks[sel_week_idx]
    
    w_res = []
    db_v = db_full[db_full['status']=="有效"] if not db_full.empty else pd.DataFrame()
    for name in STAFF:
        row = {"姓名": name}; theo_h = 0.0; real_h = 0.0
        for d in target_week_dates:
            orig = get_original_duty(name, d)
            after_swap = get_final_duty_after_swap(name, d, db_v)
            leave_recs = db_v[(db_v['name']==name) & (db_v['date']==d) & (db_v['type']!="换班")]
            
            # 标注判定
            star = "⭐" if name in LEMON_BACKUP_LIST.get(d.weekday(), []) else ""
            phone = "📞" if name == PHONE_DUTY_MAP.get(d.weekday()) else ""
            icons = f"{star}{phone}"
            
            day_theo = FIXED_HOUR if after_swap != "休息" else 0.0
            theo_h += day_theo
            cell_txt = f"🔄{after_swap}{icons}\n(原:{orig})" if after_swap != orig else f"{after_swap}{icons}"
            
            if not leave_recs.empty:
                l_h = round(leave_recs['hours'].sum(), 1)
                l_type = leave_recs.iloc[0]['type']
                if l_type == "事假": real_h += (day_theo - l_h)
                else: real_h += day_theo
                if l_h >= FIXED_HOUR: cell_txt = f"🚫{l_type}{icons}\n(原:{orig})"
                else: cell_txt += f"\n(-{l_h}h {l_type})"
            else: real_h += day_theo
            row[d.strftime("%m-%d\n%a")] = cell_txt
        row["理论工时"] = f"{round(theo_h, 1)}h"; row["计薪工时"] = f"{round(real_h, 1)}h"
        w_res.append(row)
    st.dataframe(pd.DataFrame(w_res), use_container_width=True, hide_index=True)
    
    st.markdown("---")
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.markdown("##### 📝 班次定义说明")
        st.markdown("""
        - **早班**: 09:00 - 19:00（午休 12:00 - 13:30）
        - **延迟班**: 10:00 - 20:00（午休 13:00 - 14:30）
        - **晚值班**: 12:30 - 19:00（在司）+ 20:00 - 22:00（居家），中午无休息。
        """)
    with col_info2:
        st.markdown("##### 🚩 负责人标注定义")
        st.markdown("""
        - **⭐ (星星)**：负责登录“柠檬”账号。远远不在时，由其负责。
        - **📞 (电话)**：当日**电话接线负责人**，负责所有来电处理。
        """)

# Tab 4: 计薪汇总
with tabs[3]:
    st.subheader("💰 月度计薪汇总汇总")
    m_y = st.selectbox("年份 ", [2026, 2027], key="sal_y")
    m_m = st.selectbox("月份 ", range(1, 13), index=now_beijing.month-1, key="sal_m")
    m_days = [date(m_y, m_m, d) for d in range(1, calendar.monthrange(m_y, m_m)[1] + 1) if date(m_y, m_m, d) >= START_DATE]
    m_summary = []
    for name in STAFF:
        act_wd = sum([1 for d in m_days if get_final_duty_after_swap(name, d, db_v) != "休息"])
        std = round(act_wd * FIXED_HOUR, 1)
        pers = round(db_v[(db_v['name']==name) & (pd.to_datetime(db_v['date']).dt.month==m_m) & (pd.to_datetime(db_v['date']).dt.year==m_y) & (db_v['type']=="事假")]['hours'].sum(), 1)
        m_summary.append({"姓名": name, "实到天数": act_wd, "理论总工时": f"{std}h", "事假扣除": f"-{pers}h", "应发计薪工时": f"{round(max(0.0, std - pers),1)}h"})
    st.table(pd.DataFrame(m_summary))

# Tab 5: 记录管理
with tabs[4]:
    st.subheader("🔍 流水记录查询与回撤")
    f_month = st.selectbox("查看月份  ", range(1, 13), index=now_beijing.month-1)
    if not db_full.empty:
        df_show = db_full.copy()
        df_show['month'] = pd.to_datetime(df_show['date']).dt.month
        df_show = df_show[df_show['month'] == f_month].sort_values("date", ascending=False)
        for _, r in df_show.iterrows():
            c1, c2, c3 = st.columns([1, 5, 1])
            c1.code(r['id'])
            rec_icon = "🔄" if r['type'] == "换班" else "🚫" if r['hours']>=8.5 else "📝"
            s_clr = "green" if r['status']=="有效" else "red"
            c2.markdown(f"{rec_icon} **{r['name']}** | {r['date']} | {r['type']} | {r['reason']}")
            if str(r['status']) == "有效" and c3.button("撤回", key=f"rev_{r['id']}"):
                withdraw_req(r['id']); st.rerun()
            st.divider()

if st.button("🔄 同步云端数据"): st.rerun()
