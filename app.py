import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import os
import calendar

# --- 1. 初始化配置 ---
st.set_page_config(page_title="客服智能管理系统 v2.0", layout="wide")

# 数据文件路径
LEAVE_FILE = "leave_records.csv"
START_DATE = datetime(2026, 3, 1).date()

# 班次定义
SHIFT_HOURS = {"早班": 8.5, "延迟班": 8.5, "晚值班": 10.5, "休息": 0.0}
STAFF = ["郭战勇", "徐远远", "陈鹤舞", "都 娟", "陈君琳", "顾凌海"]

# --- 2. 核心逻辑：公平轮班算法 ---
def get_base_schedule(date_obj):
    """
    根据日期动态计算当天的班次，保证公平轮转。
    逻辑：每3周为一个大循环，保证每个人轮流值周日。
    """
    weekday = date_obj.weekday()  # 0=周一, 6=周日
    # 计算当前日期是 2026-03-01 之后的第几周
    weeks_passed = (date_obj - START_DATE).days // 7
    cycle = weeks_passed % 3 # 3周一循环

    # 定义三组周日值班搭档
    pairs = [("郭战勇", "徐远远"), ("陈鹤舞", "都 娟"), ("陈君琳", "顾凌海")]
    sun_pair = pairs[cycle]

    # 确定当天的排班
    day_schedule = {}
    if weekday == 6:  # 周日
        for name in STAFF:
            day_schedule[name] = "晚值班" if name in sun_pair else "休息"
    else:
        # 周一到周六：5人全勤，周日值班的那两个人中，其中一个在周三休，一个在周六休
        off_staff = ""
        if weekday == 2: off_staff = sun_pair[0] # 周三周日值班人A休息
        if weekday == 5: off_staff = sun_pair[1] # 周六周日值班人B休息

        # 晚班轮转逻辑（每天2人晚班，按天轮流）
        night_shift_idx = (date_obj.day + weeks_passed) % 6
        night_staff_1 = STAFF[night_shift_idx]
        night_staff_2 = STAFF[(night_shift_idx + 1) % 6]

        for i, name in enumerate(STAFF):
            if name == off_staff:
                day_schedule[name] = "休息"
            elif name in [night_staff_1, night_staff_2]:
                day_schedule[name] = "晚值班"
            else:
                day_schedule[name] = "早班"
    return day_schedule

# --- 3. 数据持久化逻辑 ---
if not os.path.exists(LEAVE_FILE):
    df_init = pd.DataFrame(columns=["id", "name", "type", "date", "start_t", "end_t", "hours", "status"])
    df_init.to_csv(LEAVE_FILE, index=False)

def load_data():
    df = pd.read_csv(LEAVE_FILE)
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df

def save_request(name, req_type, date, start_t, end_t):
    df = load_data()
    # 计算时长
    duration = datetime.combine(date, end_t) - datetime.combine(date, start_t)
    h = round(duration.total_seconds() / 3600, 1)
    new_id = len(df) + 1
    new_data = pd.DataFrame([[new_id, name, req_type, date, start_t, end_t, h, "有效"]], 
                            columns=df.columns)
    df = pd.concat([df, new_data], ignore_index=True)
    df.to_csv(LEAVE_FILE, index=False)

def delete_request(req_id):
    df = load_data()
    df.loc[df['id'] == req_id, 'status'] = "已撤回"
    df.to_csv(LEAVE_FILE, index=False)

# --- 4. 界面布局 ---
st.title("⚖️ 客服部公平排班与考勤系统")
st.info(f"数据统计起点：{START_DATE} | 当前规则：全员轮流值周日，确保月度工时平衡。")

# 侧边栏：申请操作
with st.sidebar:
    st.header("📋 新增申请")
    with st.form("req_form", clear_on_submit=True):
        name = st.selectbox("申请人", STAFF)
        req_type = st.radio("类型", ["请假", "调休"])
        d = st.date_input("日期", value=datetime.now().date())
        t1 = st.time_input("开始", value=time(9,0))
        t2 = st.time_input("结束", value=time(18,0))
        if st.form_submit_button("提交申请"):
            if d < START_DATE:
                st.error("不能记录2026年3月1日之前的数据")
            else:
                save_request(name, req_type, d, t1, t2)
                st.success("申请已生效")

# 主界面：月份筛选
col1, col2 = st.columns(2)
with col1:
    view_year = st.selectbox("年份", [2026, 2027])
with col2:
    view_month = st.selectbox("月份", range(1, 13), index=datetime.now().month-1)

# --- 5. 计算并展示工时统计 ---
st.subheader("📊 月度出勤统计")
leave_df = load_data()
valid_leaves = leave_df[leave_df['status'] == "有效"]

# 获取当月所有日期
_, num_days = calendar.monthrange(view_year, view_month)
month_dates = [datetime(view_year, view_month, d).date() for d in range(1, num_days+1)]

monthly_summary = []
for name in STAFF:
    total_scheduled_h = 0
    total_deduction_h = 0

    for d_obj in month_dates:
        if d_obj < START_DATE: continue
        # 基础排班工时
        sch = get_base_schedule(d_obj)
        total_scheduled_h += SHIFT_HOURS.get(sch[name], 0)
        # 请假/调休扣除
        day_leaves = valid_leaves[(valid_leaves['name'] == name) & (valid_leaves['date'] == d_obj)]
        total_deduction_h += day_leaves['hours'].sum()

    monthly_summary.append({
        "姓名": name,
        "应出勤工时": total_scheduled_h,
        "请假/调休扣除": total_deduction_h,
        "实际计薪工时": total_scheduled_h - total_deduction_h
    })

sum_df = pd.DataFrame(monthly_summary)
st.dataframe(sum_df, use_container_width=True, hide_index=True)

# --- 6. 展示周表与操作历史 ---
st.divider()
tab1, tab2 = st.tabs(["📅 值班表查看", "⏳ 申请记录回撤"])

with tab1:
    # 默认显示本周
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_dates = [week_start + timedelta(days=i) for i in range(7)]

    week_display = pd.DataFrame(columns=["姓名"] + [d.strftime("%m-%d\n%a") for d in week_dates])
    week_display["姓名"] = STAFF

    for i, d_obj in enumerate(week_dates):
        sch = get_base_schedule(d_obj)
        for idx, name in enumerate(STAFF):
            cell = sch[name]
            # 叠加请假标记
            if not valid_leaves[(valid_leaves['name']==name) & (valid_leaves['date']==d_obj)].empty:
                cell = f"⚠️ {cell}(有假)"
            week_display.iloc[idx, i+1] = cell

    st.dataframe(week_display, use_container_width=True, hide_index=True)

with tab2:
    st.write("所有申请记录（含历史）：")
    log_df = leave_df.sort_values("id", ascending=False)
    for index, row in log_df.iterrows():
        c1, c2, c3, c4 = st.columns([1, 3, 1, 1])
        with c1: st.write(f"ID:{row['id']}")
        with c2: st.write(f"{row['name']} | {row['date']} | {row['type']} {row['hours']}小时 | 状态:{row['status']}")
        with c3:
            if row['status'] == "有效":
                if st.button("撤回", key=f"del_{row['id']}"):
                    delete_request(row['id'])
                    st.rerun()
        st.write("---")
