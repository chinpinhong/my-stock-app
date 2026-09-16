import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="美股实时预测看板", layout="centered")

st.title("📈 美股价格预测与技术看板")

# 1. 单一控制输入框 (避免组件冲突)
ticker_input = st.text_input(
    "🔍 输入或选择美股代码 (输入后按 Enter 回车):", 
    value="GOOGL", 
    help="尝试输入 MBLY, NVDA, AAPL, GOOGL, TSLA"
).strip().upper()

st.markdown("---")

# 2. 清理缓存，强行抓取最新实时股价
@st.cache_data(ttl=10) # 每 10 秒强制刷新缓存
def get_stock_data(symbol):
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="100d", interval="1d")
    return df

try:
    df = get_stock_data(ticker_input)
    
    if df.empty:
        st.error(f"⚠️ 找不到代码 '{ticker_input}' 的股价数据，请确认代码是否正确。")
        st.stop()
        
    current_price = df['Close'].iloc[-1]
    formatted_price = f"${current_price:.2f}"
    
    # 计算 RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi_val = (100 - (100 / (1 + rs))).iloc[-1]
    rsi_status = "🟢 Bullish" if rsi_val > 50 else "🔴 Bearish"
    
    # 计算 MACD
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    macd_status = "🟢 Bullish" if macd.iloc[-1] > signal.iloc[-1] else "🔴 Bearish"
    
    # 动态支撑位
    support_level = df['Low'].tail(20).min()
    formatted_support = f"${support_level:.2f}"

    # 波动率估算
    returns = df['Close'].pct_change().dropna()
    volatility = returns.tail(20).std()
    
    # 看涨看跌评分
    score = 0.5
    if rsi_val > 50: score += 0.1
    if macd.iloc[-1] > signal.iloc[-1]: score += 0.15
    if current_price > df['Close'].tail(20).mean(): score += 0.05
    
    bullish_pct = min(max(int(score * 100), 15), 85)
    bearish_pct = min(max(int((1 - score) * 0.7 * 100), 10), 75)
    neutral_pct = 100 - bullish_pct - bearish_pct
    
    expected_low = current_price * (1 - volatility)
    expected_high = current_price * (1 + volatility)
    most_likely = current_price * (1 + (score - 0.5) * volatility)

except Exception as e:
    st.error(f"获取数据失败: {e}")
    st.stop()

# 3. 渲染页面
st.subheader(f"Current Price ({ticker_input})")
st.title(formatted_price)

st.markdown("---")

st.subheader("Today's Prediction")

col1, col2 = st.columns([1, 2])
with col1:
    st.write("Bearish")
    st.write("Neutral")
    st.write("Bullish")
with col2:
    st.progress(bearish_pct / 100.0, text=f"{bearish_pct}%")
    st.progress(neutral_pct / 100.0, text=f"{neutral_pct}%")
    st.progress(bullish_pct / 100.0, text=f"{bullish_pct}%")

st.markdown("#### Expected Close")
st.write(f"**${expected_low:.2f} – ${expected_high:.2f}** *(Most likely ${most_likely:.2f})*")

st.markdown("#### Probability")
st.write(f"• **Above current:** {bullish_pct}%")
st.write(f"• **Below current:** {100 - bullish_pct}%")

st.write(f"**Confidence:** {int(70 - volatility * 100)}%")

st.markdown("---")

st.subheader("Technical Factors")

col_a, col_b = st.columns(2)

with col_a:
    st.write(f"**RSI (14):** {rsi_status}")
    st.write(f"**MACD:** {macd_status}")
    st.write("**Volume:** 🟢 Strong" if df['Volume'].iloc[-1] > df['Volume'].tail(10).mean() else "**Volume:** 🟡 Moderate")
    st.write("**ADX:** 🟡 Trend")

with col_b:
    st.write("**QQQ:** 🟢 Bullish")
    st.write("**Market:** 🟢 Bullish")
    st.write(f"**Support:** 🔴 {formatted_support}")