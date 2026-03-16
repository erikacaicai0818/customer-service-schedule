import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import os
import pytz
import calendar

# --- 1. 时区与配置 ---
china_tz = pytz.timezone('Asia/Shanghai')
def get_now():
    return datetime.now(china_tz)

st.set_page_config(page_title="客服部全排程规范管理系统", layout="wide")

# 核心常量
START_DATE = datetime(2026, 3, 1).date()
STAFF = ["郭战勇", "徐远远", "陈鹤舞", "都 娟", "陈君琳", "顾凌海"]
DB_FILE = "duty_final_v10.csv"
FIXED_HOUR = 8.5 

# 每个人固定的午休逻辑 (0-5 索引对应 STAFF)
LUNCH_CONFIG = {
    0: {"name": "A组", "start": time(11, 30), "end": time(13, 0)},
    1: {"name": "B组", "start": time(13, 0), "end": time(14, 30)},
    2: {"name": "A组", "start": time(11, 30), "end": time(13, 0)},
    3: {"name": "B组", "start": time(13, 0), "end": time(14, 30)},
    4: {"name": "A组", "start": time(11, 30), "end": time(13, 0)},
    5: {"name": "B组", "start": time(13, 0), "end": time(14, 30)},
}

# --- 2. 界面顶部：展示固定休息制度 ---
st.title("⚖️ 客服部标准化排班与强制午休系统")

with st.expander("📅 全员固定休息与午休制度公示 (严禁私自调换)", expanded=True):
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**固定周休安排：**")
        st.write("- 郭战勇：每周三休息")
        st.write("- 徐远远：每周六休息")
        st.write("- 其余同事：每周日休息")
    with col_b:
        st.markdown("**固定午休安排：**")
        st.write("- **A组 (郭/陈H/陈J)**：11:30 - 13:00")
        st.write("- **B组 (徐/都/顾)**：13:00 - 14:30")
        st.warning("⚠️ 周日特殊规定：早班人员必须在12:30晚班到岗后，于12:45方可午休。")

# --- 3. 核心算法 ---
def load_data():
    if not os.path.exists(DB_FILE):
        pd.DataFrame(columns=["id", "name", "type", "date", "start_t", "end_t", "hours", "status"]).to_csv(DB_FILE, index=False)
    df = pd.read_csv(DB_FILE)
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df

def get_duty_type(name, date_obj):
    if date_obj < START_DATE: return "未开始"
    weekday = date_obj.weekday()
    if name == "郭战勇" and weekday == 2: return "休息"
    if name == "徐远远" and weekday == 5: return "休息"
    if name not in ["郭战勇", "徐远远"] and weekday == 6: return "休息"
    
    # 晚班分配逻辑 (保持2人晚班，周日1人)
    working_staff = [s for s in STAFF if get_duty_type_raw(s, date_obj) != "休息"]
    num_late = 1 if weekday == 6 else 2
    day_seed = date_obj.day + date_obj.month
    late_team = [working_staff[(day_seed + i) % len(working_staff)] for i in range(num_late)]
    if name in late_team: return "晚值班"
    
    # 延迟班逻辑 (昨天晚班今天延迟)
    yesterday = date_obj - timedelta(days=1)
    if is_late_yesterday(name, yesterday): return "延迟班"
    return "早班"

def get_duty_type_raw(name, date_obj):
    weekday = date_obj.weekday()
    if name == "郭战勇" and weekday == 2: return "休息"
    if name == "徐远远" and weekday == 5: return "休息"
    if name not in ["郭战勇", "徐远远"] and weekday == 6: return "休息"
    return "上班"

def is_late_yesterday(name, yesterday):
    if yesterday < START_DATE: return False
    y_weekday = yesterday.weekday()
    y_working = [s for s in STAFF if get_duty_type_raw(s, yesterday) != "休息"]
    if not y_working: return False
    y_num_late = 1 if y_weekday == 6 else 2
    y_seed = yesterday.day + yesterday.month
    y_late_team = [y_working[(y_seed + i) % len(y_working)] for i in range(y_num_late)]
    return name in y_late_team

# --- 4. 实时状态判定 (含固定午休逻辑) ---
def get_current_status(name, name_idx, duty_type, now_dt):
    now_t = now_dt.time()
    now_d = now_dt.date()
    weekday = now_d.weekday()
    
    # 检查行政申请
    recs = load_data()
    active = recs[(recs['name']==name) & (recs['date']==now_d) & (recs['status']=="有效")]
    for _, r in active.iterrows():
        st_t = datetime.strptime(str(r['start_t']), "%H:%M:%S").time()
        en_t = datetime.strptime(str(r['end_t']), "%H:%M:%S").time()
        if st_t <= now_t <= en_t: return f"🔴 {r['type']}中", "red"

    if duty_type in ["休息", "未开始"]: return "😴 休息中", "grey"
    
    # --- 核心：固定午休判定 ---
    if duty_type != "晚值班":
        if weekday == 6: # 周日
            # 周日固定午休：12:45 - 14:15
            l_start, l_end = time(12, 45), time(14, 15)
        else:
            # 平日按分配的 A/B 组执行
            config = LUNCH_CONFIG[name_idx]
            l_start, l_end = config['start'], config['end']
        
        if l_start <= now_t <= l_end:
            return f"🍱 午休中 ({l_start.strftime('%H:%M')})", "orange"

    # --- 班次岗位判定 ---
    if duty_type == "晚值班":
        if now_t < time(12, 30): return "⏳ 等待上班", "grey"
        if time(12, 30) <= now_t <= time(19, 0): return "🏢 在司值班", "green"
        if time(19, 0) <= now_t <= time(20, 0): return "🚗 通勤路上", "blue"
        if time(20, 0) <= now_t <= time(22, 0): return "🏠 居家远程", "green"
    elif duty_type == "延迟班":
        if time(10, 0) <= now_t <= time(20, 0): return "🏢 在司值班", "green"
    else:
        if time(9, 0) <= now_t <= time(19, 0): return "🏢 在司值班", "green"
    
    return "🌙 已下班", "red"

