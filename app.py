import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import textwrap
from datetime import datetime

# -----------------------------------------------------------------------------
# 1. 全局配置与 TradingView 暗黑风格 CSS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="US Stock Real-time Intelligence",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ⚠️ 在这里填入你的 Finnhub 免费 API Key (去 https://finnhub.io 注册获取)
FINNHUB_API_KEY = "damh04pr01qvokas3l80damh04pr01qvokas3l8g"

st.markdown("""
<style>
    .stApp { background-color: #131722; color: #D1D4DC; }
    header, footer, #MainMenu { visibility: hidden; }
    
    .card-container {
        background-color: #1E222D;
        border: 1px solid #2A2E39;
        border-radius: 10px;
        padding: 18px;
        margin-bottom: 15px;
    }
    
    .title-text { font-size: 1.6rem; font-weight: 700; color: #FFFFFF; }
    .sub-label { color: #787B86; font-size: 0.75rem; text-transform: uppercase; font-weight: 700; letter-spacing: 0.8px; }
    .tag-blue { background: rgba(41, 98, 255, 0.2); color: #2962FF; padding: 4px 10px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; }
    
    /* 因子状态颜色 */
    .stat-bull { color: #26A69A; font-weight: bold; }
    .stat-bear { color: #EF5350; font-weight: bold; }
    .stat-neu  { color: #FFB300; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. 实时数据抓取与预测算法引擎
# -----------------------------------------------------------------------------
def get_realtime_price(symbol):
    """优先使用 Finnhub 获取实时/盘前价格，备用 yfinance"""
    if FINNHUB_API_KEY and FINNHUB_API_KEY != "YOUR_FINNHUB_API_KEY_HERE":
        try:
            url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
            res = requests.get(url, timeout=3).json()
            if res and 'c' in res and res['c'] != 0:
                return res['c'], res.get('d', 0), res.get('dp', 0)
        except Exception:
            pass
    # 备用方案
    try:
        t = yf.Ticker(symbol).history(period="2d")
        if not t.empty:
            price = t['Close'].iloc[-1]
            prev = t['Close'].iloc[-2] if len(t) > 1 else price
            change = price - prev
            pct = (change / prev) * 100
            return price, change, pct
    except Exception:
        pass
    return 100.0, 0.0, 0.0

@st.cache_data(ttl=120)
def analyze_stock_full(symbol):
    """计算单个股票的完整预测模型与技术因子"""
    try:
        df = yf.Ticker(symbol).history(period="100d", interval="1d")
        if len(df) < 50: return None
        
        price, change, pct = get_realtime_price(symbol)
        
        # 技术指标计算
        ema20 = df['Close'].ewm(span=20).mean().iloc[-1]
        ema50 = df['Close'].ewm(span=50).mean().iloc[-1]
        vol_ratio = df['Volume'].iloc[-1] / df['Volume'].tail(20).mean()
        support = df['Low'].tail(20).min()
        resistance = df['High'].tail(20).max()
        volatility = df['Close'].pct_change().dropna().tail(20).std()
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs.iloc[-1]))
        
        # MACD
        ema12 = df['Close'].ewm(span=12).mean()
        ema26 = df['Close'].ewm(span=26).mean()
        macd = (ema12 - ema26).iloc[-1]
        macd_signal = (ema12 - ema26).ewm(span=9).mean().iloc[-1]
        
        # 概率模型
        bullish = 50 + (12 if price > ema20 else -10) + (10 if macd > macd_signal else -8) + (8 if rsi > 50 else -8)
        bullish = int(np.clip(bullish, 15, 88))
        bearish = int((100 - bullish) * 0.42)
        neutral = 100 - bullish - bearish
        
        # 推荐匹配分
        score = 60 + (15 if price > ema20 else 0) + (15 if vol_ratio > 1.2 else 0) + (10 if rsi > 50 else 0)
        
        # 波段止盈止损
        target = min(resistance * 1.02, price * (1 + volatility * 2.5))
        stop = max(support * 0.98, price * (1 - volatility * 1.5))
        rr = (target - price) / (price - stop) if (price - stop) > 0 else 1.5
        
        reasons = []
        if price > ema20: reasons.append("✓ 站稳 EMA20 关键均线")
        if vol_ratio > 1.2: reasons.append(f"✓ 量能异常放大 ({vol_ratio:.1f}倍)")
        if price > support * 1.01: reasons.append(f"✓ 获得底部支撑区间 (${support:.2f})")
        
        return {
            "symbol": symbol, "price": price, "change": change, "pct": pct,
            "bullish": bullish, "neutral": neutral, "bearish": bearish,
            "exp_low": price * (1 - volatility * 0.8),
            "exp_high": price * (1 + volatility * 1.2),
            "most_likely": price * (1 + (volatility * 0.3 if bullish > 50 else -volatility * 0.3)),
            "confidence": min(int(62 + vol_ratio * 8), 92),
            "rsi_status": "Bullish" if rsi > 50 else "Bearish",
            "macd_status": "Bullish" if macd > macd_signal else "Bearish",
            "vol_status": "Strong" if vol_ratio > 1.2 else "Normal",
            "support": support, "resistance": resistance,
            # 波段卡片数据
            "score": min(score, 98),
            "entry": f"${price*0.995:.2f}–${price*1.005:.2f}",
            "target": target, "target_pct": ((target - price) / price) * 100,
            "stop": stop, "stop_pct": ((stop - price) / price) * 100,
            "rr": rr, "reasons": reasons,
            "accumulation": min(int(vol_ratio * 35 + 25), 98)
        }
    except Exception:
        return None

# -----------------------------------------------------------------------------
# 3. 主界面渲染
# -----------------------------------------------------------------------------
st.markdown("<div class='title-text'>🦅 美股实时量化与智能预测系统</div>", unsafe_allow_html=True)
st.caption(f"状态: 运行中 • 美东时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • 适配: 盘前与开盘时段")
st.write("")

tab1, tab2 = st.tabs(["🔍 功能一：单股实时深度预测", "🎯 功能二：今日 Top 3 波段推荐"])

# -----------------------------------------------------------------------------
# 功能一：单股实时预测（你图片里的原型效果）
# -----------------------------------------------------------------------------
with tab1:
    col_in, _ = st.columns([2, 2])
    with col_in:
        ticker = st.text_input("请输入美股代码查看实时预测:", value="MBLY").upper().strip()
    
    if ticker:
        d = analyze_stock_full(ticker)
        if d:
            st.markdown(f"### 📌 {d['symbol']} 实时看板")
            
            # 原型左侧 + 右侧双列布局
            col_left, col_right = st.columns(2)
            
            with col_left:
                st.markdown("""<div class="card-container">""", unsafe_allow_html=True)
                st.markdown(f"<div class='sub-label'>Current Price</div><h1 style='margin:0; color:#FFF;'>${d['price']:.2f} <span style='font-size:1.2rem; color:{'#26A69A' if d['pct']>=0 else '#EF5350'};'>({d['pct']:+.2f}%)</span></h1>", unsafe_allow_html=True)
                st.markdown("---")
                
                st.subheader("Today's Prediction")
                st.write(f"🔴 **Bearish:** {d['bearish']}%")
                st.progress(d['bearish'] / 100)
                st.write(f"⚪ **Neutral:** {d['neutral']}%")
                st.progress(d['neutral'] / 100)
                st.write(f"🟢 **Bullish:** {d['bullish']}%")
                st.progress(d['bullish'] / 100)
                
                st.markdown("---")
                st.write(f"<b>Expected Close:</b> `${d['exp_low']:.2f} – ${d['exp_high']:.2f}`", unsafe_allow_html=True)
                st.write(f"<b>Most likely:</b> `${d['most_likely']:.2f}`", unsafe_allow_html=True)
                st.markdown("""</div>""", unsafe_allow_html=True)

            with col_right:
                st.markdown("""<div class="card-container">""", unsafe_allow_html=True)
                st.write(f"<b>Probability Above Current:</b> <span class='stat-bull'>{d['bullish']}%</span>", unsafe_allow_html=True)
                st.write(f"<b>Probability Below Current:</b> <span class='stat-bear'>{100 - d['bullish']}%</span>", unsafe_allow_html=True)
                st.write(f"<b>Confidence Level:</b> <span style='color:#FFF;'>{d['confidence']}%</span>", unsafe_allow_html=True)
                
                st.markdown("---")
                st.subheader("Technical Factors")
                st.write(f"• **RSI:** <span class='{'stat-bull' if d['rsi_status']=='Bullish' else 'stat-bear'}'>{d['rsi_status']}</span>", unsafe_allow_html=True)
                st.write(f"• **MACD:** <span class='{'stat-bull' if d['macd_status']=='Bullish' else 'stat-bear'}'>{d['macd_status']}</span>", unsafe_allow_html=True)
                st.write(f"• **Volume:** <span class='stat-bull'>{d['vol_status']}</span>", unsafe_allow_html=True)
                st.write(f"• **Support:** `${d['support']:.2f}` | **Resistance:** `${d['resistance']:.2f}`", unsafe_allow_html=True)
                st.markdown("""</div>""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 功能二：预计 3 个波段推荐卡片
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("🔥 今日量化筛选最高胜率 Top 3 标的")
    
    pool = ["NVDA", "AAPL", "TSLA", "MBLY", "AMD", "META", "MSFT", "AMZN"]
    results = []
    
    for s in pool:
        res = analyze_stock_full(s)
        if res and res["score"] >= 70:
            results.append(res)
            
    top_3 = sorted(results, key=lambda x: x["score"], reverse=True)[:3]
    
    if top_3:
        for idx, item in enumerate(top_3):
            # 使用 textwrap 彻底解决卡片 HTML 代码露出的问题
            card_html = textwrap.dedent(f"""
                <div class="card-container">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                        <div>
                            <span style="font-size:1.3rem; font-weight:bold; color:#FFF;">#{idx+1} {item['symbol']}</span>
                            <span style="color:#787B86; font-size:0.9rem; margin-left:10px;">实时价: ${item['price']:.2f}</span>
                        </div>
                        <span class="tag-blue">匹配得分: {item['score']} / 100</span>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 10px; background: #131722; padding: 12px; border-radius: 8px; text-align: center;">
                        <div>
                            <div class="sub-label">建议入场区间</div>
                            <b style="color:#FFF;">{item['entry']}</b>
                        </div>
                        <div>
                            <div class="sub-label">目标止盈 (+%)</div>
                            <b style="color:#26A69A;">${item['target']:.2f} (+{item['target_pct']:.1f}%)</b>
                        </div>
                        <div>
                            <div class="sub-label">风控止损 (-%)</div>
                            <b style="color:#EF5350;">${item['stop']:.2f} ({item['stop_pct']:.1f}%)</b>
                        </div>
                        <div>
                            <div class="sub-label">盈亏比 (R:R)</div>
                            <b style="color:#FFB300;">{item['rr']:.2f} : 1</b>
                        </div>
                    </div>
                    <div style="margin-top: 12px; font-size: 0.85rem; color: #D1D4DC;">
                        <b>推荐理由:</b> {" | ".join(item['reasons'])} <br>
                        <b>主力资金进场指数:</b> <span style="color:#26A69A;">{item['accumulation']} / 100</span>
                    </div>
                </div>
            """).strip()
            
            st.markdown(card_html, unsafe_allow_html=True)
    else:
        st.info("当前无符合高胜率标准的推荐标的，建议观望。")
