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

st.set_page_config(page_title="客服考勤管理系统 v18.9", layout="wide", page_icon="⚖️")

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

# 核心常量 (保持 v18.7 名单顺序)
START_DATE = datetime(2026, 3, 1).date()
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
    # 类型强制清理
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
    """最原始的系统自动排班"""
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

    if weekday in [0, 1, 3, 4]: 
        if current_staff_pos < 2: return "早班"
        elif current_staff_pos < 4: return "延迟班"
        else: return "晚值班"
    elif weekday in [2, 5]: 
        if current_staff_pos < 2: return "早班"
        elif current_staff_pos < 3: return "延迟班"
        else: return "晚值班"
    elif weekday == 6: 
        if current_staff_pos < 1: return "早班"
        else: return "晚值班"
    return "早班"

def get_final_duty_after_swap(name, date_obj, db_df):
    """仅计算换班后的结果"""
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

st.title("🛡️ 客服部排班管理系统 v18.9 (变动全追踪)")

with st.sidebar:
    st.header("📋 提交申请")
    with st.form("leave_form", clear_on_submit=True):
        l_name = st.selectbox("人员姓名", STAFF, key="ln")
        l_type = st.radio("类型", ["事假", "病假", "调休"], horizontal=True)
        l_date = st.date_input("日期", value=now_beijing.date(), key="ld")
        c1, c2 = st.columns(2)
        l_t1 = c1.time_input("开始", value=time(9,0))
        l_t2 = c2.time_input("结束", value=time(18,0))
        l_reason = st.text_input("备注信息")
        if st.form_submit_button("确认行政申请"):
            h = round((datetime.combine(l_date, l_t2) - datetime.combine(l_date, l_t1)).total_seconds()/3600, 1)
            new_id = int(db_full['id'].max()+1) if not db_full.empty else 1001
            save_data_to_gsheets({"id": new_id, "name": l_name, "type": l_type, "date": l_date, "start_t": l_t1, "end_t": l_t2, "hours": h, "reason": l_reason, "status": "有效", "submit_time": now_beijing})
            st.rerun()
    
    st.header("🔄 提交换班")
    with st.form("swap_form", clear_on_submit=True):
        s_name = st.selectbox("申请人", STAFF, key="sn")
        target = st.selectbox("目标人", [s for s in STAFF if s != s_name])
        s_date = st.date_input("日期", value=now_beijing.date(), key="sd")
        if st.form_submit_button("确认全天换班"):
            new_id = int(db_full['id'].max()+1) if not db_full.empty else 1001
            save_data_to_gsheets({"id": new_id, "name": s_name, "type": "换班", "date": s_date, "start_t": "00:00:00", "end_t": "23:59:59", "hours": 0.0, "reason": f"与 {target} 换班", "status": "有效", "submit_time": now_beijing})
            st.rerun()

tabs = st.tabs(["🟢 实时监控", "👤 个人月度表", "📅 周度全表", "💰 计薪汇总", "🔍 记录管理"])

# Tab 1: 实时监控
with tabs[0]:
    st.subheader(f"⏱️ 状态快照 ({now_beijing.strftime('%H:%M:%S')})")
    cols = st.columns(6)
    for i, name in enumerate(STAFF):
        f_dt = get_final_duty_after_swap(name, now_beijing.date(), db_full)
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
    st.subheader("👤 个人值班日历")
    i_c1, i_c2, i_c3 = st.columns(3)
    t_staff = i_c1.selectbox("客服", STAFF, key="is_p")
    t_year = i_c2.selectbox("年份 ", [2026, 2027], key="iy_p")
    t_month = i_c3.selectbox("月份 ", range(1, 13), index=now_beijing.month-1, key="im_p")
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(t_year, t_month)
    db_v = db_full[db_full['status']=="有效"] if not db_full.empty else pd.DataFrame()
    header_cols = st.columns(7)
    for idx, d_n in enumerate(["一","二","三","四","五","六","日"]): header_cols[idx].markdown(f"<center>周{d_n}</center>", unsafe_allow_html=True)
    for week in weeks:
        cols = st.columns(7)
        for i, d in enumerate(week):
            if d.month == t_month:
                f_dt = get_final_duty_after_swap(t_staff, d, db_full)
                orig_dt = get_original_duty(t_staff, d)
                is_today = "calendar-today" if d == now_beijing.date() else ""
                with cols[i]:
                    display_txt = f"{f_dt}"
                    if f_dt != orig_dt: display_txt = f"🔄{f_dt}"
                    st.markdown(f"<div class='calendar-cell {is_today}'><div style='font-size:1.1em; font-weight:bold;'>{d.day}</div><div style='color:#004085; margin-top:5px; font-weight:bold;'>{'休' if f_dt=='休息' else display_txt}</div></div>", unsafe_allow_html=True)
                    if f_dt != "休息":
                        l_t = "12:00" if f_dt == "早班" else "13:00" if f_dt == "延迟班" else "无"
                        st.caption(f"🍱{l_t}")
                        if not db_v.empty:
                            day_l = db_v[(db_v['name']==t_staff) & (db_v['date']==d) & (db_v['type'] != "换班")]
                            for _, r in day_l.iterrows():
                                st.markdown(f":{'red' if r['type']=='事假' else 'blue'}[{r['type']}]")
            else: cols[i].write("")

