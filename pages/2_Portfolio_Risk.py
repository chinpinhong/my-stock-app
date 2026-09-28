import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="投资组合风险管理器", page_icon="🛡️", layout="wide")
st.title("🛡️ 投资组合风险管理器")
st.caption("检查你的持仓是否过度集中、是否藏着高相关性，并估算大盘下跌时你会亏多少。仅供研究学习，不构成投资建议。")

# ---------------- 输入区 ----------------
st.subheader("1️⃣ 输入你的持仓")
st.write("在表格里改代码和仓位比例（%），点表格最下面的空行可以新增一行。")

default_df = pd.DataFrame({
    "代码": ["NVDA", "AAPL", "TSLA", "MSFT", "AMD"],
    "仓位比例(%)": [30.0, 25.0, 20.0, 15.0, 10.0],
})
edited = st.data_editor(default_df, num_rows="dynamic", use_container_width=True)

c1, c2, c3 = st.columns(3)
capital = c1.number_input("总资金 ($)", 100.0, 10_000_000.0, 5000.0, step=100.0)
crash_pct = c2.slider("模拟大盘下跌幅度 (%)", 5, 50, 20)
max_w_pct = c3.slider("单只股票仓位上限 (%)", 10, 50, 25)


# ---------------- 数据函数 ----------------
@st.cache_data(ttl=600)
def load_close(sym):
    try:
        h = yf.Ticker(sym).history(period="1y")
        return h["Close"] if not h.empty else pd.Series(dtype=float)
    except Exception:
        return pd.Series(dtype=float)


@st.cache_data(ttl=3600)
def get_sector(sym):
    try:
        return yf.Ticker(sym).info.get("sector") or "未知/ETF"
    except Exception:
        return "未知/ETF"


def cap_weights(w, cap):
    """把超过上限的仓位砍到上限，多出来的按比例分给其他股票。"""
    w = w.copy()
    cap = max(cap, 1.0 / len(w))
    for _ in range(20):
        over = w > cap
        if not over.any():
            break
        excess = (w[over] - cap).sum()
        w[over] = cap
        under = ~over
        if w[under].sum() <= 0:
            break
        w[under] += excess * w[under] / w[under].sum()
    return w


