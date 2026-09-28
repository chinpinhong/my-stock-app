import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="策略回测器", page_icon="🧪", layout="wide")
st.title("🧪 策略回测器")
st.caption("用历史数据检验一个策略过去表现如何。回测好看不代表未来赚钱，仅供研究学习，不构成投资建议。")

# ---------------- 输入区 ----------------
c1, c2, c3 = st.columns(3)
symbol = c1.text_input("股票/ETF 代码", value="AAPL").upper().strip()
years = c2.selectbox("回测时长（年）", [1, 2, 3, 5, 10], index=2)
strategy = c3.selectbox("策略", ["均线交叉（快线上穿慢线买入）", "RSI 超卖反弹"])

p1, p2, p3 = st.columns(3)
if strategy.startswith("均线"):
    fast = p1.number_input("快线天数", 5, 100, 20)
    slow = p2.number_input("慢线天数", 10, 300, 50)
else:
    rsi_buy = p1.number_input("RSI 低于此值买入", 10, 50, 30)
    rsi_sell = p2.number_input("RSI 高于此值卖出", 50, 90, 60)
fee_pct = p3.number_input("单边交易成本 (%)", 0.0, 1.0, 0.05, step=0.01)


# ---------------- 数据与策略 ----------------
@st.cache_data(ttl=600)
def load_prices(sym, yrs):
    df = yf.Ticker(sym).history(period=f"{yrs}y")
    return df["Close"].dropna() if not df.empty else pd.Series(dtype=float)


def calc_rsi(close, n=14):
    d = close.diff()
    gain = d.clip(lower=0).rolling(n).mean()
    loss = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + gain / loss)


def make_position(close):
    """返回每天收盘后的目标仓位：1=持有，0=空仓"""
    if strategy.startswith("均线"):
        return (close.rolling(int(fast)).mean() > close.rolling(int(slow)).mean()).astype(int)
    rsi = calc_rsi(close)
    pos, holding = [], 0
    for v in rsi:
        if np.isnan(v):
            pos.append(0)
            continue
        if holding == 0 and v < rsi_buy:
            holding = 1
        elif holding == 1 and v > rsi_sell:
            holding = 0
        pos.append(holding)
    return pd.Series(pos, index=close.index)


def run_backtest(close):
    ret = close.pct_change().fillna(0)
    held = make_position(close).shift(1).fillna(0)  # 今天收盘出信号，明天才持有，避免"偷看未来"
    cost = held.diff().abs().fillna(0) * fee_pct / 100
    strat_ret = held * ret - cost
    return ret, held, strat_ret


def metrics(strat_ret, held):
    equity = (1 + strat_ret).cumprod()
    total = equity.iloc[-1] - 1
    max_dd = (equity / equity.cummax() - 1).min()
    trade_id = (held.diff() == 1).cumsum()
    trade_rets = (1 + strat_ret[held == 1]).groupby(trade_id[held == 1]).prod() - 1
    n = len(trade_rets)
    wins, losses = trade_rets[trade_rets > 0], trade_rets[trade_rets <= 0]
    win_rate = len(wins) / n if n else np.nan
    pf = wins.sum() / abs(losses.sum()) if len(losses) and losses.sum() != 0 else np.nan
    return {"总收益": total, "最大回撤": max_dd, "交易次数": n, "胜率": win_rate, "利润因子": pf}


def show(m):
    a, b, c, d, e = st.columns(5)
    a.metric("总收益", f"{m['总收益']*100:.1f}%")
    b.metric("最大回撤", f"{m['最大回撤']*100:.1f}%")
    c.metric("交易次数", m["交易次数"])
    d.metric("胜率", "—" if np.isnan(m["胜率"]) else f"{m['胜率']*100:.0f}%")
    e.metric("利润因子", "—" if np.isnan(m["利润因子"]) else f"{m['利润因子']:.2f}")


# ---------------- 运行 ----------------
if st.button("▶ 开始回测", type="primary"):
    close = load_prices(symbol, years)
    if len(close) < 100:
        st.warning("没取到足够的数据，请检查代码是否正确，或稍后重试。")
        st.stop()

    ret, held, strat_ret = run_backtest(close)
    bh_total = (1 + ret).prod() - 1
    bh_dd = ((1 + ret).cumprod() / (1 + ret).cumprod().cummax() - 1).min()

    st.subheader("📊 整体结果")
    show(metrics(strat_ret, held))
    st.caption(f"对比：同期一直持有不动，总收益 {bh_total*100:.1f}%，最大回撤 {bh_dd*100:.1f}%。")

    curve = pd.DataFrame({"策略": (1 + strat_ret).cumprod(), "一直持有": (1 + ret).cumprod()})
    st.line_chart(curve)

    # 样本内 / 样本外：前 70% 当"调参用的数据"，后 30% 当"没见过的数据"
    cut = int(len(close) * 0.7)
    st.subheader("🔍 样本内 vs 样本外（检验是否过拟合）")
    st.caption("如果前 70% 很好、后 30% 很差，说明这个策略可能只是碰巧适合过去。")
    l, r = st.columns(2)
    with l:
        st.write("**前 70%（样本内）**")
        show(metrics(strat_ret.iloc[:cut], held.iloc[:cut]))
    with r:
        st.write("**后 30%（样本外）**")
        show(metrics(strat_ret.iloc[cut:], held.iloc[cut:]))

    with st.expander("📖 名词解释"):
        st.markdown(
            "- **胜率**：赚钱的交易占全部交易的比例。\n"
            "- **利润因子**：总盈利 ÷ 总亏损，大于 1 才算整体赚钱，1.5 以上算不错。\n"
            "- **最大回撤**：从最高点到之后最低点的最大跌幅，代表你最可能要忍受的痛。\n"
            "- 信号在当天收盘产生，次日才计入持仓，已扣除你设置的交易成本。"
        )
