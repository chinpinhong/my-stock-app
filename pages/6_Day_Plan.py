from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="完整日交易计划", page_icon="🗓️", layout="wide")
st.title("🗓️ 完整日交易计划")
st.caption("盘前扫描 → 开盘策略 → 盘中调整 → 收盘处理，按时间节点生成可勾选的执行清单。仅供研究学习，不构成投资建议。")

ET = ZoneInfo("America/New_York")
ZONES = {"美东时间 (ET)": ("America/New_York", "ET"),
         "新加坡时间 (SGT)": ("Asia/Singapore", "SGT"),
         "北京/香港时间": ("Asia/Shanghai", "CST")}

# ---------------- 输入 ----------------
c1, c2, c3, c4 = st.columns(4)
watch_raw = c1.text_input("自选股（空格或逗号隔开，最多 10 个）", value="NVDA TSLA AMD AAPL META")
capital = c2.number_input("账户总资金 ($)", 100.0, 10_000_000.0, 5000.0, step=100.0)
risk_pct = c3.slider("单笔最大风险（占总资金 %）", 0.25, 3.0, 1.0, step=0.25)
zone_name = c4.selectbox("时间显示", list(ZONES.keys()))
d1, d2 = st.columns(2)
max_daily_loss_pct = d1.slider("单日最大亏损（占总资金 %）—— 触及即停手", 1.0, 6.0, 3.0, step=0.5)
max_trades = d2.slider("每日最多开仓笔数", 1, 8, 3)

symbols = list(dict.fromkeys(s.strip().upper() for s in watch_raw.replace(",", " ").split() if s.strip()))[:10]

st.info("ℹ️ 美国已取消『4 笔日内交易触发 25,000 美元门槛』的 PDT 规则（2026 年 6 月 4 日生效），但各券商可在过渡期内保留自己的限制，"
        "请以你所用券商当前的规定为准。另外，研究普遍显示大多数日内交易者长期并不盈利，请务必控制风险。")


# ---------------- 时间换算 ----------------
def now_et():
    return datetime.now(ET)


def plan_date():
    """计划针对的交易日：周末顺延到周一。"""
    d = now_et().date()
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def T(h, m=0):
    tz_key, tz_label = ZONES[zone_name]
    dt = datetime.combine(plan_date(), time(h, m), ET).astimezone(ZoneInfo(tz_key))
    s = f"{dt:%H:%M}"
    if dt.date() > plan_date() and tz_label != "ET":
        s += "(+1天)"
    elif dt.date() < plan_date() and tz_label != "ET":
        s += "(-1天)"
    return f"{s} {tz_label}"


# ---------------- 数据 ----------------
@st.cache_data(ttl=300)
def load_daily(sym):
    try:
        h = yf.Ticker(sym).history(period="4mo")
        if h.empty:
            return pd.DataFrame()
        h.index = h.index.tz_localize(None)
        return h[["Open", "High", "Low", "Close", "Volume"]].dropna()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=120)
def load_latest(sym):
    """最新价（含盘前盘后）。取不到返回 None。"""
    try:
        h = yf.Ticker(sym).history(period="5d", interval="5m", prepost=True)
        return float(h["Close"].iloc[-1]) if not h.empty else None
    except Exception:
        return None


