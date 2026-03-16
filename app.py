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

st.set_page_config(page_title="客服部全时段覆盖排班系统", layout="wide")

# 核心常量
START_DATE = datetime(2026, 3, 1).date()
STAFF = ["郭战勇", "徐远远", "陈鹤舞", "都 娟", "陈君琳", "顾凌海"]
DB_FILE = "duty_final_v9.csv"
FIXED_HOUR = 8.5 

# --- 2. 班次与午休规则展示 ---
st.title("⚖️ 客服部全时段覆盖系统")

with st.expander("📌 班次与交接班规则 (防真空设计)", expanded=True):
    st.markdown(f"""
    | 班次 | 在司时间 | 备注 |
    | :--- | :--- | :--- |
    | **早班** | 09:00-19:00 | 负责早间开场 |
    | **延迟班** | 10:00-20:00 | 负责19-20点覆盖 |
    | **晚值班** | 12:30-19:00 | **12:30准时到岗交接**，负责20-22点居家 |
    
    **💡 关键交接规则：**
    1. **周一至周六**：09:00到岗的人员分为 A/B 两组午休。A组11:30休，B组必须等12:30晚班到岗后，13:00才休。
    2. **周日 (只有2人)**：早班人员**严禁**在12:30前离岗。必须等晚班同事12:30到岗交接后，方可午休。
    """)

# --- 3. 数据持久化 ---
if not os.path.exists(DB_FILE):
    pd.DataFrame(columns=["id", "name", "type", "date", "start_t", "end_t", "hours", "status"]).to_csv(DB_FILE, index=False)

def load_data():
    df = pd.read_csv(DB_FILE)
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df

# --- 4. 核心算法 ---
def get_duty_type(name, date_obj):
    if date_obj < START_DATE: return "未开始"
    weekday = date_obj.weekday()
    
    # 判定休息日
    if name == "郭战勇" and weekday == 2: return "休息"
    if name == "徐远远" and weekday == 5: return "休息"
    if name not in ["郭战勇", "徐远远"] and weekday == 6: return "休息"
    
    # 获取当天上班名单
    working_staff = [s for s in STAFF if get_duty_type_raw(s, date_obj) != "休息"]
    
    # 晚班分配 (轮流)
    num_late = 1 if weekday == 6 else 2
    day_seed = date_obj.day + date_obj.month
    late_team = [working_staff[(day_seed + i) % len(working_staff)] for i in range(num_late)]
    
    if name in late_team: return "晚值班"
    
    # 延迟班逻辑
    yesterday = date_obj - timedelta(days=1)
    if is_late_yesterday(name, yesterday): return "延迟班"

    return "早班"

def get_duty_type_raw(name, date_obj):
    """辅助函数：仅判定是否休息"""
    weekday = date_obj.weekday()
    if name == "郭战勇" and weekday == 2: return "休息"
    if name == "徐远远" and weekday == 5: return "休息"
    if name not in ["郭战勇", "徐远远"] and weekday == 6: return "休息"
    return "上班"

def is_late_yesterday(name, yesterday):
    """判定昨天是否值了晚班"""
    if yesterday < START_DATE: return False
    y_weekday = yesterday.weekday()
    y_working = [s for s in STAFF if get_duty_type_raw(s, yesterday) != "休息"]
    if not y_working: return False
    y_num_late = 1 if y_weekday == 6 else 2
    y_seed = yesterday.day + yesterday.month
    y_late_team = [y_working[(y_seed + i) % len(y_working)] for i in range(y_num_late)]
    return name in y_late_team

# --- 5. 实时状态判定逻辑 (核心优化点) ---
def get_current_status(name, name_idx, duty_type, now_dt):
    now_t = now_dt.time()
    now_d = now_dt.date()
    weekday = now_d.weekday()
    recs = load_data()
    active = recs[(recs['name']==name) & (recs['date']==now_d) & (recs['status']=="有效")]
    for _, r in active.iterrows():
        st_t = datetime.strptime(str(r['start_t']), "%H:%M:%S").time()
        en_t = datetime.strptime(str(r['end_t']), "%H:%M:%S").time()
        if st_t <= now_t <= en_t: return f"🔴 {r['type']}中", "red"

    if duty_type in ["休息", "未开始"]: return "😴 休息中", "grey"
    
    # --- 午休交替逻辑控制 ---
    if duty_type != "晚值班":
        if weekday == 6: # 周日
            # 周日只有两人，早班必须等晚班(12:30)到岗后，12:40再去吃午饭
            lunch_start, lunch_end = time(12, 40), time(14, 10)
        else:
            # 平日分两组
            if name_idx % 2 == 0:
                lunch_start, lunch_end = time(11, 30), time(13, 0) # A组早吃
            else:
                lunch_start, lunch_end = time(13, 0), time(14, 30) # B组晚吃
        
        if lunch_start <= now_t <= lunch_end:
            return "🍱 午休中", "orange"

    # --- 岗位状态判定 ---
    if duty_type == "晚值班":
        if now_t < time(12, 30): return "⏳ 等待上班", "grey"
        if time(12, 30) <= now_t <= time(19, 0): return "🏢 在司值班", "green"
        if time(19, 0) <= now_t <= time(20, 0): return "🚗 通勤中", "blue"
        if time(20, 0) <= now_t <= time(22, 0): return "🏠 居家远程", "green"
    elif duty_type == "延迟班":
        if time(10, 0) <= now_t <= time(20, 0): return "🏢 在司值班", "green"
    elif duty_type == "早班":
        if time(9, 0) <= now_t <= time(19, 0): return "🏢 在司值班", "green"
    
    return "🌙 已下班", "red"

