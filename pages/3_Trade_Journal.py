import math
from datetime import timedelta

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="交易日志分析器", page_icon="📒", layout="wide")
st.title("📒 交易日志分析器")
st.caption("录入你的历史交易，自动找出重复犯的错误、行为偏差，并给出 3 条最该马上执行的规则。仅供复盘学习，不构成投资建议。")

COLS = ["入场日期", "出场日期", "代码", "方向", "入场价", "出场价", "股数"]

# ---------------- 示例数据（请替换为你自己的交易） ----------------
sample = pd.DataFrame([
    ["2026-07-01", "2026-07-03", "NVDA", "做多", 120.0, 126.0, 20],
    ["2026-07-06", "2026-07-16", "TSLA", "做多", 250.0, 232.0, 10],
    ["2026-07-07", "2026-07-08", "AMD", "做多", 150.0, 155.0, 15],
    ["2026-07-17", "2026-07-30", "TSLA", "做多", 230.0, 214.0, 20],
    ["2026-07-20", "2026-07-21", "AAPL", "做多", 210.0, 214.0, 10],
    ["2026-07-31", "2026-08-12", "TSLA", "做多", 212.0, 198.0, 25],
    ["2026-08-03", "2026-08-04", "MSFT", "做多", 430.0, 438.0, 5],
    ["2026-08-05", "2026-08-06", "NVDA", "做多", 128.0, 133.0, 20],
    ["2026-08-13", "2026-08-14", "AMD", "做多", 160.0, 151.0, 15],
    ["2026-08-14", "2026-08-25", "META", "做多", 520.0, 490.0, 5],
    ["2026-08-18", "2026-08-19", "AAPL", "做多", 215.0, 219.0, 10],
    ["2026-08-26", "2026-08-27", "NVDA", "做多", 135.0, 141.0, 20],
], columns=COLS)

st.subheader("1️⃣ 录入交易记录")
st.write("下面是**示例数据**，直接点分析可以先体验。要分析自己的交易：删掉示例，手动填，或上传 CSV（列名需与下表一致）。日期格式：`2026-08-03`。")

up = st.file_uploader("上传 CSV（可选）", type=["csv"])
template_csv = sample.to_csv(index=False).encode("utf-8-sig")
st.download_button("⬇ 下载 CSV 模板", template_csv, "trade_template.csv", "text/csv")

if up is not None:
    try:
        base = pd.read_csv(up)
        missing = [c for c in COLS if c not in base.columns]
        if missing:
            st.error(f"CSV 缺少这些列：{', '.join(missing)}")
            base = sample
        else:
            base = base[COLS]
    except Exception:
        st.error("CSV 读取失败，请检查文件格式。")
        base = sample
else:
    base = sample

edited = st.data_editor(base, num_rows="dynamic", use_container_width=True)
c1, c2 = st.columns(2)
capital = c1.number_input("账户总资金 ($)", 100.0, 10_000_000.0, 5000.0, step=100.0)
check_missed = c2.checkbox("同时检查『错失机会』（会联网取价，较慢）", value=False)