# ---------------- 分析 ----------------
if st.button("🔍 开始分析", type="primary"):
    df = edited.copy()
    df["代码"] = df["代码"].astype(str).str.upper().str.strip()
    df["仓位比例(%)"] = pd.to_numeric(df["仓位比例(%)"], errors="coerce")
    df = df[(df["代码"] != "") & (df["代码"] != "NAN") & (df["仓位比例(%)"] > 0)]
    df = df.groupby("代码", as_index=False)["仓位比例(%)"].sum()

    if len(df) < 2:
        st.warning("至少需要 2 只有效的股票才能分析。")
        st.stop()

    closes, failed = {}, []
    for s in df["代码"]:
        c = load_close(s)
        if len(c) > 60:
            closes[s] = c
        else:
            failed.append(s)
    spy = load_close("SPY")
    if failed:
        st.warning(f"以下代码没取到足够数据，已排除：{', '.join(failed)}")
    if len(closes) < 2 or len(spy) < 60:
        st.error("有效数据不足，请检查代码后重试。")
        st.stop()

    prices = pd.DataFrame(closes)
    prices["SPY"] = spy
    rets = prices.pct_change().dropna()
    syms = [s for s in closes]
    w = df.set_index("代码").loc[syms, "仓位比例(%)"]
    w = w / w.sum()  # 归一化为 100%

    # ---- 核心指标 ----
    spy_var = rets["SPY"].var()
    betas = pd.Series({s: rets[s].cov(rets["SPY"]) / spy_var for s in syms})
    port_ret = (rets[syms] * w).sum(axis=1)
    port_beta = float((w * betas).sum())
    ann_vol = port_ret.std() * np.sqrt(252)
    equity = (1 + port_ret).cumprod()
    max_dd = (equity / equity.cummax() - 1).min()
    corr = rets[syms].corr()
    pair_corrs = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool)).stack().dropna()
    avg_corr = float(pair_corrs.mean())
    eff_n = 1 / float((w ** 2).sum())
    sectors = pd.Series({s: get_sector(s) for s in syms})
    sector_w = w.groupby(sectors).sum().sort_values(ascending=False)

    st.subheader("2️⃣ 体检结果")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("组合 Beta", f"{port_beta:.2f}", help="相对大盘的敏感度：1.5 表示大盘跌 10%，你大约跌 15%")
    m2.metric("年化波动率", f"{ann_vol*100:.0f}%")
    m3.metric("过去一年最大回撤", f"{max_dd*100:.0f}%")
    m4.metric("平均相关性", f"{avg_corr:.2f}", help="越接近 1，说明你的股票越是'一起涨一起跌'")
    m5.metric("等效持仓数", f"{eff_n:.1f}", help=f"你持有 {len(syms)} 只，但仓位分布相当于只有这么多只")

    # ---- 风险警告 ----
    flags = []
    top = w.sort_values(ascending=False)
    if top.iloc[0] > max_w_pct / 100:
        flags.append(f"🔴 **单股集中**：{top.index[0]} 占 {top.iloc[0]*100:.0f}%，超过你设的 {max_w_pct}% 上限。")
    if top.iloc[:2].sum() > 0.5:
        flags.append(f"🟠 **前两大仓位**（{top.index[0]}、{top.index[1]}）合计占 {top.iloc[:2].sum()*100:.0f}%。")
    if sector_w.iloc[0] > 0.5 and sector_w.index[0] != "未知/ETF":
        flags.append(f"🔴 **行业集中**：{sector_w.index[0]} 板块占 {sector_w.iloc[0]*100:.0f}%，行业出事会一起受伤。")
    if avg_corr > 0.6:
        flags.append(f"🟠 **隐藏相关性**：平均相关性 {avg_corr:.2f}，看似分散，其实很像同一笔投资。")
    if port_beta > 1.2:
        flags.append(f"🟠 **高 Beta**：组合 Beta {port_beta:.2f}，下跌时会比大盘跌得更狠。")
    if not flags:
        flags.append("🟢 没有发现明显的集中或相关性问题（仍不代表没有风险）。")
    for f in flags:
        st.markdown(f)

    high_pairs = pair_corrs[pair_corrs > 0.75].sort_values(ascending=False)
    if len(high_pairs):
        st.write("**相关性偏高的组合（>0.75）：**")
        for (a, b), v in high_pairs.items():
            st.write(f"- {a} 与 {b}：{v:.2f}")

    l, r = st.columns(2)
    with l:
        st.write("**相关性矩阵**（越接近 1 越同涨同跌）")
        st.dataframe(corr.round(2), use_container_width=True)
    with r:
        st.write("**行业分布**")
        st.dataframe((sector_w * 100).round(1).rename("占比(%)").to_frame(), use_container_width=True)

    # ---- 大盘下跌模拟 ----
    st.subheader(f"3️⃣ 如果大盘下跌 {crash_pct}%")
    loss_pct = betas * (-crash_pct)
    loss_usd = loss_pct / 100 * w * capital
    sim = pd.DataFrame({
        "仓位(%)": (w * 100).round(1),
        "Beta": betas.round(2),
        "预计跌幅(%)": loss_pct.round(1),
        "预计亏损($)": loss_usd.round(0),
    })
    st.dataframe(sim, use_container_width=True)
    total_loss = float(loss_usd.sum())
    st.error(f"组合预计亏损约 **${abs(total_loss):,.0f}**（{port_beta * crash_pct:.1f}% of 总资金）")
    st.bar_chart(-loss_usd)
    st.caption("这是用 Beta 做的粗略估算。真实的暴跌里，个股往往跌得比 Beta 显示的更多，因为大家会一起被抛售。请把它当成'最低预期'。")

    # ---- 再平衡与对冲建议 ----
    st.subheader("4️⃣ 再平衡与对冲建议")
    new_w = cap_weights(w, max_w_pct / 100)
    reb = pd.DataFrame({
        "当前(%)": (w * 100).round(1),
        "建议(%)": (new_w * 100).round(1),
        "调整(%)": ((new_w - w) * 100).round(1),
    })
    st.write(f"**① 仓位再平衡**（把单股封顶在 {max_w_pct}%，多出的按比例分给其他股票）")
    st.dataframe(reb, use_container_width=True)
    st.caption("只是按比例分配的机械方案。真正增持哪只，还要看你自己的判断，最好增持相关性低的标的。")

    target_loss = st.slider("你能接受的最大亏损 (%)（在这次下跌模拟中）", 3, 30, 10)
    st.write("**② 降低风险的方式**")
    need_beta = target_loss / crash_pct
    if port_beta > need_beta:
        cash_frac = 1 - need_beta / port_beta
        hedge_usd = (port_beta - need_beta) * capital
        st.markdown(
            f"- **持有现金**：把约 **{cash_frac*100:.0f}%**（${cash_frac*capital:,.0f}）的仓位换成现金，"
            f"大盘跌 {crash_pct}% 时亏损可降到约 {target_loss}%。\n"
            f"- **对冲**：做空或买入约 **${hedge_usd:,.0f}** 名义金额的 SPY 看跌期权（或反向 ETF），"
            f"效果类似，但期权有成本、且需要账户权限，新手要先了解清楚。\n"
            f"- **换防御性资产**：把部分高 Beta 股票换成低 Beta 板块（如必需消费、公用事业、医疗），"
            f"目标是把组合 Beta 降到 {need_beta:.2f} 左右。"
        )
    else:
        st.success(f"你当前的组合 Beta（{port_beta:.2f}）已经低于目标（{need_beta:.2f}），在这次模拟下亏损可控制在 {target_loss}% 以内。")

    st.caption("⚠️ 以上都是基于过去一年数据的统计估算，未来的相关性和 Beta 会变化，不构成投资建议。")