# --- 6. 界面渲染 ---
now = get_now()
st.subheader(f"⏱️ 实时状态监控 ({now.strftime('%H:%M:%S')})")

# 实时计算当前在位人数
on_duty_count = 0
status_list = []
for i, name in enumerate(STAFF):
    dtype = get_duty_type(name, now.date())
    txt, clr = get_current_status(name, i, dtype, now)
    if clr == "green": on_duty_count += 1
    status_list.append((name, dtype, txt, clr))

st.markdown(f"### 📢 当前在位人数：`{on_duty_count}` 人")
if on_duty_count < 2:
    st.error("⚠️ 警告：当前在岗人数少于 2 人，请检查交接状态！")
else:
    st.success("✅ 当前人力覆盖正常")

cols = st.columns(6)
for i, (name, dtype, txt, clr) in enumerate(status_list):
    with cols[i]:
        st.write(f"**{name}**")
        st.caption(f"{dtype}")
        if clr == "green": st.success(txt)
        elif clr == "orange": st.warning(txt)
        elif clr == "red": st.error(txt)
        elif clr == "blue": st.info(txt)
        else: st.write(txt)

# --- 7. 工时与统计 ---
st.divider()
t_week, t_month, t_admin = st.tabs(["📊 周度工时", "📅 月度统计", "⚙️ 行政申请"])

with t_week:
    monday = now.date() - timedelta(days=now.weekday())
    w_dates = [monday + timedelta(days=i) for i in range(7)]
    db_v = load_data()
    db_v = db_v[db_v['status']=="有效"]
    
    res = []
    for name in STAFF:
        row = {"姓名": name}; total = 0.0
        for d in w_dates:
            dt = get_duty_type(name, d)
            h = FIXED_HOUR if dt != "休息" else 0.0
            l_h = db_v[(db_v['name']==name) & (db_v['date']==d)]['hours'].sum()
            total += (h - l_h)
            row[d.strftime("%m-%d\n%a")] = f"{dt}" + (f"\n(-{l_h})" if l_h > 0 else "")
        row["本周总工时"] = round(total, 1)
        res.append(row)
    st.dataframe(pd.DataFrame(res), hide_index=True)

with t_month:
    sel_m = st.selectbox("选择月份", range(1, 13), index=now.month-1)
    _, d_cnt = calendar.monthrange(2026, sel_m)
    m_dates = [datetime(2026, sel_m, d).date() for d in range(1, d_cnt+1) if datetime(2026, sel_m, d).date() >= START_DATE]
    m_res = []
    for name in STAFF:
        w_days = sum([1 for d in m_dates if get_duty_type(name, d) != "休息"])
        plan = w_days * FIXED_HOUR
        deduct = db_v[(db_v['name']==name) & (pd.to_datetime(db_v['date']).dt.month==sel_m)]['hours'].sum()
        m_res.append({"姓名": name, "出勤天数": w_days, "理论工时": round(plan, 1), "实到工时": round(plan-deduct, 1)})
    st.table(pd.DataFrame(m_res))

with t_admin:
    with st.form("req"):
        c1, c2, c3 = st.columns(3)
        n = c1.selectbox("人员", STAFF)
        t = c2.radio("类型", ["请假", "调休"], horizontal=True)
        d = c3.date_input("日期", value=now.date())
        t1 = st.time_input("开始", value=time(9,0))
        t2 = st.time_input("结束", value=time(18,0))
        if st.form_submit_button("提交申请"):
            df = load_data()
            h = round((datetime.combine(d, t2) - datetime.combine(d, t1)).total_seconds()/3600, 1)
            new_id = int(df['id'].max()+1) if not df.empty else 1
            pd.concat([df, pd.DataFrame([[new_id, n, t, d, str(t1), str(t2), h, "有效"]], columns=df.columns)]).to_csv(DB_FILE, index=False)
            st.success("已保存")
            st.rerun()

if st.button("🔄 刷新系统"):
    st.rerun()