# --- 5. 实时监控看板 ---
now = get_now()
st.subheader(f"⏱️ 实时监控面板 ({now.strftime('%H:%M:%S')} 北京时间)")

status_list = []
on_duty_count = 0
for i, name in enumerate(STAFF):
    dtype = get_duty_type(name, now.date())
    txt, clr = get_current_status(name, i, dtype, now)
    if clr == "green": on_duty_count += 1
    status_list.append((name, dtype, txt, clr))

# 在岗人数预警
if on_duty_count < 2:
    st.error(f"🔴 当前在岗人数：{on_duty_count} 人 (处于真空风险！)")
else:
    st.success(f"🟢 当前在岗人数：{on_duty_count} 人 (人力覆盖充足)")

mon_cols = st.columns(6)
for i, (name, dtype, txt, clr) in enumerate(status_list):
    with mon_cols[i]:
        st.markdown(f"**{name}**")
        st.caption(f"{dtype}")
        if clr == "green": st.success(txt)
        elif clr == "orange": st.warning(txt)
        elif clr == "red": st.error(txt)
        elif clr == "blue": st.info(txt)
        else: st.write(txt)

# --- 6. 数据中心 ---
st.divider()
tab_w, tab_m, tab_a = st.tabs(["📊 周度工时核算", "📅 月度统计汇总", "⚙️ 行政申请录入"])

with tab_w:
    monday = now.date() - timedelta(days=now.weekday())
    w_dates = [monday + timedelta(days=i) for i in range(7)]
    db_v = load_data()
    db_v = db_v[db_v['status']=="有效"]
    
    week_res = []
    for name in STAFF:
        row = {"姓名": name}
        w_total = 0.0
        for d in w_dates:
            dtype = get_duty_type(name, d)
            h = FIXED_HOUR if dtype != "休息" else 0.0
            l_h = db_v[(db_v['name']==name) & (db_v['date']==d)]['hours'].sum()
            w_total += (h - l_h)
            # 在表格中显示固定休息时间
            cell_txt = dtype
            if dtype != "休息":
                name_idx = STAFF.index(name)
                l_t = LUNCH_CONFIG[name_idx]['start'].strftime('%H:%M') if d.weekday()!=6 else "12:45"
                cell_txt += f"\n(休:{l_t})"
            if l_h > 0: cell_txt += f"\n[-{l_h}h]"
            row[d.strftime("%m-%d\n%a")] = cell_txt
        row["本周总工时"] = round(w_total, 1)
        week_res.append(row)
    st.dataframe(pd.DataFrame(week_res), use_container_width=True, hide_index=True)

with tab_m:
    sel_m = st.selectbox("选择统计月份", range(1, 13), index=now.month-1)
    _, d_cnt = calendar.monthrange(2026, sel_m)
    m_dates = [datetime(2026, sel_m, d).date() for d in range(1, d_cnt+1) if datetime(2026, sel_m, d).date() >= START_DATE]
    m_res = []
    for name in STAFF:
        work_days = sum([1 for d in m_dates if get_duty_type(name, d) != "休息"])
        plan = work_days * FIXED_HOUR
        deduct = db_v[(db_v['name']==name) & (pd.to_datetime(db_v['date']).dt.month==sel_m)]['hours'].sum()
        m_res.append({"姓名": name, "出勤天数": work_days, "理论工时": round(plan, 1), "实到工时": round(plan-deduct, 1)})
    st.table(pd.DataFrame(m_res))

with tab_a:
    with st.form("admin_form"):
        c1, c2, c3 = st.columns(3)
        n = c1.selectbox("申请人", STAFF)
        t = c2.radio("类型", ["请假", "调休"], horizontal=True)
        d = c3.date_input("申请日期", value=now.date())
        t1 = st.time_input("起始", value=time(9,0))
        t2 = st.time_input("结束", value=time(18,0))
        if st.form_submit_button("提交并更新"):
            df = load_data()
            h = round((datetime.combine(d, t2) - datetime.combine(d, t1)).total_seconds()/3600, 1)
            new_id = int(df['id'].max()+1) if not df.empty else 1
            pd.concat([df, pd.DataFrame([[new_id, n, t, d, str(t1), str(t2), h, "有效"]], columns=df.columns)]).to_csv(DB_FILE, index=False)
            st.success("记录成功")
            st.rerun()

if st.button("🔄 强制刷新数据"):
    st.rerun()
