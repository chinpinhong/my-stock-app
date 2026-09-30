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

st.markdown("""
<style>
    .stApp { background-color: #0A0D14; color: #E2E8F0;
             font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    header, footer, #MainMenu { visibility: hidden; }
    .terminal-card { background: linear-gradient(135deg, #131824, #0F131D);
        border: 1px solid #1E2638; border-radius: 12px; padding: 20px;
        margin-bottom: 16px; box-shadow: 0 4px 18px rgba(0,0,0,0.35); }
    .terminal-title { font-size: 1.5rem; font-weight: 700; color: #F8FAFC; letter-spacing: -0.3px; }
    .sub-caption { color: #64748B; font-size: 0.75rem; text-transform: uppercase;
        font-weight: 600; letter-spacing: 0.8px; margin-bottom: 8px; }
    .tag-bull { background: rgba(16,185,129,0.12); color:#10B981; border:1px solid rgba(16,185,129,0.3);
        padding:4px 12px; border-radius:6px; font-weight:600; font-size:0.85rem; }
    .tag-bear { background: rgba(239,68,68,0.12); color:#EF4444; border:1px solid rgba(239,68,68,0.3);
        padding:4px 12px; border-radius:6px; font-weight:600; font-size:0.85rem; }
    .tag-neutral { background: rgba(245,158,11,0.12); color:#F59E0B; border:1px solid rgba(245,158,11,0.3);
        padding:4px 12px; border-radius:6px; font-weight:600; font-size:0.85rem; }
    .signal-group-bull { background: rgba(16,185,129,0.06); border:1px solid rgba(16,185,129,0.25);
        border-radius:10px; padding:14px; margin-bottom:10px; }
    .signal-group-bear { background: rgba(239,68,68,0.06); border:1px solid rgba(239,68,68,0.25);
        border-radius:10px; padding:14px; margin-bottom:10px; }
    .signal-group-neutral { background: rgba(148,163,184,0.06); border:1px solid rgba(148,163,184,0.2);
        border-radius:10px; padding:14px; margin-bottom:10px; }
    .signal-row { font-size:0.9rem; padding:4px 0; border-bottom:1px dashed rgba(148,163,184,0.12); }
    .signal-row:last-child { border-bottom:none; }
    .risk-banner { background: rgba(245,158,11,0.1); border:1px solid rgba(245,158,11,0.35);
        border-radius:8px; padding:10px 14px; font-size:0.85rem; color:#FBBF24; margin-bottom:10px; }
    .reason-box { background: rgba(59,130,246,0.08); border:1px solid rgba(59,130,246,0.3);
        border-radius:8px; padding:12px 14px; font-size:0.88rem; color:#BFDBFE; margin-top:10px; }
    .api-badge { font-size:0.78rem; color:#64748B; background-color:#131824; border:1px solid #1E2638;
        padding:6px 14px; border-radius:20px; float:right; }
    div[data-testid="stDataFrame"] { background-color:#0F131D; border:1px solid #1E2638; border-radius:8px; padding:4px; }
</style>
""", unsafe_allow_html=True)

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

def auto_log_if_new_today(symbol, horizon, entry_price, pred_pct, target_low, target_high):
    """给『今日精选』用：同一只股票、同一周期，今天已经自动记过就跳过，避免每次刷新都重复写入。
    返回 True 表示这次确实新写了一条。"""
    df = _load_pred_log()
    today_str = datetime.now().strftime("%Y-%m-%d")
    if not df.empty:
        already = (
            (df["symbol"] == symbol) & (df["horizon"] == horizon) &
            (df["logged_at"].astype(str).str.startswith(today_str))
        ).any()
        if already:
            return False
    log_prediction(symbol, horizon, entry_price, pred_pct, target_low, target_high)
    return True

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

@st.cache_data(ttl=600)
def fetch_spy_returns():
    try:
        spy = yf.Ticker("SPY").history(period="1y")
        if len(spy) > 25:
            return spy['Close'].iloc[-1] / spy['Close'].iloc[-21] - 1
    except Exception:
        pass
    return 0.0