# --- Tab 3: 周表 (新增深度追踪逻辑) ---
with tabs[2]:
    st.subheader("📅 周度排班追踪 (已集成换班/请假/调休变动)")
    mon = now_beijing.date() - timedelta(days=now_beijing.weekday())
    w_dates = [mon + timedelta(days=i) for i in range(7)]
    w_res = []
    db_v = db_full[db_full['status']=="有效"] if not db_full.empty else pd.DataFrame()
    
    for name in STAFF:
        row = {"姓名": name}
        theo_h = 0.0; real_h = 0.0
        for d in w_dates:
            orig = get_original_duty(name, d)
            after_swap = get_final_duty_after_swap(name, d, db_v)
            leave_recs = db_v[(db_v['name']==name) & (db_v['date']==d) & (db_v['type']!="换班")]
            
            # 计算小时数
            day_theo = FIXED_HOUR if after_swap != "休息" else 0.0
            theo_h += day_theo
            
            # 基础文本确定
            if after_swap != orig:
                cell_txt = f"🔄{after_swap}\n(原:{orig})"
            else:
                cell_txt = f"{after_swap}"
            
            # 处理请假/调休叠加
            if not leave_recs.empty:
                l_h = round(leave_recs['hours'].sum(), 1)
                l_type = leave_recs.iloc[0]['type']
                if l_type == "事假": real_h += (day_theo - l_h)
                else: real_h += day_theo # 病假调休不扣费
                
                # 如果是全天请假，改写显示
                if l_h >= FIXED_HOUR:
                    cell_txt = f"🚫{l_type}\n(原:{orig})"
                else:
                    cell_txt += f"\n(-{l_h}h {l_type})"
            else:
                real_h += day_theo

            row[d.strftime("%m-%d\n%a")] = cell_txt
            
        row["理论工时"] = f"{round(theo_h, 1)}h"
        row["计薪工时"] = f"{round(max(0.0, real_h), 1)}h"
        w_res.append(row)
    
    st.dataframe(pd.DataFrame(w_res), use_container_width=True, hide_index=True)
    st.markdown("---")
    st.markdown("##### 💡 图标说明：\n- **🔄班次**: 班次已换，括号内为系统原始安排\n- **🚫类型**: 全天请假或调休\n- **-Xh 类型**: 班次内部分时间请假\n- **计薪工时**: 已扣除事假，病假/调休不扣除")

# Tab 4: 计薪汇总
with tabs[3]:
    st.subheader("💰 月度计薪汇总")
    m_y = st.selectbox("年份选择", [2026, 2027], key="sal_y")
    m_m = st.selectbox("月份选择", range(1, 13), index=now_beijing.month-1, key="sal_m")
    m_days = [datetime(m_y, m_m, d).date() for d in range(1, calendar.monthrange(m_y, m_m)[1] + 1) if datetime(m_y, m_m, d).date() >= START_DATE]
    m_summary = []
    for name in STAFF:
        act_wd = sum([1 for d in m_days if get_final_duty_after_swap(name, d, db_v) != "休息"])
        std = round(act_wd * FIXED_HOUR, 1)
        pers = round(db_v[(db_v['name']==name) & (pd.to_datetime(db_v['date']).dt.month==m_m) & (pd.to_datetime(db_v['date']).dt.year==m_y) & (db_v['type']=="事假")]['hours'].sum(), 1)
        paid = round(db_v[(db_v['name']==name) & (pd.to_datetime(db_v['date']).dt.month==m_m) & (pd.to_datetime(db_v['date']).dt.year==m_y) & (db_v['type'].isin(["病假", "调休"]))]['hours'].sum(), 1)
        m_summary.append({"姓名": name, "实到天数": act_wd, "理论工时": f"{std}h", "事假扣除": f"-{pers}h", "病假/调休": f"{paid}h", "应发计薪工时": f"{round(max(0.0, std - pers),1)}h"})
    st.table(pd.DataFrame(m_summary))

# Tab 5: 记录管理
with tabs[4]:
    st.subheader("🔍 流水记录查询 (支持一键回撤)")
    f_month = st.selectbox("查看月份 ", range(1, 13), index=now_beijing.month-1)
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
            if str(r['status']) == "有效":
                if c3.button("撤回", key=f"rev_{r['id']}"): withdraw_req(r['id']); st.rerun()
            else: c3.write(":red[已回撤]")
            st.divider()

if st.button("🔄 同步云端数据"): st.rerun()
