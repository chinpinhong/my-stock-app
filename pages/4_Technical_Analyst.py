import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="自动化技术分析师", page_icon="📈", layout="wide")
st.title("📈 自动化技术分析师")
st.caption("结合日线和周线，自动找支撑/阻力、趋势线、均线和动量，并给出分步信号。仅供研究学习，不构成投资建议。")

symbol = st.text_input("股票/ETF 代码", value="AAPL").upper().strip()


# ---------------- 数据与指标 ----------------
@st.cache_data(ttl=600)
def load_history(sym):
    try:
        h = yf.Ticker(sym).history(period="2y")
        if h.empty:
            return pd.DataFrame()
        h.index = h.index.tz_localize(None)
        return h[["Open", "High", "Low", "Close", "Volume"]].dropna()
    except Exception:
        return pd.DataFrame()


def to_weekly(d):
    return d.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min",
                                    "Close": "last", "Volume": "sum"}).dropna()


def calc_rsi(close, n=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss)


def calc_macd(close):
    line = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    sig = line.ewm(span=9, adjust=False).mean()
    return line, sig, line - sig


def calc_atr(df, n=14):
    tr = pd.concat([df["High"] - df["Low"],
                    (df["High"] - df["Close"].shift()).abs(),
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


def trendline(pivots, df, rising):
    """连接最近两个摆动点画趋势线；rising=True 用低点(需抬高)，False 用高点(需降低)。"""
    pts = pivots.tail(6)
    if len(pts) < 2:
        return None
    p1, p2 = pts.iloc[-2], pts.iloc[-1]
    if (rising and p2 <= p1) or ((not rising) and p2 >= p1):
        return None
    pos1, pos2 = df.index.get_loc(pts.index[-2]), df.index.get_loc(pts.index[-1])
    if pos2 == pos1:
        return None
    slope = (p2 - p1) / (pos2 - pos1)
    return float(p2 + slope * (len(df) - 1 - pos2))


# ---------------- 核心分析 ----------------
def analyze(d, w):
    price = float(d["Close"].iloc[-1])
    atr = float(calc_atr(d).iloc[-1])

    # 均线
    ma20, ma50, ma200 = [float(d["Close"].rolling(n).mean().iloc[-1]) for n in (20, 50, 200)]
    w10, w20, w40 = [float(w["Close"].rolling(n).mean().iloc[-1]) for n in (10, 20, 40)]

    # 动量
    rsi_d, rsi_w = float(calc_rsi(d["Close"]).iloc[-1]), float(calc_rsi(w["Close"]).iloc[-1])
    _, _, hist_d = calc_macd(d["Close"])
    line_w, sig_w, _ = calc_macd(w["Close"])

    # 支撑/阻力（日线近 250 根 + 周线摆动点）
    recent = d.tail(250)
    ph, pl = pivot_points(recent, 5)
    wph, wpl = pivot_points(w.tail(104), 3)
    all_pts = list(ph.values) + list(pl.values) + list(wph.values) + list(wpl.values)
    all_pts += [float(recent["High"].max()), float(recent["Low"].min())]
    levels = cluster_levels(all_pts)
    below = [(p, n) for p, n in levels if p < price * 0.998]
    above = [(p, n) for p, n in levels if p > price * 1.002]
    strong_below = [x for x in below if x[1] >= 2] or below
    strong_above = [x for x in above if x[1] >= 2] or above
    support = max(strong_below, key=lambda x: x[0]) if strong_below else None
    resist = min(strong_above, key=lambda x: x[0]) if strong_above else None

    # 趋势线
    up_line = trendline(pl.tail(6), recent, True)
    down_line = trendline(ph.tail(6), recent, False)

    # 量价
    vol_ratio = float(d["Volume"].iloc[-1] / d["Volume"].tail(20).mean())
    chg1 = float(d["Close"].iloc[-1] / d["Close"].iloc[-2] - 1)
    hi52 = float(recent["High"].max())

    steps = []  # (步骤, 分数, 结论)

    if price > w20 > w40:
        steps.append(("① 周线趋势（大方向）", 2, f"价格 > 20周均线(${w20:.2f}) > 40周均线(${w40:.2f})，周线多头排列"))
    elif price < w20 < w40:
        steps.append(("① 周线趋势（大方向）", -2, f"价格 < 20周均线(${w20:.2f}) < 40周均线(${w40:.2f})，周线空头排列"))
    else:
        steps.append(("① 周线趋势（大方向）", 0, "周线均线交织，大方向不明确"))

    if price > ma50 > ma200:
        steps.append(("② 日线趋势", 1, f"价格 > 50日线(${ma50:.2f}) > 200日线(${ma200:.2f})，日线多头"))
    elif price < ma50 < ma200:
        steps.append(("② 日线趋势", -1, f"价格 < 50日线(${ma50:.2f}) < 200日线(${ma200:.2f})，日线空头"))
    else:
        steps.append(("② 日线趋势", 0, f"价格与 50/200 日线纠缠，趋势不清（50日 ${ma50:.2f}，200日 ${ma200:.2f}）"))

    h_now, h_prev = float(hist_d.iloc[-1]), float(hist_d.iloc[-2])
    if h_now > 0 and h_now >= h_prev:
        steps.append(("③ 日线动能 (MACD)", 1, "MACD 柱在零轴上方且在增强，上涨动能充足"))
    elif h_now < 0 and h_now <= h_prev:
        steps.append(("③ 日线动能 (MACD)", -1, "MACD 柱在零轴下方且在扩大，下跌动能占优"))
    else:
        steps.append(("③ 日线动能 (MACD)", 0, "MACD 动能在减弱或转折中，等待确认"))

    if float(line_w.iloc[-1]) > float(sig_w.iloc[-1]):
        steps.append(("④ 周线动能 (MACD)", 1, "周线 MACD 在信号线上方，中期动能偏多"))
    else:
        steps.append(("④ 周线动能 (MACD)", -1, "周线 MACD 在信号线下方，中期动能偏空"))

    if rsi_d > 70 or rsi_w > 75:
        steps.append(("⑤ 超买超卖 (RSI)", -1, f"日线 RSI={rsi_d:.0f}，周线 RSI={rsi_w:.0f}，偏超买，追高风险大"))
    elif rsi_d < 30:
        steps.append(("⑤ 超买超卖 (RSI)", 1, f"日线 RSI={rsi_d:.0f}，超卖，存在反弹机会"))
    else:
        steps.append(("⑤ 超买超卖 (RSI)", 0, f"日线 RSI={rsi_d:.0f}，周线 RSI={rsi_w:.0f}，处于正常区间"))

    if support and (price - support[0]) / price <= 0.03:
        steps.append(("⑥ 支撑/阻力位置", 1, f"靠近支撑 ${support[0]:.2f}（距离 {(price-support[0])/price*100:.1f}%），止损空间小"))
    elif resist and (resist[0] - price) / price <= 0.02:
        steps.append(("⑥ 支撑/阻力位置", -1, f"逼近阻力 ${resist[0]:.2f}（仅 {(resist[0]-price)/price*100:.1f}%），上方空间有限"))
    elif price >= hi52 * 0.98:
        steps.append(("⑥ 支撑/阻力位置", 1, "接近 52 周新高，上方没有明显套牢盘"))
    else:
        steps.append(("⑥ 支撑/阻力位置", 0, "位于支撑与阻力之间，位置一般"))

    if vol_ratio > 1.3 and chg1 > 0:
        steps.append(("⑦ 量价配合", 1, f"放量上涨（{vol_ratio:.1f} 倍均量），资金在进场"))
    elif vol_ratio > 1.3 and chg1 < 0:
        steps.append(("⑦ 量价配合", -1, f"放量下跌（{vol_ratio:.1f} 倍均量），有资金在出货"))
    else:
        steps.append(("⑦ 量价配合", 0, f"量能 {vol_ratio:.1f} 倍均量，无明显异动"))

    score = sum(s[1] for s in steps)
    if score >= 4:
        verdict, tone = "买入", "bull"
    elif score >= 2:
        verdict, tone = "持有（偏多）", "bull"
    elif score >= -1:
        verdict, tone = "持有 / 观望", "neutral"
    elif score >= -3:
        verdict, tone = "持有（偏空，谨慎/减仓）", "bear"
    else:
        verdict, tone = "卖出", "bear"

    plan = None
    if score >= 2:
        stop = (support[0] - 0.5 * atr) if support else price - 2 * atr
        if stop >= price:
            stop = price - 2 * atr
        target = resist[0] if resist else price + 3 * atr
        risk, reward = price - stop, target - price
        plan = {"stop": stop, "target": target, "rr": reward / risk if risk > 0 else np.nan}

    return {"price": price, "atr": atr, "steps": steps, "score": score, "verdict": verdict, "tone": tone,
            "support": support, "resist": resist, "levels": levels, "up_line": up_line,
            "down_line": down_line, "plan": plan,
            "ma": (ma20, ma50, ma200), "wma": (w10, w20, w40)}


# ---------------- 页面 ----------------
if symbol:
    d = load_history(symbol)
    if len(d) < 220:
        st.warning("没取到足够的历史数据（至少需要约 1 年），请检查代码是否正确。")
        st.stop()
    w = to_weekly(d)
    r = analyze(d, w)

    # 结论
    box = {"bull": st.success, "neutral": st.warning, "bear": st.error}[r["tone"]]
    box(f"### {symbol}　综合信号：{r['verdict']}　（得分 {r['score']:+d} / 满分 ±8）　现价 ${r['price']:.2f}")

    # 分步信号
    st.subheader("🪜 分步信号与理由")
    tbl = pd.DataFrame([{"步骤": s, "方向": "🟢 +%d" % v if v > 0 else ("🔴 %d" % v if v < 0 else "🟡 0"), "理由": t}
                        for s, v, t in r["steps"]])
    st.dataframe(tbl, use_container_width=True, hide_index=True)
    st.caption("周线趋势权重最高（±2），因为大方向比短线信号更重要；其余每项 ±1。")

    # 关键价位
    st.subheader("🎯 关键价位与交易参考")
    a, b, c, e = st.columns(4)
    a.metric("最近支撑", f"${r['support'][0]:.2f}" if r["support"] else "—",
             help=f"被触及 {r['support'][1]} 次" if r["support"] else None)
    b.metric("最近阻力", f"${r['resist'][0]:.2f}" if r["resist"] else "—（接近新高）",
             help=f"被触及 {r['resist'][1]} 次" if r["resist"] else None)
    c.metric("上升趋势线（今日值）", (f"${r['up_line']:.2f}" + ("（已跌破）" if r["up_line"] > r["price"] else "")) if r["up_line"] else "—",
             help="连接最近两个逐步抬高的低点。跌破它意味着上升趋势可能结束。" if r["up_line"] else "近期低点没有逐步抬高")
    e.metric("下降趋势线（今日值）", (f"${r['down_line']:.2f}" + ("（已突破）" if r["down_line"] < r["price"] else "")) if r["down_line"] else "—",
             help="连接最近两个逐步降低的高点。突破它意味着下跌趋势可能结束。" if r["down_line"] else "近期高点没有逐步降低")

    if r["plan"]:
        p = r["plan"]
        st.info(f"**做多参考**：现价 ${r['price']:.2f}　|　止损 ${p['stop']:.2f}　|　目标 ${p['target']:.2f}　|　风险回报比 "
                f"{p['rr']:.1f} : 1" + ("　⚠️ 低于 1.5，性价比一般，可等回踩支撑再考虑。" if p["rr"] < 1.5 else ""))
    else:
        st.info("当前信号不支持做多，因此不给入场参考。可以先把上面的支撑/阻力设成价格提醒，等信号改善再看。")

    # 图表
    st.subheader("📉 日线图（近 1 年）")
    dd = d.tail(250)
    chart = pd.DataFrame({"收盘价": dd["Close"],
                          "20日线": d["Close"].rolling(20).mean().tail(250),
                          "50日线": d["Close"].rolling(50).mean().tail(250),
                          "200日线": d["Close"].rolling(200).mean().tail(250)})
    if r["support"]:
        chart["最近支撑"] = r["support"][0]
    if r["resist"]:
        chart["最近阻力"] = r["resist"][0]
    st.line_chart(chart)

    st.subheader("📉 周线图（近 2 年）")
    wc = pd.DataFrame({"周收盘": w["Close"], "10周线": w["Close"].rolling(10).mean(),
                       "20周线": w["Close"].rolling(20).mean(), "40周线": w["Close"].rolling(40).mean()})
    st.line_chart(wc)

    with st.expander("📋 所有识别出的价位（按价格从高到低）"):
        lv = pd.DataFrame(r["levels"], columns=["价位", "被触及次数"])
        lv["类型"] = np.where(lv["价位"] > r["price"], "阻力", "支撑")
        lv["距现价(%)"] = ((lv["价位"] / r["price"] - 1) * 100).round(1)
        lv["价位"] = lv["价位"].round(2)
        st.dataframe(lv.sort_values("价位", ascending=False), use_container_width=True, hide_index=True)
        st.caption("被触及次数越多，这个价位通常越有参考价值。")

    with st.expander("📖 方法说明"):
        st.markdown(
            "- **支撑/阻力**：找出近一年日线和近两年周线的『摆动高低点』，把相差 1.5% 以内的合并成一个价位，触及次数越多越可靠。\n"
            "- **趋势线**：连接最近两个摆动低点（上升）或高点（下降），并延伸到今天。\n"
            "- **得分**：7 项检查加总，≥4 买入，2~3 偏多持有，−1~1 观望，−2~−3 偏空，≤−4 卖出。\n"
            "- 技术分析只是概率参考，不保证结果，请配合止损和仓位管理。不构成投资建议。"
        )
