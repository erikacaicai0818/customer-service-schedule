import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import calendar
import os

# --- 1. 基础配置 ---
st.set_page_config(page_title="客服值班综合管理系统 V4.0", layout="wide")
START_STATS_DATE = datetime(2026, 3, 1).date()
DATA_FILE = "duty_records_v4.csv"

# 班次定义
SHIFTS = {
    "早班": {"off": 8.5, "home": 0, "s": time(9,0), "e": time(19,0), "b": (time(11,30), time(13,0))},
    "延迟班": {"off": 8.5, "home": 0, "s": time(10,0), "e": time(20,0), "b": (time(13,0), time(14,30))},
    "晚值班": {"off": 8.5, "home": 2, "s": time(9,0), "e": time(22,0), "b": (time(11,30), time(13,0)), "h": (time(20,0), time(22,0)), "c": (time(19,0), time(20,0))},
    "休息": {"off": 0, "home": 0, "s": time(0,0), "e": time(0,0), "b": None}
}

# 绝对公平周循环模板
# 保证：每人每周休1天，且晚班次数分配均衡
WEEK_PATTERN = {
    "姓名": ["郭战勇", "徐远远", "陈鹤舞", "都 娟", "陈君琳", "顾凌海"],
    0: ["延迟班", "早班", "晚值班", "早班", "早班", "早班"], # 周一
    1: ["早班", "延迟班", "延迟班", "晚值班", "早班", "早班"], # 周二
    2: ["休息", "早班", "早班", "延迟班", "晚值班", "早班"],    # 周三 (战勇休)
    3: ["早班", "早班", "早班", "早班", "延迟班", "晚值班"],    # 周四
    4: ["晚值班", "早班", "早班", "早班", "早班", "延迟班"],    # 周五
    5: ["延迟班", "休息", "早班", "早班", "早班", "早班"],    # 周六 (远远休)
    6: ["晚值班", "晚值班", "休息", "休息", "休息", "休息"]     # 周日 (其余休)
}

# --- 2. 数据处理函数 ---
def load_data():
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE)
        df['日期'] = pd.to_datetime(df['日期']).dt.date
        return df
    return pd.DataFrame(columns=["ID", "姓名", "类型", "日期", "开始", "结束", "时数", "状态"])

def save_record(name, r_type, r_date, s_time, e_time):
    df = load_data()
    r_id = int(df['ID'].max() + 1) if not df.empty else 1
    dur = (datetime.combine(r_date, e_time) - datetime.combine(r_date, s_time)).seconds / 3600
    new_rec = pd.DataFrame([[r_id, name, r_type, r_date, s_time.strftime("%H:%M"), e_time.strftime("%H:%M"), round(dur, 1), "有效"]], columns=df.columns)
    pd.concat([df, new_rec]).to_csv(DATA_FILE, index=False)

def revoke_record(r_id):
    df = load_data()
    df.loc[df['ID'] == r_id, '状态'] = "已撤回"
    df.to_csv(DATA_FILE, index=False)

# 获取某人某天的排班及实时状态
def get_detail(name, d_date, check_time=None):
    weekday = d_date.weekday()
    idx = WEEK_PATTERN["姓名"].index(name)
    s_name = WEEK_PATTERN[weekday][idx]
    s_conf = SHIFTS[s_name]
    
    # 基础工时
    off_h, home_h = s_conf["off"], s_conf["home"]
    
    # 检查请假/调休
    leaves = load_data()
    day_leave = leaves[(leaves['姓名'] == name) & (leaves['日期'] == d_date) & (leaves['状态'] == "有效")]
    leave_h = day_leave['时数'].sum()
    
    status = "🟢 正常值班"
    if s_name == "休息": status = "🔴 休息日"
    
    # 实时状态判定
    if check_time:
        # 1. 检查是否在请假时间段内
        for _, r in day_leave.iterrows():
            if datetime.strptime(r['开始'], "%H:%M").time() <= check_time <= datetime.strptime(r['结束'], "%H:%M").time():
                status = f"🟡 {r['类型']}中"
        
        # 2. 检查休息/居家/通勤
        if status == "🟢 正常值班":
            if s_conf["b"] and s_conf["b"][0] <= check_time <= s_conf["b"][1]:
                status = "☕ 午休中"
            elif s_name == "晚值班":
                if s_conf["c"][0] <= check_time <= s_conf["c"][1]: status = "🚗 通勤中"
                elif s_conf["h"][0] <= check_time <= s_conf["h"][1]: status = "🏠 居家值班"
            if not (s_conf["s"] <= check_time <= s_conf["e"]):
                if status == "🟢 正常值班": status = "🌙 已下班"

    return {"shift": s_name, "off_h": off_h, "home_h": home_h, "leave_h": leave_h, "status": status, "break": s_conf["b"]}

# --- 3. UI 渲染 ---
st.title("🎧 客服值班综合管理系统 V4.0")

