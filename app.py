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

st.set_page_config(page_title="客服考勤综合管理系统 v22.2", layout="wide", page_icon="⚖️")

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
    .calendar-holiday { background-color: #FFE3E3 !important; border: 1px solid #FFAAAA !important; }
    .calendar-today { background-color: #FFF9DB; border: 1px solid #FFE066; }
    </style>
    """, unsafe_allow_html=True)

# 核心常量
START_DATE = datetime(2026, 3, 1).date()
STAFF = ["郭战勇", "徐远远", "陈君琳", "陈鹤舞", "都 娟", "顾凌海"]
FIXED_HOUR = 8.5 

# --- 【配置：2026年法定节假日】 ---
HOLIDAYS_2026 = {
    date(2026, 1, 1): "元旦",
    date(2026, 2, 17): "春节", date(2026, 2, 18): "春节", date(2026, 2, 19): "春节",
    date(2026, 4, 4): "清明节", date(2026, 4, 5): "清明节", date(2026, 4, 6): "清明节",
    date(2026, 5, 1): "劳动节", date(2026, 5, 2): "劳动节", date(2026, 5, 3): "劳动节",
    date(2026, 6, 19): "端午节",
    date(2026, 9, 25): "中秋节",
    date(2026, 10, 1): "国庆节", date(2026, 10, 2): "国庆节", date(2026, 10, 3): "国庆节"
}

# 班次工时定义
SHIFT_HOURS_MAP = {"早班": 8.5, "延迟班": 8.5, "晚值班": 8.5, "值班晚班次": 3.0, "休息": 0.0}

# 柠檬 & 电话接线角色配置
LEMON_BACKUP_LIST = {0: ["顾凌海", "都 娟"], 1: ["郭战勇", "都 娟"], 2: ["陈鹤舞", "陈君琳"], 3: ["顾凌海", "陈君琳"], 4: ["郭战勇", "都 娟"], 5: ["顾凌海", "郭战勇"], 6: ["郭战勇"]}
PHONE_DUTY_MAP = {0: "郭战勇", 1: "陈鹤舞", 2: "徐远远", 3: "都 娟", 4: "顾凌海", 5: "陈君琳", 6: "徐远远"}

# 基础排班模板
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
    except:
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
    st.success(f"ID: {req_id} 记录已撤回")

# --- 3. 核心算法 ---
def get_original_duty(name, date_obj):
    if date_obj < START_DATE: return "未开始"
    if date_obj in HOLIDAYS_2026: return "休息" 
    weekday = date_obj.weekday()
    return BASE_DUTY_MAP.get(name, ["休息"]*7)[weekday]

def get_duty_after_holiday_app(name, date_obj, db_df):
    """判定经过节假日值班排班后的班次（过滤无效记录）"""
    duty = get_original_duty(name, date_obj)
    if not db_df.empty:
        holiday_duties = db_df[(db_df['date'] == date_obj) & (db_df['type'] == "节假日值班") & (db_df['status'] == "有效")]
        if not holiday_duties[holiday_duties['name'] == name].empty:
            duty = holiday_duties[holiday_duties['name'] == name].iloc[0]['reason']
    return duty

def get_final_duty(name, date_obj, db_df):
    """最终班次：原始 -> 节假日安排 -> 换班"""
    duty = get_original_duty(name, date_obj)
    if db_df.empty: return duty
    # A. 应用节假日值班 (必须状态为有效)
    duty = get_duty_after_holiday_app(name, date_obj, db_df)
    # B. 应用换班
    swaps = db_df[(db_df['date'] == date_obj) & (db_df['type'] == "换班") & (db_df['status'] == "有效")]
    for _, row in swaps.iterrows():
        target = str(row['reason']).replace("与", "").replace("换班", "").strip()
        if name == row['name']: return get_duty_after_holiday_app(target, date_obj, db_df)
        if name == target: return get_duty_after_holiday_app(row['name'], date_obj, db_df)
    return duty

def get_status_ui(name, final_dtype, now_dt, db_df):
    now_t, now_d = now_dt.time(), now_dt.date()
    if not db_df.empty:
        # 排除换班和节假日值班，查找行政请假状态
        active = db_df[(db_df['name']==name) & (db_df['date']==now_d) & (db_df['status']=="有效") & (~db_df['type'].isin(["换班", "节假日值班"]))]
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
    elif final_dtype == "值班晚班次":
        if time(19,0) <= now_t <= time(22,0): return "🏢 节假日值班", "green"
        
    return "🌙 已下班", "red"

# --- 4. 界面渲染 ---
now_beijing = get_now()
db_full = load_db()

st.title("🛡️ 客服综合管理系统 v22.2")

with st.sidebar:
    st.header("📋 考勤与换班申请")
    with st.form("leave_form", clear_on_submit=True):
        l_name = st.selectbox("人员姓名", STAFF, key="ln")
        l_type = st.radio("请假类型", ["事假", "病假", "调休"], horizontal=True)
        l_date = st.date_input("日期", value=now_beijing.date(), key="ld_apply")
        c1, c2 = st.columns(2)
        l_t1, l_t2 = c1.time_input("开始", value=time(9,0)), c2.time_input("结束", value=time(18,0))
        l_reason = st.text_input("备注信息")
        if st.form_submit_button("提交行政申请"):
            h = round((datetime.combine(l_date, l_t2) - datetime.combine(l_date, l_t1)).total_seconds()/3600, 1)
            save_data_to_gsheets({"id": 0, "name": l_name, "type": l_type, "date": l_date, "start_t": l_t1, "end_t": l_t2, "hours": h, "reason": l_reason, "status": "有效", "submit_time": now_beijing})
            st.rerun()

    with st.form("swap_form", clear_on_submit=True):
        s_name, target = st.selectbox("申请人", STAFF), st.selectbox("对方", STAFF)
        s_date = st.date_input("换班日期", value=now_beijing.date())
        if st.form_submit_button("确认全天换班"):
            save_data_to_gsheets({"id": 0, "name": s_name, "type": "换班", "date": s_date, "start_t": "00:00:00", "end_t": "00:00:00", "hours": 0.0, "reason": f"与 {target} 换班", "status": "有效", "submit_time": now_beijing})
            st.rerun()

    st.header("🏮 节假日值班安排")
    with st.form("holiday_form", clear_on_submit=True):
        h_name = st.selectbox("值班客服", STAFF)
        h_date = st.selectbox("选择法定假日", list(HOLIDAYS_2026.keys()), format_func=lambda x: f"{x} ({HOLIDAYS_2026[x]})")
        h_shift = st.selectbox("分配班次", ["早班", "延迟班", "晚值班", "值班晚班次"])
        if st.form_submit_button("确认节日值班安排"):
            save_data_to_gsheets({"id": 0, "name": h_name, "type": "节假日值班", "date": h_date, "start_t": "00:00:00", "end_t": "00:00:00", "hours": SHIFT_HOURS_MAP[h_shift], "reason": h_shift, "status": "有效", "submit_time": now_beijing})
            st.rerun()

tabs = st.tabs(["🟢 实时监控", "👤 个人月度表", "📅 周度全表", "💰 计薪汇总", "🔍 记录管理"])

# Tab 1
with tabs[0]:
    t_h = HOLIDAYS_2026.get(now_beijing.date())
    st.subheader(f"⏱️ 实时监控 ({now_beijing.strftime('%H:%M:%S')}{' | 🏮 '+t_h if t_h else ''})")
    cols = st.columns(6)
    for i, name in enumerate(STAFF):
        f_dt = get_final_duty(name, now_beijing.date(), db_full)
        txt, clr = get_status_ui(name, f_dt, now_beijing, db_full)
        with cols[i]:
            st.write(f"**{name}**"); st.caption(f_dt)
            if clr == "green": st.success(txt)
            elif clr == "orange": st.warning(txt)
            elif clr == "red": st.error(txt)
            elif clr == "blue": st.info(txt)
            else: st.write(txt)

# Tab 2
with tabs[1]:
    st.subheader("👤 客服个人日历")
    i1, i2, i3 = st.columns(3)
    t_s, t_y, t_m = i1.selectbox("查看人员", STAFF, key="ind_s"), i2.selectbox("年份 ", [2026, 2027], key="ind_y"), i3.selectbox("月份 ", range(1, 13), index=now_beijing.month-1, key="ind_m")
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(t_y, t_m)
    db_v = db_full[db_full['status']=="有效"] if not db_full.empty else pd.DataFrame()
    h_cols = st.columns(7)
    for idx, d_n in enumerate(["一","二","三","四","五","六","日"]): h_cols[idx].markdown(f"<center>周{d_n}</center>", unsafe_allow_html=True)
    for week in weeks:
        cols = st.columns(7)
        for i, d in enumerate(week):
            if d.month == t_m:
                f_dt = get_final_duty(t_s, d, db_full); orig = get_original_duty(t_s, d)
                h_name = HOLIDAYS_2026.get(d)
                is_t, is_h = ("calendar-today" if d==now_beijing.date() else ""), ("calendar-holiday" if h_name else "")
                star = "⭐" if t_s in LEMON_BACKUP_LIST.get(d.weekday(), []) else ""
                phone = "📞" if t_s == PHONE_DUTY_MAP.get(d.weekday()) else ""
                with cols[i]:
                    disp = f"{f_dt}"
                    if f_dt != orig: disp = f"🔄{f_dt}"
                    st.markdown(f"<div class='calendar-cell {is_t} {is_h}'><div style='font-size:1.1em; font-weight:bold;'>{d.day} {star}{phone}</div><div style='color:red; font-size:0.7em;'>{h_name if h_name else ''}</div><div style='color:#004085; font-weight:bold;'>{'休' if f_dt=='休息' else disp}</div></div>", unsafe_allow_html=True)
                    if f_dt != "休息":
                        l_t = "12:00" if f_dt=="早班" else "13:00" if f_dt=="延迟班" else "无"
                        st.caption(f"🍱{l_t}")
                        if not db_v.empty:
                            day_l = db_v[(db_v['name']==t_s) & (db_v['date']==d) & (~db_v['type'].isin(["换班", "节假日值班"]))]
                            for _, r in day_l.iterrows(): st.markdown(f":{'red' if r['type']=='事假' else 'blue'}[{r['type']}]")
            else: cols[i].write("")

# Tab 3
with tabs[2]:
    st.subheader("📅 周度排班追踪看板")
    cw1, cw2 = st.columns(2)
    s_m = cw1.selectbox("筛选月份", range(1, 13), index=now_beijing.month-1, key="wm_222")
    _, d_cnt = calendar.monthrange(2026, s_m); m_dates = [date(2026, s_m, d) for d in range(1, d_cnt + 1)]
    w_list, temp_w = [], []
    for d in m_dates:
        temp_w.append(d)
        if d.weekday() == 6 or d.day == d_cnt: w_list.append(temp_w); temp_w = []
    w_opts = [f"第{i+1}周 ({w[0].strftime('%m/%d')}-{w[-1].strftime('%m/%d')})" for i, w in enumerate(w_list)]
    target_dates = w_list[cw2.selectbox("选择周数", range(len(w_opts)), format_func=lambda x: w_opts[x])]
    w_res = []
    db_v = db_full[db_full['status']=="有效"] if not db_full.empty else pd.DataFrame()
    for name in STAFF:
        row = {"姓名": name}; theo_h, real_h = 0.0, 0.0
        for d in target_dates:
            orig, f_dt = get_original_duty(name, d), get_final_duty(name, d, db_v)
            l_recs = db_v[(db_v['name']==name) & (db_v['date']==d) & (~db_v['type'].isin(["换班", "节假日值班"]))]
            star = "⭐" if name in LEMON_BACKUP_LIST.get(d.weekday(), []) else ""
            phone = "📞" if name == PHONE_DUTY_MAP.get(d.weekday()) else ""
            h_mark = "(节)" if d in HOLIDAYS_2026 else ""
            day_theo = SHIFT_HOURS_MAP.get(f_dt, 0.0); theo_h += day_theo
            cell_txt = f"🔄{f_dt}{star}{phone}\n(原:{orig})" if f_dt != orig else f"{f_dt}{star}{phone}"
            if not l_recs.empty:
                l_h = round(l_recs['hours'].sum(), 1)
                real_h += (day_theo - l_h) if l_recs.iloc[0]['type'] == "事假" else day_theo
                cell_txt = f"🚫{l_recs.iloc[0]['type']}\n(原:{orig})" if l_h >= day_theo and day_theo > 0 else cell_txt + f"\n(-{l_h}h)"
            else: real_h += day_theo
            row[d.strftime("%m-%d")+h_mark] = cell_txt
        row["理论工时"], row["实到工时"] = f"{round(theo_h, 1)}h", f"{round(real_h, 1)}h"
        w_res.append(row)
    st.dataframe(pd.DataFrame(w_res), hide_index=True, use_container_width=True)
    st.markdown("---")
    st.markdown("##### 📝 班次说明\n- 早班: 09:00-19:00 (休12-13:30) | 延迟班: 10:00-20:00 (休13-14:30) | 晚值班: 12:30-22:00\n- 值班晚班次: 19:00-22:00 (3h) | ⭐柠檬负责人 | 📞电话接线 | (节)法定假")

# Tab 4
with tabs[3]:
    st.subheader("💰 月度考勤汇总汇总")
    m_y, m_m = st.selectbox("年份 ", [2026, 2027], key="sy222"), st.selectbox("月份 ", range(1, 13), index=now_beijing.month-1, key="sm222")
    m_days = [date(m_y, m_m, d) for d in range(1, calendar.monthrange(m_y, m_m)[1] + 1) if date(m_y, m_m, d) >= START_DATE]
    m_sum = []
    db_v = db_full[db_full['status']=="有效"] if not db_full.empty else pd.DataFrame()
    for name in STAFF:
        act_wd = [d for d in m_days if get_final_duty(name, d, db_v) != "休息"]
        h_wd = [d for d in act_wd if d in HOLIDAYS_2026]
        std = sum([SHIFT_HOURS_MAP.get(get_final_duty(name, d, db_v), 0.0) for d in m_days])
        pers = round(db_v[(db_v['name']==name) & (pd.to_datetime(db_v['date']).dt.month==m_m) & (db_v['type']=="事假")]['hours'].sum(), 1)
        m_sum.append({"姓名": name, "实到天数": len(act_wd), "法定假值班": f"🏮 {len(h_wd)} 天", "理论工时": f"{round(std,1)}h", "事假扣除": f"-{pers}h", "计薪工时": f"{round(max(0.0, std - pers),1)}h"})
    st.table(pd.DataFrame(m_sum))

# Tab 5
with tabs[4]:
    st.subheader("🔍 流水记录回撤管理")
    f_m = st.selectbox("查看月份", range(1, 13), index=now_beijing.month-1, key="fm_222")
    if not db_full.empty:
        df_s = db_full.copy(); df_s['month'] = pd.to_datetime(df_s['date']).dt.month
        df_s = df_s[df_s['month'] == f_m].sort_values("date", ascending=False)
        for _, r in df_s.iterrows():
            c1, c2, c3 = st.columns([1, 5, 1])
            c1.code(r['id'])
            icon = "🔄" if r['type']=="换班" else "🏮" if r['type']=="节假日值班" else "📝"
            s_clr = "green" if r['status']=="有效" else "red"
            c2.markdown(f"{icon} **{r['name']}** | {r['date']} | {r['type']} | {r['reason']}")
            if str(r['status']) == "有效" and c3.button("撤回记录", key=f"rev_{r['id']}"): 
                withdraw_req(r['id']); st.rerun()
            st.divider()

if st.button("🔄 全局同步数据"): st.rerun()