# ---------------- 数据处理 ----------------
def clean(df):
    d = df.copy()
    d["入场日期"] = pd.to_datetime(d["入场日期"], errors="coerce")
    d["出场日期"] = pd.to_datetime(d["出场日期"], errors="coerce")
    for c in ["入场价", "出场价", "股数"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["代码"] = d["代码"].astype(str).str.upper().str.strip()
    d = d.dropna(subset=["入场日期", "出场日期", "入场价", "出场价", "股数"])
    d = d[d["股数"] > 0]
    sign = np.where(d["方向"].astype(str).str.contains("空"), -1, 1)
    d["sign"] = sign
    d["pnl"] = (d["出场价"] - d["入场价"]) * d["股数"] * sign
    d["pnl_pct"] = (d["出场价"] / d["入场价"] - 1) * 100 * sign
    d["notional"] = d["入场价"] * d["股数"]
    d["hold"] = (d["出场日期"] - d["入场日期"]).dt.days
    return d.sort_values("入场日期").reset_index(drop=True)


@st.cache_data(ttl=3600)
def continuation_after_exit(sym, exit_date, exit_price):
    """卖出后 5 个交易日，价格又涨/跌了多少（%）。取不到返回 None。"""
    try:
        end = pd.Timestamp(exit_date) + timedelta(days=15)
        h = yf.Ticker(sym).history(start=str(pd.Timestamp(exit_date).date()), end=str(end.date()))["Close"]
        if len(h) < 3:
            return None
        return (float(h.iloc[min(5, len(h) - 1)]) / exit_price - 1) * 100
    except Exception:
        return None


def max_streak(mask):
    best = cur = 0
    for v in mask:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def analyze(d, cap, do_missed):
    wins, losses = d[d["pnl"] > 0], d[d["pnl"] <= 0]
    n = len(d)
    win_rate = len(wins) / n
    avg_win = wins["pnl"].mean() if len(wins) else 0.0
    avg_loss = abs(losses["pnl"].mean()) if len(losses) else 0.0
    payoff = avg_win / avg_loss if avg_loss > 0 else np.nan
    pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) and losses["pnl"].sum() != 0 else np.nan
    stats = {
        "交易笔数": n, "胜率": win_rate, "平均盈利": avg_win, "平均亏损": avg_loss,
        "盈亏比": payoff, "利润因子": pf, "每笔期望": d["pnl"].mean(), "总盈亏": d["pnl"].sum(),
        "最大连亏": max_streak((d["pnl"] <= 0).tolist()),
    }
    issues = []  # (严重度, 标题, 说明, 规则)

    # 1. 盈亏比与保本胜率
    if avg_loss > 0 and avg_win > 0:
        be = 1 / (1 + payoff)
        if win_rate < be:
            issues.append((70 + min(25, (be - win_rate) * 100), "盈亏比太差，赢得少亏得多",
                           f"平均盈利 ${avg_win:.0f}，平均亏损 ${avg_loss:.0f}（盈亏比 {payoff:.2f}）。在这个盈亏比下保本胜率需要 {be*100:.0f}%，但你的胜率只有 {win_rate*100:.0f}%。",
                           f"每笔交易入场前必须写下止损价，并保证『单笔最大亏损 ≤ ${avg_win:.0f}』（你的平均盈利），做不到就不进场。"))
    # 2. 亏损单拿得更久（处置效应）
    if len(wins) >= 2 and len(losses) >= 2:
        hw, hl = wins["hold"].mean(), losses["hold"].mean()
        if hw >= 0 and hl > max(hw * 1.3, hw + 1):
            limit = max(1, math.ceil(hw * 1.5))
            issues.append((55 + min(30, hl - hw), "亏损单拿得比盈利单久",
                           f"盈利单平均持有 {hw:.1f} 天，亏损单平均持有 {hl:.1f} 天。这是典型的『不愿认亏、死扛』倾向。",
                           f"亏损单持有超过 {limit} 天且仍未回到成本，就无条件离场或减半，不再找新的理由继续拿。"))
    # 3. 亏损后加大仓位
    prev_loss = (d["pnl"].shift(1) <= 0)
    after_loss, after_win = d[prev_loss & d["pnl"].shift(1).notna()], d[(~prev_loss) & d["pnl"].shift(1).notna()]
    if len(after_loss) >= 2 and len(after_win) >= 2 and after_loss["notional"].mean() > after_win["notional"].mean() * 1.3:
        r = after_loss["notional"].mean() / after_win["notional"].mean()
        issues.append((60, "亏损后加大仓位（想赢回来）",
                       f"亏损后的下一笔，平均仓位是赢钱后的 {r:.1f} 倍。",
                       "亏损之后的下一笔交易，仓位不得大于最近 5 笔的平均仓位；连亏 2 笔后当天不再开新仓。"))
    # 4. 亏损后急着再入场
    gap = (d["入场日期"] - d["出场日期"].shift(1)).dt.days
    quick = d[prev_loss & (gap <= 1)]
    if len(quick) >= 3 and (quick["pnl"] > 0).mean() < win_rate - 0.15:
        issues.append((50, "亏损后急着马上再开一单",
                       f"亏损后 1 天内再入场的 {len(quick)} 笔，胜率只有 {(quick['pnl']>0).mean()*100:.0f}%（你的整体胜率 {win_rate*100:.0f}%）。",
                       "每次亏损后强制冷静：至少隔一个交易日才允许开下一单，期间只做复盘，不看盘下单。"))
    # 5. 一天交易太多
    per_day = d.groupby(d["入场日期"].dt.date)["pnl"].agg(["count", "mean"])
    busy = per_day[per_day["count"] >= 3]
    if len(busy) >= 1 and busy["mean"].mean() < 0:
        issues.append((45, "单日交易过多，越做越亏",
                       f"有 {len(busy)} 天开了 3 笔以上，这些日子平均每笔亏 ${abs(busy['mean'].mean()):.0f}。",
                       "每日最多开 2 笔新仓，用完额度当天不再交易。"))
    # 6. 同一只票反复亏
    by_sym = d.groupby("代码")["pnl"].agg(["sum", "count"])
    bad = by_sym[(by_sym["sum"] < 0) & (by_sym["count"] >= 3)].sort_values("sum")
    if len(bad):
        s = bad.index[0]
        issues.append((40 + min(30, abs(bad.iloc[0]["sum"]) / max(cap, 1) * 100), f"在 {s} 上反复亏损",
                       f"{s} 交易了 {int(bad.iloc[0]['count'])} 次，累计亏损 ${abs(bad.iloc[0]['sum']):.0f}。可能是你并不真正了解它的节奏，或者在赌『这次会回来』。",
                       f"同一只股票连续亏损 2 次后，冷却 2 周不碰；想再做必须写出与上次不同的入场理由。"))
    # 7. 单笔大亏
    if len(losses) >= 3 and abs(losses["pnl"].min()) > 2.5 * avg_loss:
        issues.append((55, "偶尔一笔大亏吃掉很多小赚",
                       f"最大单笔亏损 ${abs(losses['pnl'].min()):.0f}，是平均亏损的 {abs(losses['pnl'].min())/avg_loss:.1f} 倍。",
                       f"设定单笔亏损硬上限：不超过账户的 2%（${cap*0.02:.0f}），到价必须执行，不移动止损。"))
    # 8. 单笔风险占比过高
    worst_pct = abs(losses["pnl"].min()) / cap * 100 if len(losses) else 0
    if worst_pct > 5:
        issues.append((50 + min(30, worst_pct), "单笔亏损占账户比例过高",
                       f"你最大的一笔亏损占账户 {worst_pct:.1f}%。连续遇到几次就会伤到本金。",
                       f"每笔交易风险 ≤ 账户的 2%（${cap*0.02:.0f}）：仓位 =（${cap*0.02:.0f}）÷（入场价 − 止损价）。"))
    # 9. 连亏
    if stats["最大连亏"] >= 4:
        issues.append((35 + stats["最大连亏"], f"出现过连亏 {stats['最大连亏']} 笔",
                       "连亏时情绪最容易失控，后面的交易往往更差。",
                       "连亏 3 笔后，停止交易 1 天并写复盘；恢复后仓位减半，直到出现一笔盈利。"))
    # 10. 错失机会（可选）
    missed_info = None
    if do_missed:
        conts = []
        for _, r in wins[wins["sign"] == 1].tail(20).iterrows():
            v = continuation_after_exit(r["代码"], r["出场日期"], float(r["出场价"]))
            if v is not None:
                conts.append(v)
        if conts:
            missed_info = (float(np.mean(conts)), len(conts), sum(1 for v in conts if v > 5))
            if missed_info[0] > 3:
                issues.append((45, "盈利单卖得太早",
                               f"检查了 {missed_info[1]} 笔盈利的做多单，卖出后 5 个交易日平均又涨了 {missed_info[0]:.1f}%，其中 {missed_info[2]} 笔又涨超 5%。",
                               "盈利单改为『分批止盈』：先卖一半，剩下一半用移动止损（如跌破 10 日均线）跟踪，不再一次性全卖。"))
    issues.sort(key=lambda x: -x[0])
    return stats, issues, missed_info