def analyze_symbol(sym, d, latest, now):
    """基于昨日已完成的日线，计算今日日内计划所需的关键数据。"""
    in_progress = d.index[-1].date() == now.date() and now.time() < time(16, 0) and now.weekday() < 5
    end = len(d) - 1 if in_progress else len(d)
    hist = d.iloc[:end]
    if len(hist) < 55:
        return None
    prev = hist.iloc[-1]
    close = hist["Close"]
    tr = pd.concat([hist["High"] - hist["Low"], (hist["High"] - close.shift()).abs(),
                    (hist["Low"] - close.shift()).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])
    ma20, ma50 = float(close.rolling(20).mean().iloc[-1]), float(close.rolling(50).mean().iloc[-1])
    prev_close = float(prev["Close"])
    price = latest if latest else prev_close
    gap = price / prev_close - 1
    relvol = float(prev["Volume"] / hist["Volume"].tail(20).mean())
    atr_pct = atr / prev_close * 100

    trend = 1 if price > ma20 > ma50 else (-1 if price < ma20 < ma50 else 0)
    if trend == 1 and gap > -0.005:
        bias = "偏多"
    elif trend == -1 and gap < 0.005:
        bias = "偏空"
    elif trend == 0 and gap >= 0.01:
        bias = "偏多"
    elif trend == 0 and gap <= -0.01:
        bias = "偏空"
    else:
        bias = "观望"

    score = 0
    score += 2 if abs(gap) >= 0.01 else (1 if abs(gap) >= 0.005 else 0)
    score += 1 if relvol >= 1.3 else 0
    score += 1 if trend != 0 else 0
    score += 1 if atr_pct >= 2 else -1

    H, L, C = float(prev["High"]), float(prev["Low"]), prev_close
    P = (H + L + C) / 3
    stop_dist = max(0.3 * atr, price * 0.004)
    risk_usd = capital * risk_pct / 100
    shares = int(risk_usd / stop_dist) if stop_dist > 0 else 0
    if shares * price > capital:
        shares = int(capital / price)
    return {"sym": sym, "price": price, "gap": gap, "relvol": relvol, "atr": atr, "atr_pct": atr_pct,
            "trend": trend, "bias": bias, "score": score, "has_pre": latest is not None,
            "H": H, "L": L, "C": C, "P": P, "R1": 2 * P - L, "S1": 2 * P - H, "R2": P + (H - L), "S2": P - (H - L),
            "stop_dist": stop_dist, "shares": shares, "risk_usd": risk_usd}


def gap_advice(x):
    g, rv = abs(x["gap"]), x["relvol"]
    if g >= 0.02 and rv >= 1.3:
        return "大幅跳空 + 昨日放量：偏向『顺势延续』，不要在第一分钟追，等开盘区间突破或回踩不破再入场。"
    if g >= 0.01:
        return "中等跳空：警惕缺口被回补。若价格回到昨收（$%.2f）附近，就放弃这个方向。" % x["C"]
    return "缺口不大：以开盘区间突破 + VWAP 位置为准，不预设方向。"


# ---------------- 页面 ----------------
if st.button("🗓️ 生成今日交易计划", type="primary"):
    st.session_state["plan_ready"] = True

