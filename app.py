import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import textwrap
import os
from datetime import datetime, timedelta

# =============================================================================
# 0. 页面配置
# =============================================================================
st.set_page_config(
    page_title="Alpha Vector | 美股量化终端",
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
                "target_low", "target_high", "due_date", "status",
                "actual_price", "actual_pct", "error_pct", "direction_hit"]

HORIZON_DAYS = {"5-10天波段": 7, "3个月中线": 63}
HORIZON_CALENDAR_DAYS = {"5-10天波段": 8, "3个月中线": 95}
HORIZON_CAP_PCT = {"5-10天波段": 15.0, "3个月中线": 35.0}
DAMPEN_FACTOR = 0.55

# =============================================================================
# 1. 视觉样式（输入框打字高亮青色 #00E5FF）
# =============================================================================
st.markdown("""
<style>
    /* 全局背景与文字 */
    .stApp { 
        background-color: #0A0D14 !important; 
        color: #CBD5E1 !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
    }
    header, footer, #MainMenu { visibility: hidden; }

    /* Input 输入框：打字字体高亮青色 #00E5FF */
    div[data-baseweb="input"] {
        background-color: #131824 !important;
        border: 1px solid #3B82F6 !important;
        border-radius: 8px !important;
        color: #00E5FF !important;
    }
    input {
        color: #00E5FF !important;
        background-color: transparent !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
    }

    /* 修复 Radio 单选框文字 */
    div[data-testid="stMarkdownContainer"] p {
        color: #CBD5E1 !important;
    }
    
    /* 折叠面板 */
    div[data-testid="stExpander"] {
        background-color: #0F131D !important;
        border: 1px solid #1E2638 !important;
        border-radius: 10px !important;
    }

    /* Notification 信息提示框 */
    div[data-testid="stNotification"] {
        background-color: #131824 !important;
        border: 1px solid #2A344B !important;
        color: #CBD5E1 !important;
    }

    /* 卡片与组件容器 */
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

    /* 柔和护眼标签 */
    .tag-bull { background: rgba(16,185,129,0.12); color:#10B981; border:1px solid rgba(16,185,129,0.3);
        padding:4px 12px; border-radius:6px; font-weight:600; font-size:0.85rem; }
    .tag-bear { background: rgba(239,68,68,0.12); color:#EF4444; border:1px solid rgba(239,68,68,0.3);
        padding:4px 12px; border-radius:6px; font-weight:600; font-size:0.85rem; }
    .tag-neutral { background: rgba(245,158,11,0.12); color:#F59E0B; border:1px solid rgba(245,158,11,0.3);
        padding:4px 12px; border-radius:6px; font-weight:600; font-size:0.85rem; }

    /* 信号归因卡片 */
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

    .api-badge { font-size:0.78rem; color:#64748B; background-color:#131824; border:1px solid #1E2638;
        padding:6px 14px; border-radius:20px; float:right; }

    /* 表格背景 */
    div[data-testid="stDataFrame"] { 
        background-color:#0F131D !important; 
        border:1px solid #1E2638 !important; 
        border-radius:8px !important; 
        padding:4px !important; 
    }
    
    /* 按钮样式 */
    .stButton>button {
        background-color: #1E2638 !important;
        color: #E2E8F0 !important;
        border: 1px solid #2A344B !important;
        border-radius: 6px !important;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #2A344B !important;
        color: #FFFFFF !important;
        border-color: #3B82F6 !important;
    }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# 2. 预测记录 / 自我校准
# =============================================================================
def _load_pred_log():
    if os.path.exists(PRED_LOG_PATH):
        try:
            return pd.read_csv(PRED_LOG_PATH)
        except Exception:
            pass
    return pd.DataFrame(columns=PRED_COLUMNS)

def _save_pred_log(df):
    try:
        df.to_csv(PRED_LOG_PATH, index=False)
    except Exception:
        pass

def log_prediction(symbol, horizon, entry_price, pred_pct, target_low, target_high):
    df = _load_pred_log()
    due = (datetime.now() + timedelta(days=HORIZON_CALENDAR_DAYS[horizon])).strftime("%Y-%m-%d")
    new_row = {
        "logged_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "symbol": symbol, "horizon": horizon, "entry_price": entry_price,
        "pred_pct": pred_pct, "target_low": target_low, "target_high": target_high,
        "due_date": due, "status": "pending", "actual_price": np.nan,
        "actual_pct": np.nan, "error_pct": np.nan, "direction_hit": np.nan
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    _save_pred_log(df)

def settle_predictions():
    df = _load_pred_log()
    if df.empty:
        return
    today = datetime.now().date()
    pending = df[df["status"] == "pending"]
    for idx, row in pending.iterrows():
        try:
            due = datetime.strptime(str(row["due_date"]), "%Y-%m-%d").date()
        except Exception:
            continue
        if due > today:
            continue
        try:
            hist = yf.Ticker(row["symbol"]).history(period="5d")
            if hist.empty:
                continue
            actual_price = float(hist["Close"].iloc[-1])
            entry = float(row["entry_price"])
            actual_pct = (actual_price - entry) / entry * 100
            error = actual_pct - float(row["pred_pct"])
            direction_hit = int(np.sign(actual_pct) == np.sign(row["pred_pct"])) if row["pred_pct"] != 0 else np.nan
            df.loc[idx, ["status", "actual_price", "actual_pct", "error_pct", "direction_hit"]] = \
                ["settled", actual_price, actual_pct, error, direction_hit]
        except Exception:
            continue
    _save_pred_log(df)

def get_calibration():
    df = _load_pred_log()
    settled = df[df["status"] == "settled"].dropna(subset=["pred_pct", "actual_pct"])
    if len(settled) < 3:
        return {"factor": 1.0, "n": len(settled), "win_rate": None, "mae": None}
    ratio = (settled["actual_pct"].abs() / settled["pred_pct"].abs().replace(0, np.nan)).dropna()
    factor = float(np.clip(ratio.median(), 0.3, 1.3)) if len(ratio) > 0 else 1.0
    win_rate = float(settled["direction_hit"].mean() * 100) if "direction_hit" in settled else None
    mae = float((settled["actual_pct"] - settled["pred_pct"]).abs().mean())
    return {"factor": factor, "n": len(settled), "win_rate": win_rate, "mae": mae}

# =============================================================================
# 3. 行情与 VIX 恐慌指数获取
# =============================================================================
def fetch_quote_data(symbol):
    if FINNHUB_API_KEY and FINNHUB_API_KEY != "YOUR_FINNHUB_API_KEY_HERE":
        try:
            url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
            res = requests.get(url, timeout=3).json()
            if res and 'c' in res and res['c'] != 0:
                st.session_state.api_counter += 1
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

@st.cache_data(ttl=300)
def fetch_vix_data():
    """获取当天 CBOE VIX 恐慌指数"""
    try:
        vix = yf.Ticker("^VIX").history(period="2d")
        if not vix.empty:
            val = float(vix['Close'].iloc[-1])
            prev = float(vix['Close'].iloc[-2]) if len(vix) > 1 else val
            change = val - prev
            pct = (change / prev) * 100
            return val, change, pct
    except Exception:
        pass
    return 18.5, 0.0, 0.0  # 默认平稳状态备用值

@st.cache_data(ttl=600)
def fetch_spy_returns():
    try:
        spy = yf.Ticker("SPY").history(period="1y")
        if len(spy) > 25:
            return spy['Close'].iloc[-1] / spy['Close'].iloc[-21] - 1
    except Exception:
        pass
    return 0.0

# =============================================================================
# 4. 核心量化诊断引擎
# =============================================================================
@st.cache_data(ttl=120)
def quant_evaluate_stock(symbol, horizon="5-10天波段"):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="1y", interval="1d")
        if len(df) < 60:
            return None

        price, change, pct = fetch_quote_data(symbol)
        vix_val, vix_change, vix_pct = fetch_vix_data()
        signals = []

        # --- VIX 恐慌指数因子 ---
        if vix_val >= 30:
            signals.append({"factor": "市场恐慌指数 (VIX)", "light": "🔴 利空", "desc": f"VIX={vix_val:.1f}（市场极度恐慌）", "w": -1})
        elif vix_val >= 20:
            signals.append({"factor": "市场恐慌指数 (VIX)", "light": "🟡 中性", "desc": f"VIX={vix_val:.1f}（情绪偏谨慎）", "w": 0})
        else:
            signals.append({"factor": "市场恐慌指数 (VIX)", "light": "🟢 利好", "desc": f"VIX={vix_val:.1f}（情绪平稳）", "w": 1})

        # --- PE 估值 ---
        info = ticker.info if hasattr(ticker, 'info') else {}
        pe = info.get('forwardPE', info.get('trailingPE', None))
        pe_val = f"{pe:.1f}" if pe else "N/A"
        if pe and pe < 30:
            signals.append({"factor": "动态 PE 估值分位", "light": "🟢 利好", "desc": f"{pe_val}（估值合理）", "w": 1})
        elif pe and pe < 50:
            signals.append({"factor": "动态 PE 估值分位", "light": "🟡 中性", "desc": f"{pe_val}（估值中等）", "w": 0})
        elif pe:
            signals.append({"factor": "动态 PE 估值分位", "light": "🔴 利空", "desc": f"{pe_val}（估值偏高）", "w": -1})
        else:
            signals.append({"factor": "动态 PE 估值分位", "light": "🟡 中性", "desc": "无盈利/数据缺失", "w": 0})

        # --- EMA 趋势排列 ---
        ema20 = df['Close'].ewm(span=20).mean().iloc[-1]
        ema50 = df['Close'].ewm(span=50).mean().iloc[-1]
        if price > ema20 > ema50:
            signals.append({"factor": "EMA 趋势阵列", "light": "🟢 利好", "desc": "均线多头排列", "w": 1})
        elif price < ema20 < ema50:
            signals.append({"factor": "EMA 趋势阵列", "light": "🔴 利空", "desc": "均线空头排列", "w": -1})
        else:
            signals.append({"factor": "EMA 趋势阵列", "light": "🟡 中性", "desc": "均线交织，趋势不明", "w": 0})

        # --- MACD ---
        ema12 = df['Close'].ewm(span=12).mean()
        ema26 = df['Close'].ewm(span=26).mean()
        macd = (ema12 - ema26).iloc[-1]
        macd_sig = (ema12 - ema26).ewm(span=9).mean().iloc[-1]
        if macd > macd_sig:
            signals.append({"factor": "MACD 动能交叉", "light": "🟢 利好", "desc": "MACD 金叉向上", "w": 1})
        else:
            signals.append({"factor": "MACD 动能交叉", "light": "🔴 利空", "desc": "MACD 死叉向下", "w": -1})

        # --- RSI ---
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi_val = int(100 - (100 / (1 + rs.iloc[-1]))) if not np.isnan(rs.iloc[-1]) else 50
        if rsi_val > 70:
            signals.append({"factor": "RSI 相对强弱", "light": "🔴 利空", "desc": f"RSI={rsi_val}（超买，回调风险）", "w": -1})
        elif rsi_val < 30:
            signals.append({"factor": "RSI 相对强弱", "light": "🟢 利好", "desc": f"RSI={rsi_val}（超卖，反弹机会）", "w": 1})
        else:
            signals.append({"factor": "RSI 相对强弱", "light": "🟡 中性", "desc": f"RSI={rsi_val}（区间震荡）", "w": 0})

        # --- 布林带位置 ---
        sma20 = df['Close'].rolling(20).mean().iloc[-1]
        std20 = df['Close'].rolling(20).std().iloc[-1]
        upper, lower = sma20 + 2 * std20, sma20 - 2 * std20
        bb_pos = (price - lower) / (upper - lower) if (upper - lower) != 0 else 0.5
        if bb_pos > 0.85:
            signals.append({"factor": "布林带位置", "light": "🔴 利空", "desc": "逼近上轨，短期超涨", "w": -1})
        elif bb_pos < 0.15:
            signals.append({"factor": "布林带位置", "light": "🟢 利好", "desc": "逼近下轨，超跌反弹可能", "w": 1})
        else:
            signals.append({"factor": "布林带位置", "light": "🟡 中性", "desc": "位于轨道中段", "w": 0})

        # --- 成交量放量倍数 ---
        vol_mean = df['Volume'].tail(20).mean()
        vol_ratio = df['Volume'].iloc[-1] / vol_mean if vol_mean > 0 else 1.0
        if vol_ratio > 1.3:
            signals.append({"factor": "机构量能放大倍数", "light": "🟢 利好", "desc": f"放量 {vol_ratio:.1f}x", "w": 1})
        elif vol_ratio > 0.8:
            signals.append({"factor": "机构量能放大倍数", "light": "🟡 中性", "desc": f"量能正常 {vol_ratio:.1f}x", "w": 0})
        else:
            signals.append({"factor": "机构量能放大倍数", "light": "🔴 利空", "desc": f"缩量 {vol_ratio:.1f}x", "w": -1})

        # --- 52 周区间位置 ---
        hi52, lo52 = df['High'].max(), df['Low'].min()
        pos52 = (price - lo52) / (hi52 - lo52) if (hi52 - lo52) != 0 else 0.5
        if pos52 > 0.9:
            signals.append({"factor": "52周区间位置", "light": "🟢 利好", "desc": "逼近52周新高，动能强", "w": 1})
        elif pos52 < 0.15:
            signals.append({"factor": "52周区间位置", "light": "🔴 利空", "desc": "逼近52周新低，弱势", "w": -1})
        else:
            signals.append({"factor": "52周区间位置", "light": "🟡 中性", "desc": f"处于区间 {pos52*100:.0f}% 位置", "w": 0})

        # --- KD 随机指标 ---
        low14 = df['Low'].rolling(14).min()
        high14 = df['High'].rolling(14).max()
        k_line = 100 * (df['Close'] - low14) / (high14 - low14)
        d_line = k_line.rolling(3).mean()
        k_val, d_val = k_line.iloc[-1], d_line.iloc[-1]
        if k_val > d_val and k_val < 80:
            signals.append({"factor": "KD 随机指标", "light": "🟢 利好", "desc": "K上穿D，未超买", "w": 1})
        elif k_val < d_val and k_val > 20:
            signals.append({"factor": "KD 随机指标", "light": "🔴 利空", "desc": "K下穿D，动能转弱", "w": -1})
        else:
            signals.append({"factor": "KD 随机指标", "light": "🟡 中性", "desc": f"K={k_val:.0f} D={d_val:.0f}", "w": 0})

        # --- 相对大盘强弱 ---
        spy_ret = fetch_spy_returns()
        stock_ret = (df['Close'].iloc[-1] / df['Close'].iloc[-21] - 1) if len(df) > 21 else 0.0
        rel_strength = stock_ret - spy_ret
        if rel_strength > 0.03:
            signals.append({"factor": "相对大盘强弱", "light": "🟢 利好", "desc": f"跑赢SPY {rel_strength*100:+.1f}%", "w": 1})
        elif rel_strength < -0.03:
            signals.append({"factor": "相对大盘强弱", "light": "🔴 利空", "desc": f"跑输SPY {rel_strength*100:+.1f}%", "w": -1})
        else:
            signals.append({"factor": "相对大盘强弱", "light": "🟡 中性", "desc": "与大盘同步", "w": 0})

        # --- ATR 波动率 ---
        tr = pd.concat([
            df['High'] - df['Low'],
            (df['High'] - df['Close'].shift()).abs(),
            (df['Low'] - df['Close'].shift()).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        atr_pct = (atr / price * 100) if price else 0.0
        high_vol_flag = atr_pct > 5.0 or vix_val >= 25.0

        # --- 综合评分 ---
        raw_sum = sum(s["w"] for s in signals)
        score = int(np.clip(50 + raw_sum * 5.5, 5, 95))

        if score >= 80:
            rating, cmd = "AAAA 强力关注", "🟢 信号偏多"
        elif score >= 65:
            rating, cmd = "AAA 偏多", "🟢 可分批关注"
        elif score >= 40:
            rating, cmd = "AA 中性观望", "🟡 保持观望"
        else:
            rating, cmd = "A 偏空避险", "🔴 建议规避/减仓"

        # --- 预期收益率 ---
        horizon_days = HORIZON_DAYS[horizon]
        cap = HORIZON_CAP_PCT[horizon]
        vol_daily = df['Close'].pct_change().dropna().tail(30).std()
        if np.isnan(vol_daily):
            vol_daily = 0.02
            
        # VIX 影响：VIX 越高，预测的波动容忍区间拉得更大
        vix_multiplier = 1.0 + max(0, (vix_val - 20) / 40.0)
        
        direction = float(np.clip((score - 50) / 50, -1, 1))
        calib = get_calibration()
        horizon_vol_pct = vol_daily * np.sqrt(horizon_days) * 100 * vix_multiplier
        exp_pct = direction * horizon_vol_pct * DAMPEN_FACTOR * calib["factor"]
        exp_pct = float(np.clip(exp_pct, -cap, cap))
        
        band = min(horizon_vol_pct * 0.5, cap)
        target_low_pct = float(np.clip(exp_pct - band, -cap * 1.3, cap * 1.3))
        target_high_pct = float(np.clip(exp_pct + band, -cap * 1.3, cap * 1.3))
        target_price = price * (1 + exp_pct / 100.0)
        target_low = price * (1 + target_low_pct / 100.0)
        target_high = price * (1 + target_high_pct / 100.0)

        stop = price - 1.5 * atr if score >= 50 else price + 1.5 * atr

        bull_factors = [s for s in signals if s["w"] == 1]
        bear_factors = [s for s in signals if s["w"] == -1]
        if score >= 65 and bull_factors:
            top = bull_factors[:3]
            reason = "入选主因：" + "、".join(f"{s['factor']}（{s['desc']}）" for s in top)
        elif score <= 40 and bear_factors:
            top = bear_factors[:3]
            reason = "预警主因：" + "、".join(f"{s['factor']}（{s['desc']}）" for s in top)
        else:
            reason = "多空信号交织，暂无明确的主导因子，建议观望。"

        return {
            "symbol": symbol, "price": price, "pct": pct, "score": score,
            "rating": rating, "cmd": cmd,
            "entry": f"${price*0.996:.2f} –${price*1.004:.2f}",
            "target": target_price, "target_pct": exp_pct,
            "target_low": target_low, "target_high": target_high,
            "target_low_pct": target_low_pct, "target_high_pct": target_high_pct,
            "stop": stop, "atr_pct": atr_pct, "high_vol_flag": high_vol_flag,
            "signals": signals, "reason": reason, "calib": calib, "vix_val": vix_val
        }
    except Exception:
        return None

# =============================================================================
# 5. 顶部统计
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

vix_val, vix_change, vix_pct = fetch_vix_data()

# =============================================================================
# 6. 界面渲染
# =============================================================================
col_h, col_q = st.columns([3, 1])
with col_h:
    st.markdown("<div class='terminal-title'>⚡ ALPHA VECTOR | 美股量化诊断终端</div>", unsafe_allow_html=True)
with col_q:
    st.markdown(f"<div class='api-badge'>📡 数据链路调用: <b>{st.session_state.api_counter} / 60</b></div>", unsafe_allow_html=True)

st.caption("⚠️ 本工具基于公开技术指标生成的量化参考信号，仅供研究学习使用，不构成投资建议；预测区间已做统计学合理化处理，仍可能出现较大偏差。")
st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

col_time, c_vix, c_win, c_pnl, c_cap = st.columns([1.2, 1, 1, 1, 1])
with col_time:
    selected_horizon = st.radio("⏱️ 策略执行时间周期:", list(HORIZON_DAYS.keys()), horizontal=True)
with c_vix:
    vix_color = "#EF4444" if vix_val >= 25 else ("#F59E0B" if vix_val >= 20 else "#10B981")
    st.metric("VIX 恐慌指数", f"{vix_val:.2f}", delta=f"{vix_pct:+.2f}%", delta_color="inverse")
with c_win:
    st.metric("实盘策略胜率", f"{win_rate}%", delta="从零计算")
with c_pnl:
    st.metric("累计实测盈亏", f"${net_pnl:+.2f}", delta=f"账户 ROI: {roi:+.2f}%")
with c_cap:
    st.metric("配置总本金", f"${TOTAL_CAPITAL:,.0f}", delta="基准仓位")

st.markdown("<hr style='border:none; border-top:1px solid #1E2638; margin:15px 0;'>", unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 动态因子诊断矩阵", "🎯 顶级阿尔法标的筛选 (Top 3)",
    "📜 策略实盘执行日志", "🧠 预测复盘 & 自我校准"
])

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

# ---- Tab 1: 单股诊断 ----
with tab1:
    target_symbol = st.text_input("请输入股票代码 (Ticker):", value="MBLY").upper().strip()

    if target_symbol:
        res = quant_evaluate_stock(target_symbol, horizon=selected_horizon)
        if res:
            st.markdown(f"#### 📌 {res['symbol']} 深度量化报告")

            if res["vix_val"] >= 25:
                st.markdown(f"<div class='risk-banner'>🚨 <b>市场风控预警：</b>当前大盘 VIX 恐慌指数升至 <b>{res['vix_val']:.1f}</b>，市场情绪剧烈波动！预测区间已自动调宽，请降低仓位谨慎操作。</div>", unsafe_allow_html=True)
            elif res["high_vol_flag"]:
                st.markdown(f"<div class='risk-banner'>⚠️ 该标的近期波动率偏高（ATR ≈ {res['atr_pct']:.1f}% / 日），预测区间已相应放宽，请注意仓位控制。</div>", unsafe_allow_html=True)

            col_left, col_right = st.columns([1, 1])
            with col_left:
                st.markdown("<div class='terminal-card'>", unsafe_allow_html=True)
                st.markdown(f"<div class='sub-caption'>实时标的报价</div><h2 style='margin:0; color:#FFF;'>${res['price']:.2f} "
                            f"<span style='font-size:1rem; color:{'#10B981' if res['pct']>=0 else '#EF4444'};'>({res['pct']:+.2f}%)</span></h2>",
                            unsafe_allow_html=True)
                st.markdown("<hr style='border:none; border-top:1px solid #1E2638; margin:12px 0;'>", unsafe_allow_html=True)

                tag_class = "tag-bull" if res['score'] >= 65 else ("tag-neutral" if res['score'] >= 40 else "tag-bear")
                st.write(f"• **综合评级:** <span class='{tag_class}'>{res['score']}分 — {res['rating']}</span>", unsafe_allow_html=True)
                st.write(f"• **量化决策建议:** {res['cmd']}")
                st.write(f"• **建议关注区间:** `{res['entry']}`")

                color_p = "#10B981" if res['target_pct'] >= 0 else "#EF4444"
                st.write(f"• **{selected_horizon}预期区间:** "
                         f"<b style='color:{color_p};'>{res['target_low_pct']:+.1f}% ~ {res['target_high_pct']:+.1f}%</b> "
                         f"（中枢 ${res['target']:.2f}，区间 ${res['target_low']:.2f} ~${res['target_high']:.2f}）",
                         unsafe_allow_html=True)
                st.write(f"• **参考止损位（1.5×ATR）:** `${res['stop']:.2f}`")

                st.markdown(f"<div class='reason-box'>💡 {res['reason']}</div>", unsafe_allow_html=True)

                if st.button("📌 记录本次预测以供复盘", key=f"log_{res['symbol']}"):
                    log_prediction(res['symbol'], selected_horizon, res['price'], res['target_pct'],
                                   res['target_low_pct'], res['target_high_pct'])
                    st.success("已记录，到期后可在「预测复盘」标签查看实际结果。")

                st.markdown("</div>", unsafe_allow_html=True)

            with col_right:
                st.markdown("<div class='terminal-card'>", unsafe_allow_html=True)
                st.markdown("<div class='sub-caption'>🔬 多维因子归因分析（已按利好/利空分组）</div>", unsafe_allow_html=True)
                render_grouped_signals(res['signals'])
                st.markdown("</div>", unsafe_allow_html=True)

            with st.expander("📖 评分与预测方法说明"):
                st.markdown(textwrap.dedent(f"""
                - **评分**：{len(res['signals'])} 个技术/估值/VIX恐慌指数因子等权打分，每个利好 +5.5 分、利空 -5.5 分，以 50 分为中枢，5–95 分封顶。
                - **预期收益率**：不是简单外推，而是「方向强度 × 历史波动率按 √时间 缩放 × VIX恐慌调节系数 × 0.55 折算 × 历史校准系数」，
                  并硬性封顶在 ±{HORIZON_CAP_PCT[selected_horizon]:.0f}%，避免出现脱离实际的极端数字。
                - **历史校准系数**：当前为 **{res['calib']['factor']:.2f}**（基于 {res['calib']['n']} 条已到期的历史预测计算，
                  样本不足 3 条时默认 1.0）。如果过去的预测持续偏乐观，这个系数会自动变小，让未来的预测更保守。
                """))
        else:
            st.warning("未能获取该代码的有效数据，请检查代码是否正确或稍后重试。")

# ---- Tab 2: Top 3 ----
with tab2:
    st.subheader(f"🔥 今日阿尔法关注榜单 ({selected_horizon})")
    st.caption("基于同一套量化因子对股票池打分，列出综合评分最高的 3 只，并给出入选理由。")

    pool = ["NVDA", "AAPL", "TSLA", "MBLY", "AMD", "META", "MSFT", "AMZN"]
    results = [r for s in pool if (r := quant_evaluate_stock(s, horizon=selected_horizon))]
    top3 = sorted(results, key=lambda x: x["score"], reverse=True)[:3]

    for i, item in enumerate(top3):
        t_class = "tag-bull" if item['score'] >= 65 else ("tag-neutral" if item['score'] >= 40 else "tag-bear")
        color_p = "#10B981" if item['target_pct'] >= 0 else "#EF4444"
        card_html = textwrap.dedent(f"""
            <div class="terminal-card">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                    <div>
                        <span style="font-size:1.2rem; font-weight:bold; color:#FFF;">#{i+1} {item['symbol']}</span>
                        <span style="color:#64748B; font-size:0.85rem; margin-left:10px;">现价: ${item['price']:.2f}</span>
                    </div>
                    <span class="{t_class}">{item['score']}分 | {item['rating']}</span>
                </div>
                <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:10px; background:#0A0D14; padding:12px; border-radius:6px; text-align:center; border:1px solid #1E2638;">
                    <div><div class="sub-caption">关注区间</div><b style="color:#FFF;">{item['entry']}</b></div>
                    <div><div class="sub-caption">{selected_horizon}预期区间</div><b style="color:{color_p};">{item['target_low_pct']:+.1f}% ~ {item['target_high_pct']:+.1f}%</b></div>
                    <div><div class="sub-caption">参考止损</div><b style="color:#EF4444;">${item['stop']:.2f}</b></div>
                </div>
                <div class="reason-box" style="margin-top:12px;">💡 {item['reason']}</div>
            </div>
        """).strip()
        st.markdown(card_html, unsafe_allow_html=True)

# ---- Tab 3: 实盘日志 ----
with tab3:
    st.subheader("📜 策略实盘执行日志")
    if len(st.session_state.realtime_trade_logs) == 0:
        st.info("📌 当前暂无历史持仓，实盘数据将从你的第一笔操作开始记录。")
    else:
        st.dataframe(pd.DataFrame(st.session_state.realtime_trade_logs), use_container_width=True)

# ---- Tab 4: 预测复盘 & 自我校准 ----
with tab4:
    st.subheader("🧠 预测复盘 & 自我校准")
    st.caption("说明：这不是黑箱式的『自动学习』，而是一个透明的反馈环 —— 系统记录每次预测，到期后自动对比真实价格，"
               "用历史误差算出一个校准系数，用于给未来的预测幅度降温或修正。")

    calib = get_calibration()
    c1, c2, c3 = st.columns(3)
    c1.metric("已结算预测数", calib["n"])
    c2.metric("方向命中率", f"{calib['win_rate']:.0f}%" if calib["win_rate"] is not None else "样本不足")
    c3.metric("当前校准系数", f"{calib['factor']:.2f}")

    log_df = _load_pred_log()
    if log_df.empty:
        st.info("暂无历史预测记录。前往「动态因子诊断矩阵」标签，点击『记录本次预测』即可开始积累复盘数据。")
    else:
        show_df = log_df.copy()
        for c in ["entry_price", "pred_pct", "target_low", "target_high", "actual_price", "actual_pct", "error_pct"]:
            if c in show_df.columns:
                show_df[c] = pd.to_numeric(show_df[c], errors="coerce").round(2)
        st.dataframe(show_df.sort_values("logged_at", ascending=False), use_container_width=True, hide_index=True)