# ---------------- 分析 ----------------
if st.button("🔍 开始分析", type="primary"):
    d = clean(edited)
    if len(d) < 5:
        st.warning("有效交易不足 5 笔，无法分析。请检查日期和数字格式（日期示例：2026-08-03）。")
        st.stop()
    if len(d) < 20:
        st.info(f"目前只有 {len(d)} 笔交易，样本偏少，结论仅供参考，建议积累到 20 笔以上。")

    stats, issues, missed = analyze(d, capital, check_missed)

    st.subheader("2️⃣ 基本成绩单")
    a, b, c, e, f = st.columns(5)
    a.metric("交易笔数", stats["交易笔数"])
    b.metric("胜率", f"{stats['胜率']*100:.0f}%")
    c.metric("盈亏比", "—" if np.isnan(stats["盈亏比"]) else f"{stats['盈亏比']:.2f}")
    e.metric("利润因子", "—" if np.isnan(stats["利润因子"]) else f"{stats['利润因子']:.2f}")
    f.metric("总盈亏", f"${stats['总盈亏']:+,.0f}")
    g, h, i = st.columns(3)
    g.metric("平均盈利 / 平均亏损", f"${stats['平均盈利']:.0f} / ${stats['平均亏损']:.0f}")
    h.metric("每笔期望盈亏", f"${stats['每笔期望']:+.1f}")
    i.metric("最大连亏", f"{stats['最大连亏']} 笔")
    st.line_chart(d.set_index("出场日期")["pnl"].cumsum().rename("累计盈亏($)"))

    st.subheader("3️⃣ 发现的问题（按严重程度排序）")
    if not issues:
        st.success("没有检测到明显的重复错误。样本量小时，请继续积累记录。")
    for sev, title, detail, _ in issues:
        st.markdown(f"**⚠️ {title}**  \n{detail}")

    if check_missed and missed is None:
        st.caption("『错失机会』检查没取到足够的价格数据，已跳过。")

    st.subheader("4️⃣ 你最该马上执行的 3 条规则")
    rules = [r for _, _, _, r in issues[:3]]
    generic = [
        f"每笔交易入场前，必须写下：入场理由、止损价、目标价。事后对照，不写不下单。",
        f"单笔风险不超过账户的 2%（${capital*0.02:.0f}）。",
        "每周日固定 20 分钟复盘本周所有交易，找出一个可以改进的点。",
    ]
    for g_rule in generic:
        if len(rules) >= 3:
            break
        rules.append(g_rule)
    for idx, rule in enumerate(rules, 1):
        st.success(f"**规则 {idx}：** {rule}")

    with st.expander("📋 交易明细"):
        show = d[["入场日期", "出场日期", "代码", "方向", "入场价", "出场价", "股数", "pnl", "pnl_pct", "hold"]].copy()
        show.columns = ["入场日期", "出场日期", "代码", "方向", "入场价", "出场价", "股数", "盈亏($)", "盈亏(%)", "持仓天数"]
        show["入场日期"] = show["入场日期"].dt.date
        show["出场日期"] = show["出场日期"].dt.date
        st.dataframe(show.round(2), use_container_width=True, hide_index=True)

    st.caption("⚠️ 这些结论是从你的记录里按规则统计出来的，样本越多越可靠。它不能替代你自己的判断，也不构成投资建议。")
