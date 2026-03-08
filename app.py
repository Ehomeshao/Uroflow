import streamlit as st
import pandas as pd
import plotly.express as px

# 設定頁面與繁體中文
st.set_page_config(page_title="智慧排尿日記", layout="centered")
st.title("💧 智慧排尿日記 (Patient Portal)")

# 初始化暫存資料庫 (Session State)
if 'diary_data' not in st.session_state:
    st.session_state.diary_data = pd.DataFrame(columns=[
        '日期', '時間', '排尿量(ml)', '餘尿量(ml)', '尿流速圖檔名'
    ])

# ================= 1. 紀錄輸入區 =================
st.header("📝 新增紀錄")
with st.form("record_form"):
    col1, col2 = st.columns(2)
    with col1:
        record_date = st.date_input("日期 (請選擇)", value=None)
        record_time = st.time_input("時間 (請選擇)", value=None)
    with col2:
        void_volume = st.number_input("排尿量 (ml) - 可空白", min_value=0, max_value=2000, step=50, value=None)
        pvr_volume = st.number_input("餘尿量 PVR (ml) - 可空白", min_value=0, max_value=1000, step=10, value=None)
    
    uploaded_file = st.file_uploader("上傳尿流速圖型 (Uroflowmetry) - 可空白", type=['png', 'jpg', 'jpeg'])
    
    submit_button = st.form_submit_button("儲存單筆紀錄")
    
    if submit_button:
        date_str = record_date.strftime("%Y-%m-%d") if record_date else "未填寫"
        time_str = record_time.strftime("%H:%M") if record_time else "未填寫"
        vol_val = void_volume if void_volume is not None else None
        pvr_val = pvr_volume if pvr_volume is not None else None
        file_name = uploaded_file.name if uploaded_file else "無"

        new_record = pd.DataFrame([{
            '日期': date_str,
            '時間': time_str,
            '排尿量(ml)': vol_val,
            '餘尿量(ml)': pvr_val,
            '尿流速圖檔名': file_name
        }])
        
        st.session_state.diary_data = pd.concat([st.session_state.diary_data, new_record], ignore_index=True)
        st.success("✅ 紀錄已成功儲存！")

# ================= 2. 歷史紀錄列表 =================
st.header("📋 詳細紀錄列表")
if not st.session_state.diary_data.empty:
    st.dataframe(st.session_state.diary_data, use_container_width=True)
else:
    st.info("目前尚無紀錄。")

# ================= 3. 數據變化與統計 (日/週) =================
st.header("📊 趨勢變化分析")
if not st.session_state.diary_data.empty:
    df = st.session_state.diary_data.copy()
    
    # 為了繪製連續的時間趨勢圖，我們過濾出「日期」與「時間」都有填寫的資料
    df_time = df[(df['日期'] != "未填寫") & (df['時間'] != "未填寫")].copy()
    
    if not df_time.empty:
        # 將日期與時間合併為完整的 Datetime 格式，做為 X 軸
        df_time['記錄時間'] = pd.to_datetime(df_time['日期'].astype(str) + ' ' + df_time['時間'].astype(str))
        df_time = df_time.sort_values('記錄時間')
        
        # 確保排尿與餘尿量為數字格式，如果該次沒填寫則補 0 (確保折線圖連貫)
        df_time['排尿量(ml)'] = pd.to_numeric(df_time['排尿量(ml)']).fillna(0)
        df_time['餘尿量(ml)'] = pd.to_numeric(df_time['餘尿量(ml)']).fillna(0)

        tab1, tab2 = st.tabs(["水量趨勢 (排尿與餘尿)", "每日排尿次數"])
        
        with tab1:
            # 使用 Plotly 一次繪製兩條曲線 (y 軸傳入兩個欄位)
            fig_trend = px.line(df_time, x='記錄時間', y=['排尿量(ml)', '餘尿量(ml)'], 
                               title="每小時排尿量與餘尿量時間趨勢圖", 
                               labels={'value': '容量 (ml)', 'variable': '紀錄項目', '記錄時間': '時間'},
                               markers=True,
                               # 設定不同顏色：排尿量為藍色，餘尿量為紅色
                               color_discrete_map={'排尿量(ml)': '#42A5F5', '餘尿量(ml)': '#EF5350'})
                               
            # 優化圖例顯示名稱 (移除括號讓標示更美觀)
            newnames = {'排尿量(ml)':'排尿量', '餘尿量(ml)': '餘尿量'}
            fig_trend.for_each_trace(lambda t: t.update(name = newnames[t.name],
                                                        legendgroup = newnames[t.name],
                                                        hovertemplate = t.hovertemplate.replace(t.name, newnames[t.name])))
                                                        
            st.plotly_chart(fig_trend, use_container_width=True)
            
        with tab2:
            # 保留原本的「排尿次數」統計
            df_valid_date = df[df['日期'] != "未填寫"].copy()
            df_valid_date['日期'] = pd.to_datetime(df_valid_date['日期'])
            df_valid_date['排尿量(ml)'] = pd.to_numeric(df_valid_date['排尿量(ml)'])
            
            daily_summary = df_valid_date.groupby('日期').agg(
                總排尿量=('排尿量(ml)', 'sum'),
                排尿次數=('排尿量(ml)', 'count'),
                最大單次尿量=('排尿量(ml)', 'max')
            ).reset_index().fillna(0)
            
            fig_freq = px.line(daily_summary, x='日期', y='排尿次數', 
                               title="每日總排尿次數變化", markers=True,
                               color_discrete_sequence=['#FF7043'])
            st.plotly_chart(fig_freq, use_container_width=True)
            
        # 臨床實用指標提示
        st.subheader("💡 臨床摘要指標")
        if not daily_summary.empty:
            avg_vol = daily_summary['總排尿量'].mean()
            max_vol = daily_summary['最大單次尿量'].max()
            st.write(f"- **平均每日總排尿量**: {avg_vol:.0f} ml")
            st.write(f"- **最大單次排尿量 (Capacity)**: {max_vol:.0f} ml")
    else:
        st.info("請至少輸入一筆包含「日期」與「時間」的紀錄，系統才能為您繪製趨勢圖表。")
