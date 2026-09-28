from datetime import datetime

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="交易想法生成器", page_icon="💡", layout="wide")
st.title("💡 交易想法生成器")
st.caption("扫描一批股票/ETF，挑出最多 5 个技术面共振的做多设置，给出入场、止损、目标、风险回报比和建议股数。仅供研究学习，不构成投资建议。")

POOLS = {
    "美股科技龙头": "AAPL MSFT NVDA GOOGL AMZN META TSLA AVGO ORCL ADBE",
    "半导体板块": "NVDA AMD AVGO QCOM MU TSM INTC AMAT LRCX ASML",
    "行业 ETF（看板块强弱）": "XLK XLF XLE XLV XLY XLP XLI XLU XLB XLC",
    "大盘指数 ETF": "SPY QQQ IWM DIA",
    "自定义": "",
}

c1, c2, c3 = st.columns(3)
pool_name = c1.selectbox("扫描范围", list(POOLS.keys()))
capital = c2.number_input("账户总资金 ($)", 100.0, 10_000_000.0, 5000.0, step=100.0)
risk_pct = c3.slider("单笔最大风险（占总资金 %）", 0.5, 5.0, 2.0, step=0.5)

if pool_name == "自定义":
    raw = st.text_input("输入代码，用空格或逗号隔开（最多 15 个）", value="AAPL MSFT NVDA")
else:
    raw = POOLS[pool_name]
symbols = list(dict.fromkeys(s.strip().upper() for s in raw.replace(",", " ").split() if s.strip()))[:15]
st.caption("将扫描：" + "、".join(symbols) if symbols else "请先输入代码")
with_fund = st.checkbox("同时获取基本面（PE、营收增速等，较慢）", value=True)


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



# ---------------- 基本面与财报日 ----------------
@st.cache_data(ttl=3600)
def get_fundamentals(sym):
    out = {"pe": None, "growth": None, "margin": None, "earn_days": None}
    try:
        t = yf.Ticker(sym)
        info = t.info or {}
        out["pe"] = info.get("forwardPE") or info.get("trailingPE")
        out["growth"] = info.get("revenueGrowth")
        out["margin"] = info.get("profitMargins")
        try:
            cal = t.calendar
            dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
            if dates:
                today = datetime.now().date()
                future = [x for x in dates if x >= today]
                if future:
                    out["earn_days"] = (min(future) - today).days
        except Exception:
            pass
    except Exception:
        pass
    return out


# ---------------- 生成交易设置 ----------------
def build_idea(sym, d, w, cap, risk_pct):
    r = analyze(d, w)
    price, atr = r["price"], r["atr"]
    sup, res = r["support"], r["resist"]

    stop = (sup[0] - 0.5 * atr) if sup else price - 2 * atr
    if stop >= price:
        stop = price - 2 * atr
    target = res[0] if res else price + 3 * atr
    risk = price - stop
    rr = (target - price) / risk if risk > 0 and target > price else np.nan

    pull_entry, pull_rr = None, None
    if sup and price > sup[0] * 1.03:
        pull_entry = sup[0] * 1.01
        risk2 = pull_entry - stop
        if risk2 > 0 and target > pull_entry:
            pull_rr = (target - pull_entry) / risk2

    risk_usd = cap * risk_pct / 100
    shares = int(risk_usd / risk) if risk > 0 else 0
    shares = min(shares, int(cap * 0.4 / price))  # 单只最多占总资金 40%

    if r["score"] < 2:
        status = "评分不足"
    elif np.isnan(rr) or rr < 1.5:
        status = "性价比低"
    else:
        status = "入选"
    return {"symbol": sym, "price": price, "score": r["score"], "verdict": r["verdict"], "steps": r["steps"],
            "stop": stop, "target": target, "rr": rr, "pull_entry": pull_entry, "pull_rr": pull_rr,
            "shares": shares, "risk_usd": risk_usd, "status": status, "support": sup, "resist": res}


