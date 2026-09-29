"""
每天由 GitHub Actions 自动运行，扫描股票池，挑出最多 5 个技术面共振的做多设置，
写入 data/latest_picks.json。Streamlit 的「今日精选」页面只负责读这个文件，不做计算。
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf
import pandas as pd
import numpy as np

POOL = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AVGO",
        "AMD", "NFLX", "CRM", "ORCL", "QCOM", "MU", "SPY", "QQQ"]
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "latest_picks.json"
MIN_PICKS = 3
MAX_PICKS = 5


def calc_rsi(close, n=14):
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss)


def calc_macd(close):
    line = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    return line - line.ewm(span=9, adjust=False).mean()


def calc_atr(df, n=14):
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - df["Close"].shift()).abs(),
                    (df["Low"] - df["Close"].shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def pivot_points(df, k=5):
    hi, lo = df["High"], df["Low"]
    ph = hi[hi == hi.rolling(2 * k + 1, center=True).max()]
    pl = lo[lo == lo.rolling(2 * k + 1, center=True).min()]
    return ph, pl


def cluster_levels(prices, tol=0.015):
    prices = sorted(prices)
    groups = []
    for p in prices:
        if groups and p <= np.mean(groups[-1]) * (1 + tol):
            groups[-1].append(p)
        else:
            groups.append([p])
    return [(float(np.mean(g)), len(g)) for g in groups]


def analyze(sym):
    h = yf.Ticker(sym).history(period="1y")
    if len(h) < 220:
        return None
    h.index = h.index.tz_localize(None)
    d = h[["Open", "High", "Low", "Close", "Volume"]].dropna()
    w = d.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min",
                                 "Close": "last", "Volume": "sum"}).dropna()
    price = float(d["Close"].iloc[-1])
    atr = float(calc_atr(d).iloc[-1])
    ma50, ma200 = float(d["Close"].rolling(50).mean().iloc[-1]), float(d["Close"].rolling(200).mean().iloc[-1])
    w20, w40 = float(w["Close"].rolling(20).mean().iloc[-1]), float(w["Close"].rolling(40).mean().iloc[-1])
    rsi_d = float(calc_rsi(d["Close"]).iloc[-1])
    macd_hist = calc_macd(d["Close"])
    h_now, h_prev = float(macd_hist.iloc[-1]), float(macd_hist.iloc[-2])

    recent = d.tail(250)
    ph, pl = pivot_points(recent, 5)
    levels = cluster_levels(list(ph.values) + list(pl.values) +
                            [float(recent["High"].max()), float(recent["Low"].min())])
    below = [(p, n) for p, n in levels if p < price * 0.998]
    above = [(p, n) for p, n in levels if p > price * 1.002]
    support = max(below, key=lambda x: x[0]) if below else None
    resist = min(above, key=lambda x: x[0]) if above else None

    score = 0
    score += 2 if price > w20 > w40 else (-2 if price < w20 < w40 else 0)
    score += 1 if price > ma50 > ma200 else (-1 if price < ma50 < ma200 else 0)
    score += 1 if (h_now > 0 and h_now >= h_prev) else (-1 if (h_now < 0 and h_now <= h_prev) else 0)
    score += -1 if rsi_d > 70 else (1 if rsi_d < 30 else 0)
    if support and (price - support[0]) / price <= 0.03:
        score += 1
    elif resist and (resist[0] - price) / price <= 0.02:
        score -= 1

    stop = (support[0] - 0.5 * atr) if support else price - 2 * atr
    if stop >= price:
        stop = price - 2 * atr
    target = resist[0] if resist else price + 3 * atr
    risk = price - stop
    rr = (target - price) / risk if risk > 0 and target > price else None

    return {"symbol": sym, "price": round(price, 2), "score": int(score),
            "entry": round(price, 2), "stop": round(stop, 2), "target": round(target, 2),
            "rr": round(rr, 2) if rr else None, "atr_pct": round(atr / price * 100, 1)}


def scan_pool(pool, progress_cb=None):
    """扫描一批代码，返回每只的分析结果（失败的自动跳过）。progress_cb(done, total, symbol) 可选，用于显示进度。"""
    results = []
    total = len(pool)
    for i, s in enumerate(pool):
        try:
            r = analyze(s)
            if r:
                results.append(r)
        except Exception as e:
            print(f"跳过 {s}：{e}")
        if progress_cb:
            progress_cb(i + 1, total, s)
    return results


def select_picks(results, min_picks=MIN_PICKS, max_picks=MAX_PICKS):
    """从扫描结果里挑出最多 max_picks 个：优先用严格标准，不够数再放宽，但宁可少给也不硬凑。"""
    strict = [r for r in results if r["score"] >= 2 and r["rr"] and r["rr"] >= 1.5]
    picks = sorted(strict, key=lambda x: (x["score"], x["rr"]), reverse=True)[:max_picks]
    if len(picks) < min_picks:
        relaxed = sorted([r for r in results if r["score"] >= 1], key=lambda x: x["score"], reverse=True)
        for r in relaxed:
            if r["symbol"] not in {p["symbol"] for p in picks}:
                picks.append(r)
            if len(picks) >= min_picks:
                break
        picks = sorted(picks, key=lambda x: x["score"], reverse=True)[:max_picks]
    return picks


def main():
    results = scan_pool(POOL)
    picks = select_picks(results)
    payload = {"updated_at": datetime.now(timezone.utc).isoformat(), "picks": picks,
              "scanned": len(results), "pool_size": len(POOL)}
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {len(picks)} 个精选到 {OUT_PATH}")


if __name__ == "__main__":
    main()