def _vectorized_score_series(df, spy_close):
    """跟 quant_evaluate_stock 同一套打分规则的『整段历史』向量化版本（不含 PE，历史上没有逐日估值数据）。
    只用来给『历史上出现过同样分数时，未来实际涨跌多少』这个统计做数据源，不影响当天显示的分数。"""
    close, high, low, volume = df['Close'], df['High'], df['Low'], df['Volume']

    ema20, ema50 = close.ewm(span=20).mean(), close.ewm(span=50).mean()
    ema_sig = np.where((close > ema20) & (ema20 > ema50), 1, np.where((close < ema20) & (ema20 < ema50), -1, 0))

    ema12, ema26 = close.ewm(span=12).mean(), close.ewm(span=26).mean()
    macd = ema12 - ema26
    macd_sig = np.where(macd > macd.ewm(span=9).mean(), 1, -1)

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - 100 / (1 + gain / loss)
    rsi_sig = np.where(rsi > 70, -1, np.where(rsi < 30, 1, 0))

    sma20, std20 = close.rolling(20).mean(), close.rolling(20).std()
    upper, lower = sma20 + 2 * std20, sma20 - 2 * std20
    bb_pos = (close - lower) / (upper - lower)
    bb_sig = np.where(bb_pos > 0.85, -1, np.where(bb_pos < 0.15, 1, 0))

    vol_ratio = volume / volume.rolling(20).mean()
    vol_sig = np.where(vol_ratio > 1.3, 1, np.where(vol_ratio > 0.8, 0, -1))

    hi52 = high.rolling(252, min_periods=60).max()
    lo52 = low.rolling(252, min_periods=60).min()
    pos52 = (close - lo52) / (hi52 - lo52)
    pos52_sig = np.where(pos52 > 0.9, 1, np.where(pos52 < 0.15, -1, 0))

    low14, high14 = low.rolling(14).min(), high.rolling(14).max()
    k_line = 100 * (close - low14) / (high14 - low14)
    d_line = k_line.rolling(3).mean()
    kd_sig = np.where((k_line > d_line) & (k_line < 80), 1, np.where((k_line < d_line) & (k_line > 20), -1, 0))

    spy_aligned = spy_close.reindex(close.index).ffill()
    rel = close.pct_change(20) - spy_aligned.pct_change(20)
    rel_sig = np.where(rel > 0.03, 1, np.where(rel < -0.03, -1, 0))

    raw_sum = ema_sig + macd_sig + rsi_sig + bb_sig + vol_sig + pos52_sig + kd_sig + rel_sig
    return pd.Series(np.clip(50 + raw_sum * 6, 5, 95), index=close.index)


@st.cache_data(ttl=3600)
def get_historical_edge(symbol, horizon):
    """这只股票历史上，出现过跟『今天』差不多分数的时候，未来实际平均涨跌多少（真实数据，不是公式猜的）。
    样本不够（少于 20 次）就返回 None，调用方会自动退回用公式估算，不瞎编。"""
    try:
        df3 = yf.Ticker(symbol).history(period="3y")
        if len(df3) < 300:
            return None, 0
        spy3 = yf.Ticker("SPY").history(period="3y")["Close"] if symbol != "SPY" else df3["Close"]
        score_hist = _vectorized_score_series(df3, spy3)
        horizon_days = HORIZON_DAYS[horizon]
        fwd = df3["Close"].pct_change(horizon_days).shift(-horizon_days)
        cur_score = float(score_hist.iloc[-1])
        mask = (score_hist - cur_score).abs() <= 8  # 分数相近（同一档附近）算作『类似情形』
        sample = fwd[mask].dropna()
        if len(sample) < 20:
            return None, len(sample)
        return float(sample.mean() * 100), len(sample)
    except Exception:
        return None, 0


