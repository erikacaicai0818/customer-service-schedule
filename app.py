import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import calendar

# --- 1. 页面配置 ---
st.set_page_config(page_title="客服月度智能排班系统", layout="wide", page_icon="🗓️")

# --- 2. 基础规则定义 ---
# 班次对应的纯工时（不含休息）
WORK_HOURS_VAL = {"早班": 8.5, "延迟班": 8.5, "晚值班": 10.5, "休息": 0.0}

# 定义午休时段
LUNCH_SLOT_A = (time(11, 30), time(13, 0))  # 午休A
LUNCH_SLOT_B = (time(13, 0), time(14, 30))  # 午休B

# --- 3. 初始化持久化数据 ---
if 'leave_requests' not in st.session_state:
    st.session_state.leave_requests = []

# --- 4. 基础排班模板 (固定规律) ---
base_schedule = {
    "姓名": ["郭战勇", "徐远远", "陈鹤舞", "都 娟", "陈君琳", "顾凌海"],
    "周一": ["延迟班", "延迟班", "晚值班", "晚值班", "早班", "早班"],
    "周二": ["早班", "早班", "延迟班", "延迟班", "晚值班", "晚值班"],
    "周三": ["休息", "早班", "早班", "早班", "延迟班", "延迟班"],
    "周四": ["晚值班", "早班", "早班", "晚值班", "早班", "早班"],
    "周五": ["延迟班", "晚值班", "晚值班", "延迟班", "早班", "早班"],
    "周六": ["早班", "休息", "延迟班", "早班", "晚值班", "晚值班"],
    "周日": ["晚值班", "晚值班", "休息", "休息", "休息", "休息"]
}

staff_list = base_schedule["姓名"]
weekdays_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# --- 5. 辅助逻辑函数 ---
def get_lunch_slot(name_idx):
    """根据人员索引交错分配午休，确保覆盖"""
    return LUNCH_SLOT_A if name_idx % 2 == 0 else LUNCH_SLOT_B

def get_shift_details(shift_type, name_idx):
    """获取班次的时间线详情，包含动态分配的午休"""
    slot = get_lunch_slot(name_idx)
    slot_str = f"{slot[0].strftime('%H:%M')}-{slot[1].strftime('%H:%M')}"
    
    if shift_type == "早班":
        return [(time(9,0), slot[0], "🏢 在司值班"), (slot[0], slot[1], f"🍱 午休({slot_str})"), (slot[1], time(19,0), "🏢 在司值班")]
    if shift_type == "延迟班":
        return [(time(10,0), slot[0], "🏢 在司值班"), (slot[0], slot[1], f"🍱 午休({slot_str})"), (slot[1], time(20,0), "🏢 在司值班")]
    if shift_type == "晚值班":
        return [(time(9,0), slot[0], "🏢 在司值班"), (slot[0], slot[1], f"🍱 午休({slot_str})"), (slot[1], time(19,0), "🏢 在司值班"), (time(19,0), time(20,0), "🚗 通勤中"), (time(20,0), time(22,0), "🏠 居家远程")]
    return []

def calculate_hours(name, date_obj):
    """计算单日工时（扣除请假）"""
    weekday_str = weekdays_cn[date_obj.weekday()]
    name_idx = staff_list.index(name)
    shift_type = base_schedule[weekday_str][name_idx]
    daily_h = WORK_HOURS_VAL.get(shift_type, 0)
    
    for r in st.session_state.leave_requests:
        if r['name'] == name and r['date'] == date_obj:
            duration = datetime.combine(date_obj, r['end_t']) - datetime.combine(date_obj, r['start_t'])
            daily_h = max(0, daily_h - duration.total_seconds()/3600)
    return daily_h

