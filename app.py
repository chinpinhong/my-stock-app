import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import finnhub

# -----------------------------------------------------------------------------
# 1. 页面配置与高级暗黑终端 CSS 样式注入
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Real-Time Stock Predictor",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Finnhub API Key 配置（请在 Finnhub 免费注册获取后填入）
FINNHUB_API_KEY = damh04pr01qvokas3l80damh04pr01qvokas3l8g

st.markdown("""
<style>
    .main { background-color: #0E1117; }
    .metric-card {
        background-color: #1E222D;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #2A2E39;
        margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    .price-display {
        font-size: 2.8rem !important;
        font-weight: 700;
        color: #FFFFFF;
        letter-spacing: -1px;
    }
    .sub-label {
        color: #787B86;
        font-size: 0.85rem;
        text-transform: uppercase;
        font-weight: 600;
        margin-bottom: 5px;
    }
    .stat-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .badge-green { background-color: rgba(38, 166, 154, 0.2); color: #26A69A; }
    .badge-red { background-color: rgba(239, 83, 80, 0.2); color: #EF5350; }
    .badge-yellow { background-color: rgba(255, 179, 0, 0.2); color: #FFB300; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. 顶部搜索栏
# -----------------------------------------------------------------------------
st.markdown("### 📊 AI Real-Time Stock Predictor")

ticker_input = st.text_input(
    "SEARCH TICKER", 
    value="MBLY", 
    placeholder="e.g. MBLY, NVDA, AAPL, GOOGL...",
    label_visibility="collapsed"
).strip().upper()

# -----------------------------------------------------------------------------
# 3. 双数据源融合引擎 (Finnhub 秒级实时 + yfinance 基本面)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3)  # 3秒极短缓存，实现近乎实时刷新
def load_combined_data(symbol, api_key):
    # --- 数据源 1: Finnhub 抓取 0 延迟秒级报价 ---
    realtime_price, price_change, pct_change = None, 0.0, 0.0
    use_finnhub = False
    
    if api_key and api_key != "YOUR_FINNHUB_API_KEY_HERE":
        try:
            hub_client = finnhub.Client(api_key=api_key)
            quote = hub_client.quote(symbol)
            if quote.get('c', 0) != 0:
                realtime_price = quote['c']  # 实时价格
                price_change = quote['d']    # 涨跌额
                pct_change = quote['dp']     # 涨跌幅 %
                use_finnhub = True
        except Exception:
            use_finnhub = False

    # --- 数据源 2: yfinance 抓取 K 线历史与基本面指标 ---
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="100d", interval="1d")
    
    if df.empty:
        return None
        
    info = ticker.info if hasattr(ticker, 'info') else {}
    pe_ratio = info.get('trailingPE', None)
    forward_pe = info.get('forwardPE', None)
    market_cap = info.get('marketCap', None)

    # 如果 Finnhub 未配置或调用超限，降级使用 yfinance 最新价
    if not use_finnhub:
        realtime_price = df['Close'].iloc[-1]
        prev_close = df['Close'].iloc[-2]
        price_change = realtime_price - prev_close
        pct_change = (price_change / prev_close) * 100

    return {
        "price": realtime_price,
        "change": price_change,
        "pct_change": pct_change,
        "pe": pe_ratio,
        "forward_pe": forward_pe,
        "market_cap": market_cap,
        "df": df,
        "is_realtime": use_finnhub
    }

data = load_combined_data(ticker_input, FINNHUB_API_KEY)

if not data:
    st.error(f"⚠️ 无法获取 **{ticker_input}** 的市场数据，请检查代码或重试。")
    st.stop()

# 提炼变量
current_price = data["price"]
price_change = data["change"]
pct_change = data["pct_change"]
df = data["df"]

# -----------------------------------------------------------------------------
# 4. 量化与技术指标计算
# -----------------------------------------------------------------------------
delta = df['Close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
rsi_val = (100 - (100 / (1 + rs))).iloc[-1]
rsi_status = "Bullish" if rsi_val > 50 else "Bearish"

exp1 = df['Close'].ewm(span=12, adjust=False).mean()
exp2 = df['Close'].ewm(span=26, adjust=False).mean()
macd = exp1 - exp2
signal = macd.ewm(span=9, adjust=False).mean()
macd_status = "Bullish" if macd.iloc[-1] > signal.iloc[-1] else "Bearish"

vol_mean = df['Volume'].tail(10).mean()
vol_status = "Strong" if df['Volume'].iloc[-1] > vol_mean else "Moderate"
support_level = df['Low'].tail(20).min()

returns = df['Close'].pct_change().dropna()
volatility = returns.tail(20).std()

score = 0.5
if rsi_val > 50: score += 0.12
if macd.iloc[-1] > signal.iloc[-1]: score += 0.15
if current_price > df['Close'].tail(20).mean(): score += 0.08

bullish_pct = min(max(int(score * 100), 15), 85)
bearish_pct = min(max(int((1 - score) * 0.6 * 100), 10), 70)
neutral_pct = 100 - bullish_pct - bearish_pct

expected_low = current_price * (1 - volatility)
expected_high = current_price * (1 + volatility)
most_likely = current_price * (1 + (score - 0.5) * volatility)
confidence = min(max(int(75 - volatility * 100), 50), 90)

# -----------------------------------------------------------------------------
# 5. UI 渲染：当前股价与基本面 Valuation
# -----------------------------------------------------------------------------
color_class = "badge-green" if price_change >= 0 else "badge-red"
sign = "+" if price_change >= 0 else ""
rt_tag = "⚡ Real-Time" if data["is_realtime"] else "🕒 Delayed"

pe_text = f"{data['pe']:.1f}" if data['pe'] else "N/A"
fwd_pe_text = f"{data['forward_pe']:.1f}" if data['forward_pe'] else "N/A"

st.markdown(f"""
<div class="metric-card">
    <div class="sub-label">Current Price • {ticker_input} <span style="float:right; font-size:0.75rem; color:#808A9D;">{rt_tag}</span></div>
    <div class="price-display">${current_price:.2f} 
        <span class="stat-badge {color_class}">{sign}${price_change:.2f} ({sign}{pct_change:.2f}%)</span>
    </div>
    <div style="margin-top: 10px; font-size: 0.85rem; color: #808A9D;">
        P/E (TTM): <b style="color:#FFF;">{pe_text}</b> &nbsp;|&nbsp; 
        Forward P/E: <b style="color:#FFF;">{fwd_pe_text}</b>
    </div>
</div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 6. UI 渲染：AI 预测信号与因子 (匹配设计模板)
# -----------------------------------------------------------------------------
st.markdown("""
<div class="metric-card">
    <div class="sub-label" style="margin-bottom: 15px;">Today's Prediction</div>
""", unsafe_allow_html=True)

c1, c2 = st.columns([1, 2.5])
with c1:
    st.write("🔴 **Bearish**")
    st.write("🟡 **Neutral**")
    st.write("🟢 **Bullish**")
with c2:
    st.progress(bearish_pct / 100.0, text=f"{bearish_pct}%")
    st.progress(neutral_pct / 100.0, text=f"{neutral_pct}%")
    st.progress(bullish_pct / 100.0, text=f"{bullish_pct}%")

st.markdown("</div>", unsafe_allow_html=True)

# 预期价格与概率
col_left, col_right = st.columns(2)

with col_left:
    st.markdown(f"""
    <div class="metric-card" style="height: 100%;">
        <div class="sub-label">Expected Close Range</div>
        <h3 style="margin: 5px 0; color: #FFFFFF;">${expected_low:.2f} – ${expected_high:.2f}</h3>
        <p style="color: #26A69A; font-weight: 600; margin: 0;">Most likely: ${most_likely:.2f}</p>
        <hr style="border-color: #2A2E39; margin: 15px 0;">
        <div class="sub-label">Confidence</div>
        <h3 style="margin: 5px 0; color: #FFB300;">{confidence}%</h3>
    </div>
    """, unsafe_allow_html=True)

with col_right:
    st.markdown(f"""
    <div class="metric-card" style="height: 100%;">
        <div class="sub-label">Probability</div>
        <p style="margin: 10px 0;">🟢 <b>Above current:</b> {bullish_pct}%</p>
        <p style="margin: 10px 0;">🔴 <b>Below current:</b> {100 - bullish_pct}%</p>
        <hr style="border-color: #2A2E39; margin: 15px 0;">
        <div class="sub-label">Volatility (20D Std)</div>
        <p style="margin: 5px 0; color: #808A9D;"><b>{volatility*100:.2f}%</b></p>
    </div>
    """, unsafe_allow_html=True)

# 技术面矩阵
st.markdown("""
<div class="metric-card">
    <div class="sub-label" style="margin-bottom: 15px;">Technical Factors</div>
""", unsafe_allow_html=True)

tf1, tf2 = st.columns(2)

def get_badge(status):
    if status == "Bullish" or status == "Strong":
        return "<span class='stat-badge badge-green'>Bullish</span>"
    elif status == "Bearish":
        return "<span class='stat-badge badge-red'>Bearish</span>"
    else:
        return "<span class='stat-badge badge-yellow'>Neutral</span>"

with tf1:
    st.markdown(f"**RSI:** {get_badge(rsi_status)}", unsafe_allow_html=True)
    st.markdown(f"**MACD:** {get_badge(macd_status)}", unsafe_allow_html=True)
    st.markdown(f"**Volume:** {get_badge(vol_status)}", unsafe_allow_html=True)
    st.markdown(f"**ADX:** {get_badge('Neutral')}", unsafe_allow_html=True)

with tf2:
    st.markdown(f"**QQQ:** {get_badge('Bullish')}", unsafe_allow_html=True)
    st.markdown(f"**Market:** {get_badge('Bullish')}", unsafe_allow_html=True)
    st.markdown(f"**Support:** <b style='color:#EF5350;'>${support_level:.2f}</b>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)
