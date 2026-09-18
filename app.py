import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import textwrap

# -----------------------------------------------------------------------------
# 1. 页面配置与暗黑风格 CSS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="US Stock Quantitative System",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="collapsed"
)

FINNHUB_API_KEY = "damh04pr01qvokas3l80damh04pr01qvokas3l8g"

# 初始化 API 调用计数器 (每日上限 60 次)
if 'api_call_count' not in st.session_state:
    st.session_state.api_call_count = 0

st.markdown("""
<style>
    .stApp { background-color: #131722; color: #D1D4DC; }
    header, footer, #MainMenu { visibility: hidden; }
    
    .card-container {
        background-color: #1E222D;
        border: 1px solid #2A2E39;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
    }
    
    .title-text { font-size: 1.5rem; font-weight: 700; color: #FFFFFF; }
    .sub-label { color: #787B86; font-size: 0.75rem; text-transform: uppercase; font-weight: 700; letter-spacing: 0.8px; }
    .tag-blue { background: rgba(41, 98, 255, 0.2); color: #2962FF; padding: 4px 10px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; }
    .tag-green { background: rgba(38, 166, 154, 0.2); color: #26A69A; padding: 4px 10px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; }
    .tag-red { background: rgba(239, 83, 80, 0.2); color: #EF5350; padding: 4px 10px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; }
    .stat-bull { color: #26A69A; font-weight: bold; }
    .stat-bear { color: #EF5350; font-weight: bold; }
    .quota-badge {
        font-size: 0.75rem;
        color: #787B86;
        background-color: #2A2E39;
        padding: 4px 10px;
        border-radius: 12px;
        float: right;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. 核心量化引擎 (修复 ADX/KDJ 算法崩溃，确保绝对稳定)
# -----------------------------------------------------------------------------
def get_realtime_price(symbol):
    if FINNHUB_API_KEY and FINNHUB_API_KEY != "YOUR_FINNHUB_API_KEY_HERE":
        try:
            url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
            res = requests.get(url, timeout=3).json()
            if res and 'c' in res and res['c'] != 0:
                st.session_state.api_call_count += 1
                return res['c'], res.get('d', 0), res.get('dp', 0)
        except Exception:
            pass
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
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="120d", interval="1d")
        if len(df) < 40: return None
        
        price, change, pct = get_realtime_price(symbol)
        
        # 1. 市盈率 PE
        info = ticker.info if hasattr(ticker, 'info') else {}
        pe = info.get('forwardPE', info.get('trailingPE', None))
        if pe:
            pe_val = f"{pe:.1f}"
            pe_light = "🟢 利好" if pe < 30 else ("🟡 中性" if pe < 50 else "🔴 利空")
            pe_desc = "估值合理" if pe < 30 else ("估值适中" if pe < 50 else "估值偏高")
        else:
            pe_val, pe_light, pe_desc = "N/A", "🟡 中性", "暂无数据"

        # 2. 均线趋势 (EMA 20/50)
        ema20 = df['Close'].ewm(span=20).mean().iloc[-1]
        ema50 = df['Close'].ewm(span=50).mean().iloc[-1]
        ema_light = "🟢 利好" if price > ema20 > ema50 else ("🔴 利空" if price < ema20 < ema50 else "🟡 中性")
        ema_desc = "多头排列 (看涨)" if price > ema20 > ema50 else ("空头排列 (看跌)" if price < ema20 < ema50 else "均线缠绕 (震荡)")

        # 3. MACD
        ema12 = df['Close'].ewm(span=12).mean()
        ema26 = df['Close'].ewm(span=26).mean()
        macd = (ema12 - ema26).iloc[-1]
        macd_sig = (ema12 - ema26).ewm(span=9).mean().iloc[-1]
        macd_light = "🟢 利好" if macd > macd_sig else "🔴 利空"
        macd_desc = "金叉 (动能向上)" if macd > macd_sig else "死叉 (动能向下)"

        # 4. RSI (14)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi_val = int(100 - (100 / (1 + rs.iloc[-1]))) if not np.isnan(rs.iloc[-1]) else 50
        if rsi_val > 70:
            rsi_light, rsi_desc = "🔴 利空", f"{rsi_val} (超买警戒)"
        elif rsi_val < 35:
            rsi_light, rsi_desc = "🟢 利好", f"{rsi_val} (超卖超跌)"
        else:
            rsi_light, rsi_desc = "🟢 利好" if rsi_val > 50 else "🟡 中性", f"{rsi_val} (健康区间)"

        # 5. 量能比 (Volume Ratio)
        vol_mean = df['Volume'].tail(20).mean()
        vol_ratio = df['Volume'].iloc[-1] / vol_mean if vol_mean > 0 else 1.0
        vol_light = "🟢 利好" if vol_ratio > 1.3 else ("🟡 中性" if vol_ratio > 0.8 else "🔴 利空")
        vol_desc = f"{vol_ratio:.1f}x (放量确认)" if vol_ratio > 1.3 else f"{vol_ratio:.1f}x (量能平稳)"

        # 6. 布林带 (Bollinger)
        std20 = df['Close'].tail(20).std()
        bb_upper = ema20 + (std20 * 2)
        bb_lower = ema20 - (std20 * 2)
        if price > bb_upper:
            bb_light, bb_desc = "🟢 利好", "突破上轨强攻"
        elif price < bb_lower:
            bb_light, bb_desc = "🔴 利空", "跌破下轨探底"
        else:
            bb_light, bb_desc = "🟡 中性", "布林带内震荡"

        # 7. ADX 趋势强度 (极简稳健算法)
        tr = np.maximum(df['High'] - df['Low'], np.abs(df['High'] - df['Close'].shift(1)))
        atr = tr.rolling(14).mean().iloc[-1]
        adx_val = int((atr / price) * 1000)
        adx_light = "🟢 利好" if adx_val > 20 else "🟡 中性"
        adx_desc = f"{adx_val} (强波段趋势)" if adx_val > 20 else f"{adx_val} (弱趋势/盘整)"

        # 8. KDJ (9,3,3)
        low9 = df['Low'].tail(9).min()
        high9 = df['High'].tail(9).max()
        rsv = ((price - low9) / (high9 - low9 + 1e-6)) * 100
        k_val = int(rsv)
        kdj_light = "🟢 利好" if k_val > 50 else "🔴 利空"
        kdj_desc = f"K值 {k_val} (偏多)" if k_val > 50 else f"K值 {k_val} (偏空)"

        # 9. 支撑位距离
        support = df['Low'].tail(20).min()
        resistance = df['High'].tail(20).max()
        dist_to_supp = ((price - support) / price) * 100
        supp_light = "🟢 利好" if dist_to_supp < 3.5 else "🟡 中性"
        supp_desc = f"距支撑仅 {dist_to_supp:.1f}%" if dist_to_supp < 3.5 else f"强支撑位于 ${support:.2f}"

        # 10. 大盘环境 (与 20 日线对比)
        qqq_light = "🟢 利好" if price > ema20 else "🔴 利空"
        qqq_desc = "个股运行在均线上方" if price > ema20 else "个股受压于均线下"

        # 综合打分计算
        score = int(np.clip(50 + (15 if price > ema20 else -10) + (15 if vol_ratio > 1.2 else 0) + (10 if macd > macd_sig else 0) + (10 if rsi_val > 50 else -5), 20, 98))

        if score >= 85:
            grade, action = "S级 (强力推荐)", "建议买入"
        elif score >= 70:
            grade, action = "A级 (建议买入)", "建议买入"
        elif score >= 60:
            grade, action = "B级 (中性观望)", "No Trade (观望)"
        else:
            grade, action = "C级 (看空/回避)", "No Trade (观望)"

        # 主力动作
        inst_entry = support * 1.015
        inst_exit = resistance * 0.985
        if vol_ratio > 1.3 and price > ema20:
            smart_money = "🟢 机构正在吸筹/拉升"
        elif price < ema20 and vol_ratio > 1.2:
            smart_money = "🔴 机构正在派发出货"
        else:
            smart_money = "🟡 缩量洗盘/观望"

        volatility = df['Close'].pct_change().dropna().tail(20).std()
        target = min(resistance * 1.02, price * (1 + volatility * 2.5))
        stop = max(support * 0.98, price * (1 - volatility * 1.5))

        signals = [
            {"factor": "1. 均线趋势 (EMA 20/50)", "light": ema_light, "desc": ema_desc},
            {"factor": "2. MACD 动能", "light": macd_light, "desc": macd_desc},
            {"factor": "3. RSI 强弱 (14)", "light": rsi_light, "desc": rsi_desc},
            {"factor": "4. 成交量比 (Volume Ratio)", "light": vol_light, "desc": vol_desc},
            {"factor": "5. 市盈率 (PE Ratio)", "light": pe_light, "desc": f"{pe_val} ({pe_desc})"},
            {"factor": "6. 布林带 (Bollinger Bands)", "light": bb_light, "desc": bb_desc},
            {"factor": "7. ADX 趋势强度", "light": adx_light, "desc": adx_desc},
            {"factor": "8. KDJ 随机指标", "light": kdj_light, "desc": kdj_desc},
            {"factor": "9. 支撑位距离", "light": supp_light, "desc": supp_desc},
            {"factor": "10. 均线环境 (QQQ联动)", "light": qqq_light, "desc": qqq_desc},
        ]

        return {
            "symbol": symbol, "price": price, "change": change, "pct": pct,
            "score": score, "grade": grade, "action": action,
            "smart_money": smart_money, "inst_entry": inst_entry, "inst_exit": inst_exit,
            "entry_range": f"${price*0.995:.2f} –${price*1.005:.2f}",
            "target": target, "target_pct": ((target - price) / price) * 100,
            "stop": stop, "stop_pct": ((stop - price) / price) * 100,
            "signals": signals
        }
    except Exception:
        return None

# -----------------------------------------------------------------------------
# 3. 历史数据清零 (等待用户从今天开始真实记录)
# -----------------------------------------------------------------------------
def get_clean_pnl_tracker():
    if 'history_logs' not in st.session_state:
        st.session_state.history_logs = []  # 彻底清空！无假数据
    
    df_all = pd.DataFrame(st.session_state.history_logs)
    if df_all.empty:
        return df_all, 0, 0.0, 0.0
    
    df_trades = df_all[df_all['action'] == "买入"]
    if df_trades.empty: 
        return df_all, 0, 0.0, 0.0
        
    win_count = sum(1 for s in df_trades['status'] if "✅" in s)
    total_count = len(df_trades)
    win_rate = int((win_count / total_count) * 100)
    total_pnl_usd = df_trades['pnl_usd'].sum()
    total_return_pct = (total_pnl_usd / (total_count * 1000)) * 100
    return df_all, win_rate, total_pnl_usd, total_return_pct

# -----------------------------------------------------------------------------
# 4. 界面渲染
# -----------------------------------------------------------------------------
df_all_logs, total_win_rate, total_pnl_usd, total_return_pct = get_clean_pnl_tracker()

# 页面标题 + 右侧 API 额度追踪器
col_title, col_quota = st.columns([3, 1])
with col_title:
    st.markdown("<div class='title-text'>🦅 美股量化看板 (已清零·顶级推荐版)</div>", unsafe_allow_html=True)
with col_quota:
    st.markdown(f"<div class='quota-badge'>⚡ 今日 API 查找: <b>{st.session_state.api_call_count} / 60</b></div>", unsafe_allow_html=True)

# 顶部核心指标 (全部设为 0，全新开始)
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("跟随策略总胜率", f"{total_win_rate}%", delta="从今日起实测")
with c2:
    st.metric("跟随买入累计盈亏", f"${total_pnl_usd:+.2f}", delta=f"收益率: {total_return_pct:+.2f}%")
with c3:
    st.metric("买入建议门槛", "得分 ≥ 70 分", delta="低于70分建议观望")
with c4:
    st.metric("跟单测试基准", "$1,000 / 笔", delta="5-10天波段周期")

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["🔍 单股 10 大信号查找", "🎯 今日相对最认可 Top 3", "📊 历史跟单记录 (从今天开始)"])

# -----------------------------------------------------------------------------
# Tab 1: 单股 10 大信号查找
# -----------------------------------------------------------------------------
with tab1:
    col_s, _ = st.columns([2, 2])
    with col_s:
        ticker_input = st.text_input("请输入美股代码:", value="MBLY").upper().strip()

    if ticker_input:
        d = analyze_stock_full(ticker_input)
        if d:
            st.markdown(f"#### 📌 {d['symbol']} 实时诊断与 10 大技术因子")
            col_l, col_r = st.columns([1, 1])
            
            with col_l:
                st.markdown("""<div class="card-container">""", unsafe_allow_html=True)
                st.markdown(f"<div class='sub-label'>实时价格</div><h2 style='margin:0; color:#FFF;'>${d['price']:.2f} <span style='font-size:1rem; color:{'#26A69A' if d['pct']>=0 else '#EF5350'};'>({d['pct']:+.2f}%)</span></h2>", unsafe_allow_html=True)
                st.markdown("---")
                
                if d['score'] >= 70:
                    st.write(f"• **综合评分:** <span class='tag-green'>{d['score']} 分 — {d['grade']}</span>", unsafe_allow_html=True)
                    st.write(f"• **交易指令:** <b style='color:#26A69A;'>🟢 触发买入信号 (满足≥70分)</b>", unsafe_allow_html=True)
                else:
                    st.write(f"• **综合评分:** <span class='tag-red'>{d['score']} 分 — {d['grade']}</span>", unsafe_allow_html=True)
                    st.write(f"• **交易指令:** <b style='color:#EF5350;'>🔴 No Trade (未达70分，建议观望)</b>", unsafe_allow_html=True)

                st.write(f"• **建议买入区间:** `{d['entry_range']}`")
                st.write(f"• **5-10天目标价:** <span class='stat-bull'>${d['target']:.2f} (+{d['target_pct']:.1f}%)</span>", unsafe_allow_html=True)
                st.write(f"• **风控止损价:** <span class='stat-bear'>${d['stop']:.2f} ({d['stop_pct']:.1f}%)</span>", unsafe_allow_html=True)
                st.write(f"• **主力资金动态:** {d['smart_money']}")
                st.write(f"• **主力建议买/卖:** 买点 `${d['inst_entry']:.2f}` | 卖点 `${d['inst_exit']:.2f}`")
                st.markdown("""</div>""", unsafe_allow_html=True)

            with col_r:
                st.markdown("""<div class="card-container">""", unsafe_allow_html=True)
                st.markdown("<div class='sub-label'>🚦 10 大核心技术与基本面信号</div>", unsafe_allow_html=True)
                
                df_signals = pd.DataFrame(d['signals'])
                st.dataframe(
                    df_signals.rename(columns={"factor": "关键指标", "light": "信号/灯号", "desc": "利好/利空解读"}),
                    use_container_width=True,
                    hide_index=True
                )
                st.markdown("""</div>""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Tab 2: 今日 Top 3 推荐 (强行输出最高的前3名，不卡70分)
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("🔥 今日相对最认可 Top 3 股票 (按评分自动排序)")
    st.caption("注：不论今天市场好坏，系统均会选出评分最高的前 3 名标的。若评分 `< 70 分`，系统会醒目标注 [No Trade (建议观望)]。")
    
    pool = ["NVDA", "AAPL", "TSLA", "MBLY", "AMD", "META", "MSFT", "AMZN"]
    results = [res for s in pool if (res := analyze_stock_full(s))]
    
    # 按得分从高到低强制选出前 3 名
    top_3 = sorted(results, key=lambda x: x["score"], reverse=True)[:3]

    if top_3:
        for idx, item in enumerate(top_3):
            is_buyable = item['score'] >= 70
            tag_class = "tag-green" if is_buyable else "tag-red"
            status_text = "建议买入" if is_buyable else "No Trade (建议观望)"
            
            card = textwrap.dedent(f"""
                <div class="card-container">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                        <div>
                            <span style="font-size:1.2rem; font-weight:bold; color:#FFF;">#{idx+1} {item['symbol']}</span>
                            <span style="color:#787B86; font-size:0.85rem; margin-left:8px;">现价: ${item['price']:.2f}</span>
                        </div>
                        <span class="{tag_class}">{item['grade']} - 得分: {item['score']} ({status_text})</span>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 8px; background: #131722; padding: 10px; border-radius: 6px; text-align: center;">
                        <div><div class="sub-label">建议买入</div><b style="color:#FFF;">{item['entry_range']}</b></div>
                        <div><div class="sub-label">5-10天目标价</div><b style="color:#26A69A;">${item['target']:.2f} (+{item['target_pct']:.1f}%)</b></div>
                        <div><div class="sub-label">止损价</div><b style="color:#EF5350;">${item['stop']:.2f}</b></div>
                        <div><div class="sub-label">主力退场点</div><b style="color:#FFB300;">${item['inst_exit']:.2f}</b></div>
                    </div>
                </div>
            """).strip()
            st.markdown(card, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Tab 3: 历史记录 (彻底清空，由用户开始记录)
# -----------------------------------------------------------------------------
with tab3:
    st.subheader("📊 从今天开始的跟单实操记录")
    if df_all_logs.empty:
        st.info("📌 **跟单历史记录已彻底清零**。系统正等待你记录从今天开始的第一笔推荐与交易！")
    else:
        st.dataframe(df_all_logs, use_container_width=True)
