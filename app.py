import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import textwrap
import os
from datetime import datetime, timedelta

# =============================================================================
# 0. 页面配置与全局状态
# =============================================================================
st.set_page_config(
    page_title="Alpha Vector Pro | 美股量化终端",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

if 'realtime_trade_logs' not in st.session_state:
    st.session_state.realtime_trade_logs = []
if 'api_counter' not in st.session_state:
    st.session_state.api_counter = 0
if 'settled_this_session' not in st.session_state:
    st.session_state.settled_this_session = False

FINNHUB_API_KEY = "YOUR_FINNHUB_API_KEY_HERE"
PRED_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prediction_log.csv")
PRED_COLUMNS = ["logged_at", "symbol", "horizon", "entry_price", "pred_pct",
                "target_price", "due_date", "status",
                "actual_price", "actual_pct", "error_pct", "direction_hit"]

HORIZON_DAYS = {"5-10天波段": 7, "3个月中线": 63}
HORIZON_CALENDAR_DAYS = {"5-10天波段": 8, "3个月中线": 95}
HORIZON_CAP_PCT = {"5-10天波段": 25.0, "3个月中线": 50.0}

HORIZON_DAMPEN = {
    "5-10天波段": 0.85, 
    "3个月中线": 0.70
}

# =============================================================================
# 1. 还原：极致暗黑科技感 CSS 视觉样式
# =============================================================================
st.markdown("""
<style>
    .stApp { 
        background-color: #0A0D14 !important; 
        color: #CBD5E1 !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
    }
    header, footer, #MainMenu { visibility: hidden; }

    div[data-baseweb="input"] {
        background-color: #FFFFFF !important;
        border: 1px solid #3B82F6 !important;
        border-radius: 8px !important;
        color: #000000 !important;
    }
    input {
        color: #000000 !important;
        background-color: transparent !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
    }

    div[data-testid="stMarkdownContainer"] p { color: #CBD5E1 !important; }

    .terminal-card { 
        background: linear-gradient(135deg, #131824, #0F131D);
        border: 1px solid #1E2638; 
        border-radius: 12px; 
        padding: 20px;
        margin-bottom: 16px; 
        box-shadow: 0 4px 18px rgba(0,0,0,0.35); 
    }

    .terminal-title { font-size: 1.5rem; font-weight: 700; color: #F8FAFC; letter-spacing: -0.3px; }
    .sub-caption { color: #64748B; font-size: 0.75rem; text-transform: uppercase;
        font-weight: 600; letter-spacing: 0.8px; margin-bottom: 8px; }

    .tag-bull { background: rgba(16,185,129,0.12); color:#10B981; border:1px solid rgba(16,185,129,0.3);
        padding:4px 12px; border-radius:6px; font-weight:600; font-size:0.85rem; }
    .tag-bear { background: rgba(239,68,68,0.12); color:#EF4444; border:1px solid rgba(239,68,68,0.3);
        padding:4px 12px; border-radius:6px; font-weight:600; font-size:0.85rem; }
    .tag-neutral { background: rgba(245,158,11,0.12); color:#F59E0B; border:1px solid rgba(245,158,11,0.3);
        padding:4px 12px; border-radius:6px; font-weight:600; font-size:0.85rem; }

    .signal-group-bull { background: rgba(16,185,129,0.05); border:1px solid rgba(16,185,129,0.2);
        border-radius:10px; padding:14px; margin-bottom:10px; }
    .signal-group-bear { background: rgba(239,68,68,0.05); border:1px solid rgba(239,68,68,0.2);
        border-radius:10px; padding:14px; margin-bottom:10px; }
    .signal-group-neutral { background: rgba(148,163,184,0.05); border:1px solid rgba(148,163,184,0.15);
        border-radius:10px; padding:14px; margin-bottom:10px; }
    .signal-row { font-size:0.88rem; padding:5px 0; border-bottom:1px dashed rgba(148,163,184,0.1); color:#94A3B8; }
    .signal-row:last-child { border-bottom:none; }

    .risk-banner { background: rgba(245,158,11,0.08); border:1px solid rgba(245,158,11,0.25);
        border-radius:8px; padding:10px 14px; font-size:0.85rem; color:#FBBF24; margin-bottom:12px; }
    .reason-box { background: rgba(59,130,246,0.08); border:1px solid rgba(59,130,246,0.25);
        border-radius:8px; padding:12px 14px; font-size:0.88rem; color:#93C5FD; margin-top:10px; }
    .exit-box { background: rgba(16,185,129,0.08); border:1px solid rgba(16,185,129,0.25);
        border-radius:8px; padding:12px 14px; font-size:0.88rem; color:#A7F3D0; margin-top:10px; }
    .kelly-box { background: rgba(139,92,246,0.08); border:1px solid rgba(139,92,246,0.3);
        border-radius:8px; padding:12px 14px; font-size:0.88rem; color:#C4B5FD; margin-top:10px; }

    .api-badge { font-size:0.78rem; color:#64748B; background-color:#131824; border:1px solid #1E2638;
        padding:6px 14px; border-radius:20px; float:right; }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# 2. 预测校准模块
# =============================================================================
def _load_pred_log():
    if os.path.exists(PRED_LOG_PATH):
        try: return pd.read_csv(PRED_LOG_PATH)
        except Exception: pass
    return pd.DataFrame(columns=PRED_COLUMNS)

def _save_pred_log(df):
    try: df.to_csv(PRED_LOG_PATH, index=False)
    except Exception: pass

def log_prediction(symbol, horizon, entry_price, pred_pct, target_price):
    df = _load_pred_log()
    due = (datetime.now() + timedelta(days=HORIZON_CALENDAR_DAYS[horizon])).strftime("%Y-%m-%d")
    new_row = {
        "logged_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "symbol": symbol, "horizon": horizon, "entry_price": entry_price,
        "pred_pct": pred_pct, "target_price": target_price,
        "due_date": due, "status": "pending", "actual_price": np.nan,
        "actual_pct": np.nan, "error_pct": np.nan, "direction_hit": np.nan
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    _save_pred_log(df)

def settle_predictions():
    df = _load_pred_log()
    if df.empty: return
    today = datetime.now().date()
    pending = df[df["status"] == "pending"]
    for idx, row in pending.iterrows():
        try:
            due = datetime.strptime(str(row["due_date"]), "%Y-%m-%d").date()
            if due > today: continue
            hist = yf.Ticker(row["symbol"]).history(period="5d")
            if hist.empty: continue
            actual_price = float(hist["Close"].iloc[-1])
            entry = float(row["entry_price"])
            actual_pct = (actual_price - entry) / entry * 100
            error = actual_pct - float(row["pred_pct"])
            direction_hit = int(np.sign(actual_pct) == np.sign(row["pred_pct"])) if row["pred_pct"] != 0 else np.nan
            df.loc[idx, ["status", "actual_price", "actual_pct", "error_pct", "direction_hit"]] = \
                ["settled", actual_price, actual_pct, error, direction_hit]
        except Exception: continue
    _save_pred_log(df)

def get_calibration():
    df = _load_pred_log()
    settled = df[df["status"] == "settled"].dropna(subset=["pred_pct", "actual_pct"])
    if len(settled) < 3:
        return {"factor": 1.0, "n": len(settled), "win_rate": None, "mae": None}
    ratio = (settled["actual_pct"].abs() / settled["pred_pct"].abs().replace(0, np.nan)).dropna()
    factor = float(np.clip(ratio.median(), 0.5, 1.3)) if len(ratio) > 0 else 1.0
    win_rate = float(settled["direction_hit"].mean() * 100) if "direction_hit" in settled else None
    mae = float((settled["actual_pct"] - settled["pred_pct"]).abs().mean())
    return {"factor": factor, "n": len(settled), "win_rate": win_rate, "mae": mae}

# =============================================================================
# 3. 数据获取与期权情绪
# =============================================================================
def fetch_quote_data(symbol):
    try:
        t = yf.Ticker(symbol).history(period="2d")
        if not t.empty:
            price = float(t['Close'].iloc[-1])
            prev = float(t['Close'].iloc[-2]) if len(t) > 1 else price
            return price, price - prev, ((price - prev) / prev) * 100
    except Exception: pass
    return 100.0, 0.0, 0.0

@st.cache_data(ttl=300)
def fetch_vix_data():
    try:
        vix = yf.Ticker("^VIX").history(period="2d")
        if not vix.empty:
            val = float(vix['Close'].iloc[-1])
            prev = float(vix['Close'].iloc[-2]) if len(vix) > 1 else val
            return val, val - prev, ((val - prev) / prev) * 100
    except Exception: pass
    return 18.5, 0.0, 0.0

def fetch_option_sentiment(symbol):
    try:
        tk = yf.Ticker(symbol)
        opts = tk.options
        if not opts: return 1.0, "无期权数据"
        chain = tk.option_chain(opts[0])
        call_vol = chain.calls['volume'].sum()
        put_vol = chain.puts['volume'].sum()
        if call_vol > 0:
            pc_ratio = put_vol / call_vol
            if pc_ratio < 0.7: return pc_ratio, "🟢 看多 (Call强劲)"
            elif pc_ratio > 1.2: return pc_ratio, "🔴 看空 (Put避险)"
            else: return pc_ratio, "🟡 多空平衡"
    except Exception: pass
    return 1.0, "🟡 中性"

# =============================================================================
# 4. 全维度量化计算引擎 (基本面 + 技术面 + 期权 + 凯利仓位)
# =============================================================================
@st.cache_data(ttl=120)
def quant_evaluate_stock(symbol, horizon="5-10天波段"):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="1y", interval="1d")
        if len(df) < 60: return None

        price, change, pct = fetch_quote_data(symbol)
        vix_val, _, _ = fetch_vix_data()
        signals = []

        # --- A. 基本面因子 ---
        info = ticker.info if hasattr(ticker, 'info') else {}
        rev_growth = info.get('revenueGrowth', None)
        gross_margins = info.get('grossMargins', None)
        pe = info.get('forwardPE', info.get('trailingPE', None))

        if rev_growth and rev_growth > 0.15:
            signals.append({"factor": "营收同比增速", "light": "🟢 利好", "desc": f"增速 {rev_growth*100:.1f}%（高成长）", "w": 1})
        elif rev_growth and rev_growth < 0:
            signals.append({"factor": "营收同比增速", "light": "🔴 利空", "desc": f"增速 {rev_growth*100:.1f}%（下滑）", "w": -1})
        else:
            signals.append({"factor": "营收同比增速", "light": "🟡 中性", "desc": "增长平缓", "w": 0})

        if gross_margins and gross_margins > 0.45:
            signals.append({"factor": "毛利率水平", "light": "🟢 利好", "desc": f"毛利率 {gross_margins*100:.1f}%（高护城河）", "w": 1})

        if pe and pe < 30:
            signals.append({"factor": "动态 PE 估值", "light": "🟢 利好", "desc": f"PE={pe:.1f}（估值合理）", "w": 1})
        elif pe and pe > 50:
            signals.append({"factor": "动态 PE 估值", "light": "🔴 利空", "desc": f"PE={pe:.1f}（估值偏高）", "w": -1})

        # --- B. 期权市场情绪 ---
        pc_ratio, pc_desc = fetch_option_sentiment(symbol)
        if "看多" in pc_desc:
            signals.append({"factor": "期权异动 (P/C Ratio)", "light": "🟢 利好", "desc": f"Ratio={pc_ratio:.2f} ({pc_desc})", "w": 1})
        elif "看空" in pc_desc:
            signals.append({"factor": "期权异动 (P/C Ratio)", "light": "🔴 利空", "desc": f"Ratio={pc_ratio:.2f} ({pc_desc})", "w": -1})

        # --- C. 技术面因子 ---
        ema20 = df['Close'].ewm(span=20).mean().iloc[-1]
        ema50 = df['Close'].ewm(span=50).mean().iloc[-1]
        if price > ema20 > ema50:
            signals.append({"factor": "EMA 趋势阵列", "light": "🟢 利好", "desc": "均线多头排列", "w": 1})
        elif price < ema20 < ema50:
            signals.append({"factor": "EMA 趋势阵列", "light": "🔴 利空", "desc": "均线空头排列", "w": -1})
        else:
            signals.append({"factor": "EMA 趋势阵列", "light": "🟡 中性", "desc": "均线交织观望", "w": 0})

        ema12, ema26 = df['Close'].ewm(span=12).mean(), df['Close'].ewm(span=26).mean()
        macd, macd_sig = (ema12 - ema26).iloc[-1], (ema12 - ema26).ewm(span=9).mean().iloc[-1]
        if macd > macd_sig:
            signals.append({"factor": "MACD 动能", "light": "🟢 利好", "desc": "金叉向上", "w": 1})
        else:
            signals.append({"factor": "MACD 动能", "light": "🔴 利空", "desc": "死叉向下", "w": -1})

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi_val = int(100 - (100 / (1 + rs.iloc[-1]))) if not np.isnan(rs.iloc[-1]) else 50
        if rsi_val < 35:
            signals.append({"factor": "RSI 指标", "light": "🟢 利好", "desc": f"RSI={rsi_val}（超卖区）", "w": 1})
        elif rsi_val > 70:
            signals.append({"factor": "RSI 指标", "light": "🔴 利空", "desc": f"RSI={rsi_val}（超买区）", "w": -1})
        else:
            signals.append({"factor": "RSI 指标", "light": "🟡 中性", "desc": f"RSI={rsi_val}（正常区间）", "w": 0})

        vol_ratio = df['Volume'].iloc[-1] / df['Volume'].tail(20).mean() if df['Volume'].tail(20).mean() > 0 else 1.0
        if vol_ratio > 1.3:
            signals.append({"factor": "机构量能", "light": "🟢 利好", "desc": f"放量 {vol_ratio:.1f}x", "w": 1})
        elif vol_ratio < 0.8:
            signals.append({"factor": "机构量能", "light": "🔴 利空", "desc": f"缩量 {vol_ratio:.1f}x", "w": -1})

        # --- D. 得分与目标价 ---
        raw_sum = sum(s["w"] for s in signals)
        score = int(np.clip(50 + raw_sum * 6.0, 5, 95))

        if score >= 75: rating, cmd = "AAAA 强力关注", "🟢 信号偏多"
        elif score >= 60: rating, cmd = "AAA 偏多", "🟢 可分批关注"
        elif score >= 40: rating, cmd = "AA 中性观望", "🟡 保持观望"
        else: rating, cmd = "A 偏空避险", "🔴 建议规避/减仓"

        tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift()).abs(), (df['Low']-df['Close'].shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        atr_pct = (atr / price * 100) if price else 0.0

        direction = float(np.clip((score - 50) / 25.0, -1.0, 1.0))
        calib = get_calibration()

        if horizon == "5-10天波段":
            exp_pct = direction * (atr * 2.5 / price * 100) * HORIZON_DAMPEN[horizon] * calib["factor"]
        else:
            vol_daily = df['Close'].pct_change().dropna().tail(30).std()
            exp_pct = direction * (vol_daily * np.sqrt(63) * 100) * HORIZON_DAMPEN[horizon] * calib["factor"]

        exp_pct = float(np.clip(exp_pct, -HORIZON_CAP_PCT[horizon], HORIZON_CAP_PCT[horizon]))
        target_price = price * (1 + exp_pct / 100.0)
        stop = price - 1.5 * atr if score >= 50 else price + 1.5 * atr

        # --- E. 凯利公式 ---
        win_prob = np.clip(score / 100.0, 0.1, 0.9)
        reward = abs(target_price - price)
        risk = abs(price - stop)
        b = reward / risk if risk > 0 else 1.0
        kelly_f = (b * win_prob - (1 - win_prob)) / b
        suggested_position = float(np.clip(kelly_f * 0.5, 0.0, 0.25)) * 100

        exit_strategy = (
            f"🎯 <b>计算止盈卖出价：</b> `${target_price:.2f}` ({exp_pct:+.1f}%)\n"
            f"🛑 <b>参考止损卖出价：</b> `${stop:.2f}` —— 跌破无条件止损。"
        )

        bull_factors = [s for s in signals if s["w"] == 1]
        bear_factors = [s for s in signals if s["w"] == -1]
        if score >= 60 and bull_factors:
            reason = "入选主因：" + "、".join(f"{s['factor']}（{s['desc']}）" for s in bull_factors[:3])
        elif score <= 40 and bear_factors:
            reason = "预警主因：" + "、".join(f"{s['factor']}（{s['desc']}）" for s in bear_factors[:3])
        else:
            reason = "多空信号交织，暂无明确主导因子，建议观望。"

        return {
            "symbol": symbol, "price": price, "pct": pct, "score": score,
            "rating": rating, "cmd": cmd,
            "entry": f"${price*0.995:.2f} –${price*1.005:.2f}",
            "target": target_price, "target_pct": exp_pct, "stop": stop,
            "kelly_pos": suggested_position, "exit_strategy": exit_strategy,
            "atr_pct": atr_pct, "signals": signals, "reason": reason, "calib": calib, "vix_val": vix_val
        }
    except Exception: return None

# =============================================================================
# 5. 还原：双列信号渲染函数
# =============================================================================
def render_grouped_signals(signals):
    bulls = [s for s in signals if s["w"] == 1]
    bears = [s for s in signals if s["w"] == -1]
    neutrals = [s for s in signals if s["w"] == 0]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"<div class='signal-group-bull'><b style='color:#10B981;'>🟢 利好信号 ({len(bulls)})</b>", unsafe_allow_html=True)
        if bulls:
            for s in bulls:
                st.markdown(f"<div class='signal-row'>• <b>{s['factor']}</b> — {s['desc']}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='signal-row' style='color:#64748B;'>暂无</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.markdown(f"<div class='signal-group-bear'><b style='color:#EF4444;'>🔴 利空信号 ({len(bears)})</b>", unsafe_allow_html=True)
        if bears:
            for s in bears:
                st.markdown(f"<div class='signal-row'>• <b>{s['factor']}</b> — {s['desc']}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='signal-row' style='color:#64748B;'>暂无</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    if neutrals:
        st.markdown(f"<div class='signal-group-neutral'><b style='color:#94A3B8;'>🟡 中性信号 ({len(neutrals)})</b>", unsafe_allow_html=True)
        for s in neutrals:
            st.markdown(f"<div class='signal-row'>• <b>{s['factor']}</b> — {s['desc']}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

# =============================================================================
# 6. UI 渲染 (补全胜率/盈亏统计与排版)
# =============================================================================
TOTAL_CAPITAL = 5000.0
if not st.session_state.settled_this_session:
    settle_predictions()
    st.session_state.settled_this_session = True

trade_logs = st.session_state.realtime_trade_logs
if len(trade_logs) > 0:
    df_logs = pd.DataFrame(trade_logs)
    total_trades = len(df_logs)
    win_trades = sum(1 for s in df_logs['status'] if "✅" in str(s))
    win_rate = int((win_trades / total_trades) * 100)
    net_pnl = df_logs['pnl'].sum()
    roi = (net_pnl / TOTAL_CAPITAL) * 100
else:
    win_rate, net_pnl, roi = 0, 0.0, 0.0

vix_val, _, vix_pct = fetch_vix_data()

col_h, col_q = st.columns([3, 1])
with col_h: st.markdown("<div class='terminal-title'>⚡ ALPHA VECTOR PRO | 机构级量化终端</div>", unsafe_allow_html=True)
with col_q: st.markdown(f"<div class='api-badge'>📡 数据链路: <b>ONLINE</b></div>", unsafe_allow_html=True)

st.caption("⚠️ 本工具基于公开技术指标与量化模型生成参考信号，不构成投资建议。")
st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

# 还原：顶部完整 5 列统计卡片（恢复胜率与累计盈亏）
col_time, c_vix, c_win, c_pnl, c_cap = st.columns([1.2, 1, 1, 1, 1])
with col_time: selected_horizon = st.radio("⏱️ 策略周期:", list(HORIZON_DAYS.keys()), horizontal=True)
with c_vix: st.metric("VIX 恐慌指数", f"{vix_val:.2f}", delta=f"{vix_pct:+.2f}%", delta_color="inverse")
with c_win: st.metric("实盘策略胜率", f"{win_rate}%", delta="实盘记录")
with c_pnl: st.metric("累计实测盈亏", f"${net_pnl:+.2f}", delta=f"ROI: {roi:+.2f}%")
with c_cap: st.metric("配置总本金", f"${TOTAL_CAPITAL:,.0f}", delta="基准资金")

st.markdown("<hr style='border:none; border-top:1px solid #1E2638; margin:15px 0;'>", unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 动态因子诊断矩阵", "🎯 顶级阿尔法标的筛选 (Top 3)",
    "📜 策略实盘执行日志", "🧠 预测复盘 & 自我校准"
])

# ---- Tab 1: 单股诊断 ----
with tab1:
    target_symbol = st.text_input("请输入股票代码 (Ticker):", value="MBLY").upper().strip()
    if target_symbol:
        res = quant_evaluate_stock(target_symbol, horizon=selected_horizon)
        if res:
            st.markdown(f"#### 📌 {res['symbol']} 深度量化报告")
            col_left, col_right = st.columns([1, 1])
            with col_left:
                st.markdown("<div class='terminal-card'>", unsafe_allow_html=True)
                st.markdown(f"<div class='sub-caption'>实时标的报价</div><h2 style='margin:0; color:#FFF;'>${res['price']:.2f} "
                            f"<span style='font-size:1rem; color:{'#10B981' if res['pct']>=0 else '#EF4444'};'>({res['pct']:+.2f}%)</span></h2>", unsafe_allow_html=True)
                st.markdown("<hr style='border:none; border-top:1px solid #1E2638; margin:12px 0;'>", unsafe_allow_html=True)
                
                tag_class = "tag-bull" if res['score'] >= 60 else ("tag-neutral" if res['score'] >= 40 else "tag-bear")
                st.write(f"• **综合评级:** <span class='{tag_class}'>{res['score']}分 — {res['rating']}</span>", unsafe_allow_html=True)
                st.write(f"• **量化决策建议:** {res['cmd']}")
                st.write(f"• **建议买入关注区间:** `{res['entry']}`")

                color_p = "#10B981" if res['target_pct'] >= 0 else "#EF4444"
                st.write(f"• **{selected_horizon}预期计算目标价:** "
                         f"<b style='color:{color_p}; font-size:1.1rem;'>${res['target']:.2f}</b> "
                         f"（预期涨跌: <b style='color:{color_p};'>{res['target_pct']:+.1f}%</b>）", unsafe_allow_html=True)

                st.markdown(f"<div class='exit-box'>{res['exit_strategy']}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='kelly-box'>📐 <b>半凯利公式建议配仓比例：</b> <b style='font-size:1.1rem; color:#A7F3D0;'>{res['kelly_pos']:.1f}%</b> （建议建仓约 ${TOTAL_CAPITAL*res['kelly_pos']/100:.0f}）</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='reason-box'>💡 {res['reason']}</div>", unsafe_allow_html=True)

                if st.button("📌 记录本次预测以供复盘", key=f"log_{res['symbol']}"):
                    log_prediction(res['symbol'], selected_horizon, res['price'], res['target_pct'], res['target'])
                    st.success("已记录，可在「预测复盘」标签查看实际结果。")
                st.markdown("</div>", unsafe_allow_html=True)

            with col_right:
                st.markdown("<div class='terminal-card'>", unsafe_allow_html=True)
                st.markdown("<div class='sub-caption'>🔬 多维因子归因分析</div>", unsafe_allow_html=True)
                render_grouped_signals(res['signals'])  # 还原：双列卡片归因
                st.markdown("</div>", unsafe_allow_html=True)

# ---- Tab 2: Top 3 筛选 ----
with tab2:
    st.subheader(f"🔥 最佳阿尔法波段标的 Top 3 ({selected_horizon})")
    st.caption("筛选条件：多维评分前列，且预测盈利预期 ≥ 5.0% 的优质动能标的。")

    pool = ["NVDA", "AAPL", "TSLA", "MBLY", "AMD", "META", "MSFT", "AMZN", "GOOGL", "AVGO", "PLTR", "SMCI"]
    all_results = [r for s in pool if (r := quant_evaluate_stock(s, horizon=selected_horizon))]
    eligible = [r for r in all_results if r["target_pct"] >= 5.0]
    top3 = sorted(eligible, key=lambda x: (x["score"], x["target_pct"]), reverse=True)[:3]

    if not top3:
        st.info("⚠️ 当前市场环境下暂未筛选出预期涨幅 ≥ 5% 的高胜率标的，建议观望。")
    else:
        for i, item in enumerate(top3):
            t_class = "tag-bull" if item['score'] >= 60 else ("tag-neutral" if item['score'] >= 40 else "tag-bear")
            color_p = "#10B981" if item['target_pct'] >= 0 else "#EF4444"
            st.markdown(f"""
                <div class="terminal-card">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                        <div>
                            <span style="font-size:1.2rem; font-weight:bold; color:#FFF;">#{i+1} {item['symbol']}</span>
                            <span style="color:#64748B; font-size:0.85rem; margin-left:10px;">现价: ${item['price']:.2f}</span>
                        </div>
                        <span class="{t_class}">{item['score']}分 | 建议仓位: {item['kelly_pos']:.1f}%</span>
                    </div>
                    <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:10px; background:#0A0D14; padding:12px; border-radius:6px; text-align:center; border:1px solid #1E2638;">
                        <div><div class="sub-caption">建议买入位</div><b style="color:#FFF;">{item['entry']}</b></div>
                        <div><div class="sub-caption">计算目标价 (涨幅)</div><b style="color:{color_p}; font-size:1.05rem;">${item['target']:.2f} ({item['target_pct']:+.1f}%)</b></div>
                        <div><div class="sub-caption">参考止损离场价</div><b style="color:#EF4444;">${item['stop']:.2f}</b></div>
                    </div>
                    <div class="reason-box" style="margin-top:12px;">💡 {item['reason']}</div>
                </div>
            """, unsafe_allow_html=True)

# ---- Tab 3: 日志 ----
with tab3:
    st.subheader("📜 策略实盘执行日志")
    if len(st.session_state.realtime_trade_logs) == 0:
        st.info("📌 当前暂无历史持仓，实盘数据将从第一笔操作开始记录。")
    else:
        st.dataframe(pd.DataFrame(st.session_state.realtime_trade_logs), use_container_width=True)

# ---- Tab 4: 复盘 ----
with tab4:
    st.subheader("🧠 预测复盘 & 自我校准")
    calib = get_calibration()
    c1, c2, c3 = st.columns(3)
    c1.metric("已结算预测数", calib["n"])
    c2.metric("方向命中率", f"{calib['win_rate']:.0f}%" if calib["win_rate"] is not None else "样本不足")
    c3.metric("当前校准系数", f"{calib['factor']:.2f}")

    log_df = _load_pred_log()
    if not log_df.empty:
        st.dataframe(log_df.sort_values("logged_at", ascending=False), use_container_width=True, hide_index=True)