# 侧边栏
st.sidebar.header("📅 时间筛选")
sel_date = st.sidebar.date_input("查看日期", datetime.now().date())
sel_month = sel_date.month
sel_year = sel_date.year

st.sidebar.divider()
st.sidebar.header("📝 申请录入")
with st.sidebar.form("apply_form", clear_on_submit=True):
    a_name = st.selectbox("申请人", WEEK_PATTERN["姓名"])
    a_type = st.radio("类型", ["请假", "调休"])
    a_date = st.date_input("日期", sel_date)
    a_s = st.time_input("开始", time(9, 0))
    a_e = st.time_input("结束", time(18, 0))
    if st.form_submit_button("提交申请"):
        save_record(a_name, a_type, a_date, a_s, a_e)
        st.rerun()

# --- Tab 分页 ---
tab1, tab2, tab3, tab4 = st.tabs(["🕒 实时状态", "📅 周排班表", "📊 工时统计", "📜 历史记录"])

# Tab 1: 实时状态
with tab1:
    now = datetime.now()
    st.subheader(f"当前在岗监控 ({now.strftime('%H:%M:%S')})")
    cols = st.columns(6)
    for i, name in enumerate(WEEK_PATTERN["姓名"]):
        res = get_detail(name, now.date(), now.time())
        with cols[i]:
            if "🟢" in res['status']: st.success(f"**{name}**\n\n{res['status']}")
            elif "☕" in res['status'] or "🚗" in res['status']: st.info(f"**{name}**\n\n{res['status']}")
            elif "🏠" in res['status']: st.warning(f"**{name}**\n\n{res['status']}")
            elif "🟡" in res['status']: st.info(f"**{name}**\n\n{res['status']}")
            else: st.error(f"**{name}**\n\n{res['status']}")
            st.caption(f"今日班次: {res['shift']}")

# Tab 2: 周排班表
with tab2:
    start_w = sel_date - timedelta(days=sel_date.weekday())
    st.subheader(f"周排班视图 ({start_w} ~ {start_w + timedelta(days=6)})")
    week_data = []
    for name in WEEK_PATTERN["姓名"]:
        row = {"姓名": name}
        total_w_h = 0
        for i in range(7):
            d = start_w + timedelta(days=i)
            info = get_detail(name, d)
            day_str = d.strftime('%m-%d')
            row[day_str] = f"{info['shift']}"
            if info['leave_h'] > 0: row[day_str] += f" (假-{info['leave_h']}h)"
            total_w_h += (info['off_h'] + info['home_h'] - info['leave_h'])
        row["周工时"] = total_w_h
        week_data.append(row)
    st.dataframe(pd.DataFrame(week_data), use_container_width=True)

# Tab 3: 工时统计
with tab3:
    st.subheader(f"工时统计汇总 (起止: 2026-03-01 至 {sel_year}-{sel_month}月底)")
    month_days = calendar.monthrange(sel_year, sel_month)[1]
    m_stats = []
    for name in WEEK_PATTERN["姓名"]:
        # 月度统计
        m_off, m_home, m_leave = 0, 0, 0
        for d in range(1, month_days + 1):
            d_obj = datetime(sel_year, sel_month, d).date()
            if d_obj < START_STATS_DATE: continue
            info = get_detail(name, d_obj)
            m_off += info['off_h']
            m_home += info['home_h']
            m_leave += info['leave_h']
        
        # 历史累计统计 (自2026-03-01起所有数据)
        h_total = 0
        curr_d = START_STATS_DATE
        while curr_d <= datetime.now().date():
            h_info = get_detail(name, curr_d)
            h_total += (h_info['off_h'] + h_info['home_h'] - h_info['leave_h'])
            curr_d += timedelta(days=1)

        m_stats.append({
            "姓名": name,
            "本月在司(h)": m_off,
            "本月居家(h)": m_home,
            "本月请假(h)": m_leave,
            "本月总计": m_off + m_home - m_leave,
            "自2026-03-01累计": h_total
        })
    st.table(pd.DataFrame(m_stats))

# Tab 4: 历史记录
with tab4:
    st.subheader("申请流水与撤回管理")
    history = load_data().sort_values("ID", ascending=False)
    if history.empty:
        st.write("暂无记录")
    else:
        for _, r in history.iterrows():
            c1, c2, c3, c4 = st.columns([1, 3, 1, 1])
            with c1: st.write(f"ID: {r['ID']}")
            with c2: st.write(f"**{r['日期']} {r['姓名']}** | {r['类型']} ({r['开始']}-{r['结束']}) | {r['时数']}h")
            with c3:
                color = "green" if r['状态'] == "有效" else "gray"
                st.markdown(f":{color}[{r['状态']}]")
            with c4:
                if r['状态'] == "有效":
                    if st.button("撤回", key=f"rev_{r['ID']}"):
                        revoke_record(r['ID'])
                        st.rerun()

st.divider()
st.caption("提示：晚值班人员次日自动执行10:00上岗班次（延迟班）。")