# ---------------- 页面 ----------------
if st.button("🔍 开始扫描", type="primary") and symbols:
    ideas, failed = [], []
    bar = st.progress(0.0, text="正在扫描…")
    for i, s in enumerate(symbols):
        bar.progress((i + 1) / len(symbols), text=f"正在分析 {s}（{i+1}/{len(symbols)}）")
        d = load_history(s)
        if len(d) < 220:
            failed.append(s)
            continue
        try:
            ideas.append(build_idea(s, d, to_weekly(d), capital, risk_pct))
        except Exception:
            failed.append(s)
    bar.empty()

    if failed:
        st.warning(f"以下代码数据不足或分析失败，已跳过：{', '.join(failed)}")
    if not ideas:
        st.error("没有可用的数据，请稍后重试。")
        st.stop()

    # 大盘环境
    spy_d = load_history("SPY")
    if len(spy_d) >= 220:
        spy_r = analyze(spy_d, to_weekly(spy_d))
        if spy_r["score"] <= -2:
            st.error(f"🌧️ 大盘环境偏弱（SPY 得分 {spy_r['score']:+d}，{spy_r['verdict']}）。逆势做多的成功率通常更低，请降低仓位或等待。")
        elif spy_r["score"] >= 2:
            st.success(f"☀️ 大盘环境偏强（SPY 得分 {spy_r['score']:+d}，{spy_r['verdict']}），顺势做多更有利。")
        else:
            st.info(f"⛅ 大盘环境中性（SPY 得分 {spy_r['score']:+d}），个股信号要多留一份谨慎。")

    picks = sorted([x for x in ideas if x["status"] == "入选"], key=lambda x: (x["score"], x["rr"]), reverse=True)[:5]

    st.subheader(f"🎯 今日入选的做多设置（{len(picks)} 个）")
    if not picks:
        st.info("这批股票里，暂时没有同时满足『得分 ≥ 2』和『风险回报比 ≥ 1.5』的设置。**没有好机会时不交易，本身就是一种策略。** 可以换个扫描范围，或明天再看。")
    elif len(picks) < 5:
        st.caption(f"只有 {len(picks)} 个满足条件，不会为了凑数而降低标准。")

    for i, x in enumerate(picks, 1):
        fund = get_fundamentals(x["symbol"]) if with_fund else {}
        with st.container(border=True):
            st.markdown(f"### #{i}　{x['symbol']}　·　得分 {x['score']:+d}　·　{x['verdict']}")
            a, b, c, e, f = st.columns(5)
            a.metric("入场（现价）", f"${x['price']:.2f}")
            b.metric("止损", f"${x['stop']:.2f}", f"{(x['stop']/x['price']-1)*100:.1f}%", delta_color="off")
            c.metric("目标", f"${x['target']:.2f}", f"+{(x['target']/x['price']-1)*100:.1f}%", delta_color="off")
            e.metric("风险回报比", f"{x['rr']:.1f} : 1")
            f.metric("建议股数", f"{x['shares']} 股" if x["shares"] > 0 else "资金不足")
            if x["shares"] > 0:
                st.caption(f"按单笔最大亏损 ${x['risk_usd']:.0f} 计算，约占用资金 ${x['shares']*x['price']:,.0f}。触及止损时亏损约 ${x['shares']*(x['price']-x['stop']):.0f}。")
            else:
                st.caption("按你设的风险额度，连 1 股都买不起（每股风险太大），建议跳过。")
            if x["pull_entry"]:
                pr = f"（回踩买点风险回报比 {x['pull_rr']:.1f} : 1）" if x["pull_rr"] else ""
                st.markdown(f"🪝 **更好的买点**：现价离支撑较远，可以挂单等回踩到 **${x['pull_entry']:.2f}** 附近再买 {pr}")

            st.markdown("**为什么有效（技术面）：**")
            for s, v, t in x["steps"]:
                if v > 0:
                    st.markdown(f"- 🟢 {s.split(' ', 1)[1]}：{t}")
            fund_bits = []
            if fund.get("pe"):
                fund_bits.append(f"动态 PE {fund['pe']:.1f}")
            if fund.get("growth") is not None:
                fund_bits.append(f"营收同比 {fund['growth']*100:+.0f}%")
            if fund.get("margin") is not None:
                fund_bits.append(f"净利润率 {fund['margin']*100:.0f}%")
            if fund_bits:
                st.markdown("**基本面参考：** " + "　|　".join(fund_bits))

            warns = [f"🔴 {s.split(' ', 1)[1]}：{t}" for s, v, t in x["steps"] if v < 0]
            if fund.get("earn_days") is not None and fund["earn_days"] <= 10:
                warns.append(f"🟠 **{fund['earn_days']} 天后发布财报**，财报前后价格可能大幅跳空，止损可能失效。")
            if fund.get("pe") and fund["pe"] > 50:
                warns.append(f"🟠 估值偏高（PE {fund['pe']:.0f}），回调时跌幅可能更大。")
            if warns:
                st.markdown("**需要留意：**")
                for wtxt in warns:
                    st.markdown(f"- {wtxt}")

    st.subheader("📋 全部扫描结果")
    tbl = pd.DataFrame([{"代码": x["symbol"], "现价": round(x["price"], 2), "得分": x["score"], "信号": x["verdict"],
                         "风险回报比": None if np.isnan(x["rr"]) else round(x["rr"], 1), "状态": x["status"]}
                        for x in sorted(ideas, key=lambda y: y["score"], reverse=True)])
    st.dataframe(tbl, use_container_width=True, hide_index=True)

    with st.expander("📖 入选条件与方法说明"):
        st.markdown(
            "- **入选条件**：技术面得分 ≥ 2（周线/日线趋势、MACD、RSI、支撑阻力、量价共 7 项打分），并且风险回报比 ≥ 1.5。\n"
            "- **止损**：最近支撑下方 0.5 倍 ATR（没有支撑则用现价下方 2 倍 ATR）。**目标**：最近的阻力位。\n"
            "- **建议股数** = 单笔最大风险 ÷ 每股风险，且单只不超过总资金的 40%。\n"
            "- **关于『高概率』**：这里的得分代表『多个信号同时指向做多』，并不是统计出来的胜率。想知道某类信号历史上有多灵，可以到『策略回测器』页面验证。\n"
            "- 技术信号会失效，请一定设置止损。不构成投资建议。"
        )
