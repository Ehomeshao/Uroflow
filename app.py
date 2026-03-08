import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from scipy.signal import butter, filtfilt
import soundfile as sf
import io

# 設定頁面與繁體中文
st.set_page_config(page_title="智慧排尿日記", layout="centered")
st.title("💧 智慧排尿日記 (Patient Portal)")

# ================= 核心演算法：音訊轉尿流速 =================
def process_sonouroflow(audio_bytes, void_volume):
    # 讀取音訊
    data, sr = sf.read(io.BytesIO(audio_bytes))
    if len(data.shape) > 1:
        data = data.mean(axis=1) # 轉為單聲道
        
    # 高通濾波 300Hz
    nyquist = sr / 2
    b, a = butter(4, 300 / nyquist, btype='high')
    filtered_signal = filtfilt(b, a, data)
    
    # 計算 RMS
    frame_size = 8820
    hop_length = 4410
    rms_values = []
    for i in range(0, len(filtered_signal), hop_length):
        frame_end = min(i + frame_size, len(filtered_signal))
        current_frame = filtered_signal[i:frame_end]
        if len(current_frame) > 0:
            rms = np.sqrt(np.mean(current_frame**2))
            rms_values.append(rms)
    rms_values = np.array(rms_values)
    rms_time = np.arange(len(rms_values)) * hop_length / sr
    
    # 移動平均平滑 window=9
    filter_rms = pd.Series(rms_values).rolling(window=9, min_periods=1, center=True).mean().values
    
    # 面積轉換與排尿量校正
    area = np.trapezoid(filter_rms, x=rms_time)
    if area > 0 and void_volume > 0:
        truevalue = np.round(filter_rms * (void_volume / area), 1)
    else:
        truevalue = np.zeros_like(filter_rms)
        
    return rms_time, truevalue

# ================= 初始化暫存資料庫 =================
if 'diary_data' not in st.session_state:
    st.session_state.diary_data = pd.DataFrame(columns=[
        '日期', '時間', '排尿量(ml)', '餘尿量(ml)', '有尿流圖'
    ])

# ================= 1. 紀錄輸入區 =================
st.header("📝 新增紀錄")

# 這裡不使用 st.form，以達成勾選 Checkbox 立即顯示上傳區的互動效果
col1, col2 = st.columns(2)
with col1:
    record_date = st.date_input("日期 (請選擇)", value=None)
    record_time = st.time_input("時間 (請選擇)", value=None)
with col2:
    void_volume = st.number_input("排尿量 (ml) - 可空白", min_value=0, max_value=2000, step=50, value=None)
    pvr_volume = st.number_input("餘尿量 PVR (ml) - 可空白", min_value=0, max_value=1000, step=10, value=None)

# 提供病患選擇是否上傳音訊
need_audio = st.checkbox("🎙️ 我要附上排尿錄音檔，由 AI 預測尿流速圖")
uploaded_audio = None
if need_audio:
    st.info("💡 提醒：若要由音訊分析尿流速，請務必於上方填寫「排尿量」。")
    uploaded_audio = st.file_uploader("上傳錄音檔 (WAV格式)", type=['wav'])

# 儲存按鈕
if st.button("儲存紀錄", type="primary"):
    # 邏輯檢查：如果有傳音訊，但沒填尿量，給予警告並不予儲存
    if need_audio and uploaded_audio is not None and (void_volume is None or void_volume <= 0):
        st.error("⚠️ 演算法需要您的『排尿量』來進行校正計算，請先填寫排尿量再儲存。")
    else:
        # 資料整理
        date_str = record_date.strftime("%Y-%m-%d") if record_date else "未填寫"
        time_str = record_time.strftime("%H:%M") if record_time else "未填寫"
        has_plot = "是" if (need_audio and uploaded_audio is not None) else "否"

        # 寫入資料庫
        new_record = pd.DataFrame([{
            '日期': date_str, '時間': time_str,
            '排尿量(ml)': void_volume, '餘尿量(ml)': pvr_volume, '有尿流圖': has_plot
        }])
        st.session_state.diary_data = pd.concat([st.session_state.diary_data, new_record], ignore_index=True)
        st.success("✅ 紀錄已成功儲存！")
        
        # 若有音訊則執行分析與畫圖
        if need_audio and uploaded_audio is not None:
            with st.spinner('正在使用 Sonouroflow 演算法分析音訊...'):
                audio_bytes = uploaded_audio.read()
                try:
                    time_arr, flow_arr = process_sonouroflow(audio_bytes, void_volume)
                    
                    fig_uroflow = go.Figure()
                    fig_uroflow.add_trace(go.Scatter(x=time_arr, y=flow_arr, mode='lines', line=dict(color='blue', width=2), name='Flowrate'))
                    fig_uroflow.update_layout(
                        title="本次預測尿流速圖型 (Predicted Uroflowmetry)",
                        xaxis_title="Time (s)", yaxis_title="Flowrate (ml/s)",
                        xaxis_range=[0, max(100, max(time_arr))],
                        yaxis_range=[0, max(50, max(flow_arr)*1.2)],
                        height=400
                    )
                    st.plotly_chart(fig_uroflow, use_container_width=True)
                except Exception as e:
                    st.error(f"音訊解析失敗，請確認檔案格式是否正確。({e})")

st.divider()

# ================= 2. 歷史紀錄列表 =================
st.header("📋 詳細紀錄列表")
if not st.session_state.diary_data.empty:
    st.dataframe(st.session_state.diary_data, use_container_width=True)
else:
    st.info("目前尚無紀錄。")

# ================= 3. 趨勢變化分析 =================
st.header("📊 趨勢變化分析")
if not st.session_state.diary_data.empty:
    df = st.session_state.diary_data.copy()
    df_time = df[(df['日期'] != "未填寫") & (df['時間'] != "未填寫")].copy()
    
    if not df_time.empty:
        df_time['記錄時間'] = pd.to_datetime(df_time['日期'].astype(str) + ' ' + df_time['時間'].astype(str))
        df_time = df_time.sort_values('記錄時間')
        df_time['排尿量(ml)'] = pd.to_numeric(df_time['排尿量(ml)']).fillna(0)
        df_time['餘尿量(ml)'] = pd.to_numeric(df_time['餘尿量(ml)']).fillna(0)

        tab1, tab2 = st.tabs(["水量趨勢 (排尿與餘尿)", "每日排尿次數"])
        
        with tab1:
            fig_trend = px.line(df_time, x='記錄時間', y=['排尿量(ml)', '餘尿量(ml)'], 
                               title="每小時排尿量與餘尿量時間趨勢圖", 
                               labels={'value': '容量 (ml)', 'variable': '紀錄項目', '記錄時間': '時間'},
                               markers=True,
                               color_discrete_map={'排尿量(ml)': '#42A5F5', '餘尿量(ml)': '#EF5350'})
            
            newnames = {'排尿量(ml)':'排尿量', '餘尿量(ml)': '餘尿量'}
            fig_trend.for_each_trace(lambda t: t.update(name = newnames[t.name],
                                                        legendgroup = newnames[t.name],
                                                        hovertemplate = t.hovertemplate.replace(t.name, newnames[t.name])))
            st.plotly_chart(fig_trend, use_container_width=True)
            
        with tab2:
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
    else:
        st.info("請至少輸入一筆包含「日期」與「時間」的紀錄，系統才能為您繪製趨勢圖表。")