@st.cache_data(ttl=120)
def quant_evaluate_stock(symbol, horizon="5-10天波段"):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="1y", interval="1d")
        if len(df) < 60:
            return None

        price, change, pct = fetch_quote_data(symbol)
        signals = []

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

        ema20 = df['Close'].ewm(span=20).mean().iloc[-1]
        ema50 = df['Close'].ewm(span=50).mean().iloc[-1]
        if price > ema20 > ema50:
            signals.append({"factor": "EMA 趋势阵列", "light": "🟢 利好", "desc": "均线多头排列", "w": 1})
        elif price < ema20 < ema50:
            signals.append({"factor": "EMA 趋势阵列", "light": "🔴 利空", "desc": "均线空头排列", "w": -1})
        else:
            signals.append({"factor": "EMA 趋势阵列", "light": "🟡 中性", "desc": "均线交织，趋势不明", "w": 0})

        ema12 = df['Close'].ewm(span=12).mean()
        ema26 = df['Close'].ewm(span=26).mean()
        macd = (ema12 - ema26).iloc[-1]
        macd_sig = (ema12 - ema26).ewm(span=9).mean().iloc[-1]
        if macd > macd_sig:
            signals.append({"factor": "MACD 动能交叉", "light": "🟢 利好", "desc": "MACD 金叉向上", "w": 1})
        else:
            signals.append({"factor": "MACD 动能交叉", "light": "🔴 利空", "desc": "MACD 死叉向下", "w": -1})

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

        vol_mean = df['Volume'].tail(20).mean()
        vol_ratio = df['Volume'].iloc[-1] / vol_mean if vol_mean > 0 else 1.0
        if vol_ratio > 1.3:
            signals.append({"factor": "机构量能放大倍数", "light": "🟢 利好", "desc": f"放量 {vol_ratio:.1f}x", "w": 1})
        elif vol_ratio > 0.8:
            signals.append({"factor": "机构量能放大倍数", "light": "🟡 中性", "desc": f"量能正常 {vol_ratio:.1f}x", "w": 0})
        else:
            signals.append({"factor": "机构量能放大倍数", "light": "🔴 利空", "desc": f"缩量 {vol_ratio:.1f}x", "w": -1})

        hi52, lo52 = df['High'].max(), df['Low'].min()
        pos52 = (price - lo52) / (hi52 - lo52) if (hi52 - lo52) != 0 else 0.5
        if pos52 > 0.9:
            signals.append({"factor": "52周区间位置", "light": "🟢 利好", "desc": "逼近52周新高，动能强", "w": 1})
        elif pos52 < 0.15:
            signals.append({"factor": "52周区间位置", "light": "🔴 利空", "desc": "逼近52周新低，弱势", "w": -1})
        else:
            signals.append({"factor": "52周区间位置", "light": "🟡 中性", "desc": f"处于区间 {pos52*100:.0f}% 位置", "w": 0})

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

        spy_ret = fetch_spy_returns()
        stock_ret = (df['Close'].iloc[-1] / df['Close'].iloc[-21] - 1) if len(df) > 21 else 0.0
        rel_strength = stock_ret - spy_ret
        if rel_strength > 0.03:
            signals.append({"factor": "相对大盘强弱", "light": "🟢 利好", "desc": f"跑赢SPY {rel_strength*100:+.1f}%", "w": 1})
        elif rel_strength < -0.03:
            signals.append({"factor": "相对大盘强弱", "light": "🔴 利空", "desc": f"跑输SPY {rel_strength*100:+.1f}%", "w": -1})
        else:
            signals.append({"factor": "相对大盘强弱", "light": "🟡 中性", "desc": "与大盘同步", "w": 0})

        tr = pd.concat([
            df['High'] - df['Low'],
            (df['High'] - df['Close'].shift()).abs(),
            (df['Low'] - df['Close'].shift()).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        atr_pct = (atr / price * 100) if price else 0.0
        high_vol_flag = atr_pct > 5.0

        raw_sum = sum(s["w"] for s in signals)
        score = int(np.clip(50 + raw_sum * 6, 5, 95))

        if score >= 80:
            rating, cmd = "AAAA 强力关注", "🟢 信号偏多"
        elif score >= 65:
            rating, cmd = "AAA 偏多", "🟢 可分批关注"
        elif score >= 40:
            rating, cmd = "AA 中性观望", "🟡 保持观望"
        else:
            rating, cmd = "A 偏空避险", "🔴 建议规避/减仓"

        horizon_days = HORIZON_DAYS[horizon]
        cap = HORIZON_CAP_PCT[horizon]
        vol_daily = df['Close'].pct_change().dropna().tail(30).std()
        if np.isnan(vol_daily):
            vol_daily = 0.02
        direction = float(np.clip((score - 50) / 50, -1, 1))
        calib = get_calibration()
        horizon_vol_pct = vol_daily * np.sqrt(horizon_days) * 100
        formula_pct = direction * horizon_vol_pct * DAMPEN_FACTOR

        # 用这只股票历史上『同样分数出现时，未来实际涨跌多少』去修正公式猜的数字，而不是纯拍脑袋。
        # 样本太少（这只股票很少出现类似分数）就只用公式，不硬凑。
        edge_pct, edge_n = get_historical_edge(symbol, horizon)
        if edge_pct is not None:
            edge_weight = float(np.clip(edge_n / 100, 0.3, 0.7))  # 历史样本越多，越信历史，最高信 70%
            blended_pct = (1 - edge_weight) * formula_pct + edge_weight * edge_pct
            edge_note = f"（融合了 {edge_n} 次历史同类分数的真实表现，权重 {edge_weight*100:.0f}%）"
        else:
            blended_pct = formula_pct
            edge_note = "（历史上出现同类分数的次数太少，仅用公式估算，未做历史修正）"

        exp_pct = float(np.clip(blended_pct * calib["factor"], -cap, cap))
        # 区间宽度跟着信号强弱走：信号越极端（很看多/很看空），区间越集中在那一侧；
        # 信号越模糊（接近中性），区间才更宽——避免一个明显看跌的中枢被固定宽度的区间盖成正数。
        band_frac = 0.6 - 0.35 * abs(direction)
        band = min(horizon_vol_pct * band_frac, cap)
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
            "entry": f"${price*0.996:.2f} – ${price*1.004:.2f}",
            "target": target_price, "target_pct": exp_pct,
            "target_low": target_low, "target_high": target_high,
            "target_low_pct": target_low_pct, "target_high_pct": target_high_pct,
            "stop": stop, "atr_pct": atr_pct, "high_vol_flag": high_vol_flag,
            "signals": signals, "reason": reason, "calib": calib,
            "edge_note": edge_note, "edge_n": edge_n,
        }
    except Exception:
        return None

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

col_h, col_q = st.columns([3, 1])
with col_h:
    st.markdown("<div class='terminal-title'>⚡ ALPHA VECTOR | 美股量化诊断终端</div>", unsafe_allow_html=True)
with col_q:
    st.markdown(f"<div class='api-badge'>📡 数据链路调用: <b>{st.session_state.api_counter} / 60</b></div>", unsafe_allow_html=True)

st.caption("⚠️ 本工具基于公开技术指标生成的量化参考信号，仅供研究学习使用，不构成投资建议；预测区间已做统计学合理化处理，仍可能出现较大偏差。")
st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

col_time, c_win, c_pnl, c_cap = st.columns([1.3, 1, 1, 1])
with col_time:
    selected_horizon = st.radio("⏱️ 策略执行时间周期:", list(HORIZON_DAYS.keys()), horizontal=True)
with c_win:
    st.metric("实盘策略胜率", f"{win_rate}%", delta="从零计算")
with c_pnl:
    st.metric("累计实测盈亏", f"${net_pnl:+.2f}", delta=f"账户 ROI: {roi:+.2f}%")
with c_cap:
    st.metric("配置总本金", f"${TOTAL_CAPITAL:,.0f}", delta="基准仓位")

st.markdown("<hr style='border:none; border-top:1px solid #1E2638; margin:15px 0;'>", unsafe_allow_html=True)

tab0, tab1, tab3, tab4 = st.tabs([
    "⭐ 今日精选（自动）", "📊 动态因子诊断矩阵",
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

SCAN_POOL = [
    # 科技
    "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "AVGO", "ORCL", "CRM", "ADBE",
    "AMD", "QCOM", "INTC", "CSCO", "IBM", "NOW", "INTU", "TXN", "MU", "PANW", "TSLA",
    # 通信/媒体
    "NFLX", "DIS", "CMCSA", "TMUS", "VZ", "T",
    # 金融
    "JPM", "BAC", "WFC", "GS", "MS", "V", "MA", "AXP", "BLK", "SCHW",
    # 医疗
    "UNH", "JNJ", "LLY", "PFE", "ABBV", "MRK", "TMO", "ABT", "DHR", "ISRG",
    # 消费
    "WMT", "HD", "COST", "PG", "KO", "PEP", "MCD", "NKE", "SBUX", "TGT", "LOW",
    # 能源
    "XOM", "CVX", "COP", "SLB",
    # 工业
    "BA", "CAT", "GE", "HON", "UPS", "RTX", "LMT",
    # 公用事业 / 房地产 / 材料
    "NEE", "DUK", "PLD", "AMT", "LIN",
    # 大盘 / 行业 ETF
    "SPY", "QQQ", "DIA", "IWM",
]
MIN_PICKS, MAX_PICKS = 3, 5

@st.cache_data(ttl=300)
def scan_today_picks(pool, horizon):
    """扫描股票池并挑出最多 5 个（至少 3 个，不够格宁可少给），结果缓存 5 分钟。"""
    results = []
    for s in pool:
        r = quant_evaluate_stock(s, horizon=horizon)
        if r:
            results.append(r)
    strict = [r for r in results if r["score"] >= 65]
    picks = sorted(strict, key=lambda x: x["score"], reverse=True)[:MAX_PICKS]
    if len(picks) < MIN_PICKS:
        relaxed = sorted([r for r in results if r["score"] >= 50], key=lambda x: x["score"], reverse=True)
        for r in relaxed:
            if r["symbol"] not in {p["symbol"] for p in picks}:
                picks.append(r)
            if len(picks) >= MIN_PICKS:
                break
        picks = sorted(picks, key=lambda x: x["score"], reverse=True)[:MAX_PICKS]
    return picks, len(results)

with tab0:
    st.subheader(f"⭐ 今日精选（{selected_horizon}）")
    st.caption("打开就自动扫描，结果缓存 5 分钟；想看最新的可以点下面的按钮重新扫描一次。")

    top_row = st.columns([3, 1])
    if top_row[1].button("🔄 立即重新扫描", key="rescan_tab0"):
        scan_today_picks.clear()

    with st.spinner(f"正在扫描 {len(SCAN_POOL)} 只股票，缓存过期时首次扫描约需 30-90 秒，请稍候…"):
        picks, scanned_n = scan_today_picks(SCAN_POOL, selected_horizon)
    top_row[0].info(f"本次扫描了 {scanned_n} / {len(SCAN_POOL)} 只股票　|　评分 ≥65 才入选，够格的不足 3 只时才放宽到 ≥50")

    if not picks:
        st.warning("这次扫描没有找到够格的设置。**没有好机会时不出手，本身就是一种策略。** 可以点上面的按钮重新扫描，或换个时间再看。")
    else:
        st.success(f"🎯 入选 {len(picks)} 个（最多显示 5 个）")
        newly_logged = 0
        for i, item in enumerate(picks, 1):
            t_class = "tag-bull" if item['score'] >= 65 else ("tag-neutral" if item['score'] >= 40 else "tag-bear")
            with st.container(border=True):
                st.markdown(f"#### #{i}　{item['symbol']}　·　<span class='{t_class}'>{item['score']}分 · {item['rating']}</span>",
                           unsafe_allow_html=True)
                st.markdown(f"**现价：** ${item['price']:,.2f}　（{item['pct']:+.2f}%）")
                st.markdown(f"**建议关注区间（入场）：** `{item['entry']}`")
                color_p = "#10B981" if item['target_pct'] >= 0 else "#EF4444"
                a, b = st.columns(2)
                a.markdown(f"🎯 **止盈点位：** <span style='color:{color_p};font-size:1.1rem;'>${item['target']:,.2f}</span>　"
                          f"<span style='color:{color_p};'>({item['target_pct']:+.1f}%)</span>", unsafe_allow_html=True)
                b.markdown(f"🛑 **止损点位：** <span style='color:#EF4444;font-size:1.1rem;'>${item['stop']:,.2f}</span>",
                          unsafe_allow_html=True)
                st.caption(f"止盈的波动区间（仅供参考，不是另一个买卖点）：${item['target_low']:,.2f} ~ ${item['target_high']:,.2f}"
                          f"（{item['target_low_pct']:+.1f}% ~ {item['target_high_pct']:+.1f}%）")
                st.caption(f"💡 {item['reason']}　{item.get('edge_note','')}")
            if auto_log_if_new_today(item['symbol'], selected_horizon, item['price'], item['target_pct'],
                                      item['target_low_pct'], item['target_high_pct']):
                newly_logged += 1
        if newly_logged:
            st.caption(f"📌 已自动把这 {newly_logged} 个新加入「预测复盘」记录，到期后会自动结算，不用手动点。"
                       + (f"（另外 {len(picks)-newly_logged} 个今天已经记过，不会重复）" if newly_logged < len(picks) else ""))
        else:
            st.caption("📌 这几个今天已经自动记过复盘了，不会重复写入。")

    st.caption("⚠️ 结果由固定规则机械算出，止损止盈仅供参考，请务必自己核对当前价格，不构成投资建议。")

with tab1:
    target_symbol = st.text_input("请输入股票代码 (Ticker):", value="MBLY").upper().strip()

    if target_symbol:
        res = quant_evaluate_stock(target_symbol, horizon=selected_horizon)
        if res:
            st.markdown(f"#### 📌 {res['symbol']} 深度量化报告")

            if res["high_vol_flag"]:
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
                st.write(f"• **🎯 {selected_horizon}止盈点位:** "
                         f"<b style='color:{color_p};font-size:1.1rem;'>${res['target']:.2f}</b> "
                         f"<span style='color:{color_p};'>({res['target_pct']:+.1f}%)</span>",
                         unsafe_allow_html=True)
                st.write(f"• **🛑 参考止损点位:** `${res['stop']:.2f}`")
                st.caption(f"止盈的波动区间（仅供参考，不是另一个买卖点）：${res['target_low']:.2f} ~ ${res['target_high']:.2f}"
                          f"（{res['target_low_pct']:+.1f}% ~ {res['target_high_pct']:+.1f}%）")

                st.markdown(f"<div class='reason-box'>💡 {res['reason']}<br>{res.get('edge_note','')}</div>", unsafe_allow_html=True)

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
                - **评分**：{len(res['signals'])} 个技术/估值/相对强弱因子等权打分，每个利好 +6 分、利空 -6 分，以 50 分为中枢，5–95 分封顶。
                - **预期收益率**：不是简单外推，而是「方向强度 × 历史波动率按 √时间 缩放 × 0.55 折算 × 历史校准系数」，
                  并硬性封顶在 ±{HORIZON_CAP_PCT[selected_horizon]:.0f}%，避免出现脱离实际的极端数字（例如短线 100%+ 的收益预测）。
                - **历史校准系数**：当前为 **{res['calib']['factor']:.2f}**（基于 {res['calib']['n']} 条已到期的历史预测计算，
                  样本不足 3 条时默认 1.0）。如果过去的预测持续偏乐观，这个系数会自动变小，让未来的预测更保守。
                """))
        else:
            st.warning("未能获取该代码的有效数据，请检查代码是否正确或稍后重试。")

with tab3:
    st.subheader("📜 策略实盘执行日志")
    if len(st.session_state.realtime_trade_logs) == 0:
        st.info("📌 当前暂无历史持仓，实盘数据将从你的第一笔操作开始记录。")
    else:
        st.dataframe(pd.DataFrame(st.session_state.realtime_trade_logs), use_container_width=True)

with tab4:
    st.subheader("🧠 预测复盘 & 自我校准")
    st.caption("说明：这不是黑箱式的『自动学习』，而是一个透明的反馈环 —— 系统记录每次预测，到期后自动对比真实价格，"
               "用历史误差算出一个校准系数（在 Tab1 的方法说明中可见），用于给未来的预测幅度降温或修正。")

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