# --- 6. 侧边栏：请假与月度筛选 ---
with st.sidebar:
    st.header("⚙️ 管理面板")
    
    # 月度筛选器
    target_year = st.selectbox("选择年份", [2025, 2026], index=1)
    target_month = st.selectbox("选择月份", list(range(1, 13)), index=datetime.now().month - 1)
    
    st.divider()
    
    # 请假申请
    st.subheader("📝 录入请假")
    with st.form("leave_form", clear_on_submit=True):
        l_name = st.selectbox("人员", staff_list)
        l_date = st.date_input("日期", value=datetime.now().date())
        l_start_t = st.time_input("开始时间", value=time(9, 0))
        l_end_t = st.time_input("结束时间", value=time(18, 0))
        if st.form_submit_button("提交申请"):
            st.session_state.leave_requests.append({"name": l_name, "date": l_date, "start_t": l_start_t, "end_t": l_end_t})
            st.success("请假已记录")

# --- 7. 主界面逻辑 ---
st.title(f"📊 {target_year}年{target_month}月 客服排班管理系统")

# A. 月度数据计算
month_days = calendar.monthrange(target_year, target_month)[1]
all_dates = [datetime(target_year, target_month, d).date() for d in range(1, month_days + 1)]

# 按周分组日期
weeks_in_month = []
current_week = []
for d in all_dates:
    current_week.append(d)
    if d.weekday() == 6 or d == all_dates[-1]:  # 周日或月终
        weeks_in_month.append(current_week)
        current_week = []

# B. 实时监控 (仅在今天属于该月时展示)
now = datetime.now()
if now.year == target_year and now.month == target_month:
    st.subheader(f"⏱️ 实时监控 ({now.strftime('%H:%M:%S')})")
    cols = st.columns(6)
    
    for i, name in enumerate(staff_list):
        is_leave = False
        for r in st.session_state.leave_requests:
            if r['name'] == name and r['date'] == now.date() and r['start_t'] <= now.time() <= r['end_t']:
                is_leave = True; break
        
        with cols[i]:
            st.write(f"**{name}**")
            if is_leave:
                st.error("🔴 请假中")
            else:
                shift = base_schedule[weekdays_cn[now.weekday()]][i]
                if shift == "休息":
                    st.info("😴 休息")
                else:
                    details = get_shift_details(shift, i)
                    status_text, color = "🌙 已下班", "red"
                    for s, e, txt in details:
                        if s <= now.time() <= e:
                            status_text, color = txt, ("green" if "值班" in txt else "orange")
                            break
                    if color == "green":
                        st.success(status_text)
                    elif color == "orange":
                        st.warning(status_text)
                    else:
                        st.error(status_text)

    st.divider()

# C. 月度工时统计汇总
st.subheader("📈 本月工时统计")
monthly_stats = []
for name in staff_list:
    total_h = sum([calculate_hours(name, d) for d in all_dates])
    monthly_stats.append({"姓名": name, "全月实到工时": round(total_h, 1)})

stat_df = pd.DataFrame(monthly_stats)

col_table, col_chart = st.columns([1, 2])
with col_table:
    st.dataframe(stat_df, hide_index=True)
with col_chart:
    st.bar_chart(stat_df, x="姓名", y="全月实到工时")

st.divider()

# D. 筛选单周排班表
st.subheader("📅 周值班表查看")
week_options = [f"第{i+1}周 ({w[0].strftime('%m-%d')} 至 {w[-1].strftime('%m-%d')})" for i, w in enumerate(weeks_in_month)]
selected_week_idx = st.selectbox("请选择要查看的周：", range(len(week_options)), format_func=lambda x: week_options[x])
target_week = weeks_in_month[selected_week_idx]

week_df = pd.DataFrame(columns=["姓名"] + [d.strftime("%m-%d (%a)") for d in target_week])
week_df["姓名"] = staff_list

for i, date_obj in enumerate(target_week):
    day_cn = weekdays_cn[date_obj.weekday()]
    for name_idx, name in enumerate(staff_list):
        shift = base_schedule[day_cn][name_idx]
        cell_val = shift
        # 检查是否有请假
        for r in st.session_state.leave_requests:
            if r['name'] == name and r['date'] == date_obj:
                cell_val = f"⚠️ 请假({shift})"
        week_df.iloc[name_idx, i+1] = cell_val

st.dataframe(week_df, width='stretch')
st.caption("注：系统已自动交错安排午休：索引单数(11:30-13:00) / 索引双数(13:00-14:30)，确保午间有人在岗。")