if st.session_state.get("plan_ready") and symbols:
    md = []
    now = now_et()
    pd_date = plan_date()
    if now.weekday() >= 5:
        st.warning(f"今天是周末，美股休市。以下计划按下一个交易日（{pd_date}）准备，数据为上一交易日收盘后的状态。")
    st.success(f"**计划交易日：{pd_date}**　|　美股常规交易时间 {T(9, 30)} – {T(16, 0)}")
    md.append(f"# 日交易计划 {pd_date}\n")

    risk_usd = capital * risk_pct / 100
    max_loss_usd = capital * max_daily_loss_pct / 100

    # ---- 风险铁律 ----
    st.subheader("🛡️ 今日风险铁律（先写下来，再交易）")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("单笔最大亏损", f"${risk_usd:.0f}")
    r2.metric("单日最大亏损（触及即停）", f"${max_loss_usd:.0f}")
    r3.metric("最多开仓笔数", max_trades)
    r4.metric("连亏 2 笔", "停手 30 分钟")
    md += ["## 风险铁律", f"- 单笔最大亏损 ${risk_usd:.0f}；单日最大亏损 ${max_loss_usd:.0f}，触及即停手",
           f"- 每日最多 {max_trades} 笔；连亏 2 笔停手 30 分钟；不给亏损单加仓；日内仓位收盘前全部平掉\n"]

    # ---- 大盘环境 ----
    st.subheader(f"☀️ 盘前 {T(8, 0)} 起：大盘环境")
    mk_rows, spy_info, vix = [], None, None
    for s, label in [("SPY", "标普500 ETF"), ("QQQ", "纳指100 ETF"), ("^VIX", "恐慌指数 VIX")]:
        d = load_daily(s)
        if len(d) < 60:
            continue
        x = analyze_symbol(s, d, load_latest(s), now)
        if x is None:
            continue
        mk_rows.append({"标的": f"{s}（{label}）", "最新价": round(x["price"], 2),
                        "盘前/隔夜涨跌(%)": round(x["gap"] * 100, 2) if x["has_pre"] else None,
                        "趋势": {1: "上行", 0: "震荡", -1: "下行"}[x["trend"]]})
        if s == "SPY":
            spy_info = x
        if s == "^VIX":
            vix = x["price"]
    if mk_rows:
        st.dataframe(pd.DataFrame(mk_rows), use_container_width=True, hide_index=True)
    size_factor, env_msg = 1.0, "大盘数据不足，请人工判断。"
    if spy_info:
        if spy_info["trend"] == 1 and spy_info["gap"] > -0.003:
            env_msg = "大盘顺风：可以正常执行多头计划。"
        elif spy_info["trend"] == -1 or spy_info["gap"] < -0.01:
            env_msg = "大盘逆风：做多要更挑剔，仓位减半。"
            size_factor = 0.5
        else:
            env_msg = "大盘中性：只做最清晰的设置。"
    if vix is not None:
        if vix > 30:
            env_msg += f" VIX={vix:.1f}（极高），波动剧烈，建议今日仓位再减半或休息。"
            size_factor *= 0.5
        elif vix > 22:
            env_msg += f" VIX={vix:.1f}（偏高），止损要留宽一点，仓位相应缩小。"
            size_factor *= 0.75
        else:
            env_msg += f" VIX={vix:.1f}（正常/偏低）。"
    st.info(f"{env_msg}　**建议今日仓位系数：×{size_factor:.2f}**")
    md += ["## 大盘环境", env_msg, f"建议今日仓位系数 ×{size_factor:.2f}\n"]

    # ---- 自选股扫描 ----
    st.subheader(f"🔎 盘前 {T(9, 0)}：自选股扫描与重点股")
    results, failed = [], []
    for s in symbols:
        d = load_daily(s)
        x = analyze_symbol(s, d, load_latest(s), now) if len(d) >= 60 else None
        (results if x else failed).append(x if x else s)
    if failed:
        st.warning(f"以下代码数据不足，已跳过：{', '.join(failed)}")
    if not results:
        st.error("没有可用的数据，请稍后重试。")
        st.stop()
    if not any(x["has_pre"] for x in results):
        st.caption("提示：暂时没取到盘前价格，下面的『缺口』按昨收计算为 0，开盘前请再点一次生成。")

    tbl = pd.DataFrame([{"代码": x["sym"], "最新价": round(x["price"], 2), "缺口(%)": round(x["gap"] * 100, 2),
                         "昨日量比": round(x["relvol"], 2), "ATR(%)": round(x["atr_pct"], 1),
                         "趋势": {1: "上行", 0: "震荡", -1: "下行"}[x["trend"]], "倾向": x["bias"], "关注度": x["score"]}
                        for x in sorted(results, key=lambda y: (y["score"], abs(y["gap"])), reverse=True)])
    st.dataframe(tbl, use_container_width=True, hide_index=True)
    st.caption("关注度 = 缺口大小 + 昨日放量 + 趋势清晰 + 波动足够。ATR% 低于 2% 的股票日内空间小，会被扣分。")

    focus = sorted(results, key=lambda y: (y["score"], abs(y["gap"])), reverse=True)[:3]
    md.append("## 重点股")
    st.markdown(f"#### 🎯 今日重点股（最多 3 只，其余不碰）")
    for x in focus:
        adj_shares = int(x["shares"] * size_factor)
        with st.container(border=True):
            st.markdown(f"**{x['sym']}**　·　倾向 **{x['bias']}**　·　最新价 ${x['price']:.2f}　·　缺口 {x['gap']*100:+.2f}%")
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("昨高 / 昨低", f"${x['H']:.2f} / ${x['L']:.2f}")
            k2.metric("Pivot", f"${x['P']:.2f}")
            k3.metric("阻力 R1 / R2", f"${x['R1']:.2f} / ${x['R2']:.2f}")
            k4.metric("支撑 S1 / S2", f"${x['S1']:.2f} / ${x['S2']:.2f}")
            k5.metric("参考仓位", f"{adj_shares} 股" if adj_shares > 0 else "资金不足")
            R = x["stop_dist"]
            if x["bias"] == "偏多":
                plan_line = (f"**多头计划**：开盘区间（{T(9,30)}–{T(10,0)}）高点被放量突破且站稳 VWAP 时买入 → 止损放在区间低点或入场价下方约 ${R:.2f}；"
                             f"第一目标 +1.5R（约 +${1.5*R:.2f}），第二目标看 R1（${x['R1']:.2f}）。")
            elif x["bias"] == "偏空":
                plan_line = (f"**空头倾向**：开盘区间低点被放量跌破时才会走弱。做空需要保证金账户且有风险，"
                             f"**新手建议只观察或回避**；若持有该股，跌破 S1（${x['S1']:.2f}）要考虑减仓。")
            else:
                plan_line = "**观望**：方向不清晰，等开盘区间被明确突破后再决定，或者直接放弃这只。"
            st.markdown(plan_line)
            st.markdown(f"💡 {gap_advice(x)}")
            st.caption(f"参考仓位按『单笔风险 ${risk_usd:.0f} ÷ 止损距离 ${R:.2f}』计算并乘以今日仓位系数 {size_factor:.2f}，"
                       f"且不使用杠杆。实际入场价和止损位以开盘区间形成后的真实价格为准。")
        md.append(f"- {x['sym']}｜{x['bias']}｜现价 ${x['price']:.2f}｜缺口 {x['gap']*100:+.2f}%｜昨高 ${x['H']:.2f} 昨低 ${x['L']:.2f}｜"
                  f"Pivot ${x['P']:.2f} R1 ${x['R1']:.2f} S1 ${x['S1']:.2f}｜止损距离约 ${x['stop_dist']:.2f}｜参考 {adj_shares} 股")
    md.append("")

    # ---- 可勾选清单 ----
    def phase(title, items, key):
        st.markdown(f"### {title}")
        md.append(f"## {title}")
        for i, (tm, text) in enumerate(items):
            st.checkbox(f"**{tm}**　{text}", key=f"{key}_{i}")
            md.append(f"- [ ] {tm}　{text}")
        md.append("")

    st.subheader("✅ 执行清单（可勾选）")
    phase("🌅 盘前", [
        (T(8, 0), "确认今天不是休市日/提前收盘日；查看经济数据日历（CPI、非农、FOMC 等）和自选股是否有财报"),
        (T(8, 30), "看 SPY / QQQ 盘前方向和 VIX，确定今日仓位系数"),
        (T(9, 0), "浏览上面的重点股，只保留 ≤3 只；每只写下多头触发位、止损位、目标位"),
        (T(9, 15), f"按单笔风险 ${risk_usd:.0f} 算好每只的股数，预先设置好价格提醒"),
        (T(9, 25), "最后检查：资金、风险额度、只用限价单和止损单；关掉无关的社交媒体和新闻"),
    ], "pre")
    phase("🔔 开盘", [
        (f"{T(9, 30)} – {T(9, 35)}", "只看不做：开盘 5 分钟波动最大、买卖价差最宽"),
        (f"{T(9, 35)} – {T(10, 0)}", "记录重点股的开盘区间高点和低点，观察成交量和 VWAP 位置"),
        (T(10, 0), "区间被放量突破且站稳 VWAP，才按计划入场；入场后立刻挂好止损单"),
        (T(10, 0), "如果 30 分钟内没有出现清晰的设置，放弃当前这只，不要硬找机会"),
    ], "open")
    phase("⚙️ 盘中调整", [
        (f"{T(10, 0)} – {T(11, 30)}", "主要交易窗口：流动性好，优先在这里执行计划"),
        (f"{T(11, 30)} – {T(13, 30)}", "午间清淡、假突破多：减少交易，缩小仓位，或者干脆休息"),
        (f"{T(13, 30)} – {T(15, 0)}", "二次机会：观察趋势是否延续；盈利达到 +1R 后把止损上移到成本价"),
        ("全天", f"累计亏损达到 ${max_loss_usd:.0f} 立刻停手；连亏 2 笔停手 30 分钟；不给亏损单加仓、不移动止损"),
        ("全天", f"已开仓笔数达到 {max_trades} 笔就收工，把额度留给高质量设置"),
    ], "mid")
    phase("🌇 收盘处理", [
        (T(15, 0), "不再开新仓（除非设置极其清晰）；未达目标的持仓收紧止损"),
        (T(15, 45), "平掉所有日内仓位，不隔夜（除非你在计划里明确写了隔夜持有的理由）"),
        (f"{T(16, 0)} – {T(16, 30)}", "复盘：把每笔交易记进『交易日志分析器』；写下今天做对的一件事和最需要改的一件事"),
        (T(16, 30), "整理明日自选股和关键价位，为明天的盘前扫描做准备"),
    ], "close")

    st.download_button("⬇ 下载今日计划（文本，可打印/存手机）", "\n".join(md).encode("utf-8-sig"),
                       f"day_plan_{pd_date}.md", "text/markdown")
    st.caption("⚠️ 关键价位和倾向由日线数据机械计算，只是执行框架，不是买卖建议；盘前价格数据可能有延迟或缺失，请以你的券商行情为准。")
