from datetime import datetime, timezone
from pathlib import Path
import json
import sys

import streamlit as st

st.set_page_config(page_title="今日精选", page_icon="⭐", layout="wide")
st.title("⭐ 今日精选")
st.caption("默认显示后台每天自动更新的结果；想看现在最新情况，点下面的按钮立即重新扫描。仅供研究学习，不构成投资建议。")

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "latest_picks.json"

# 让页面能直接复用仓库根目录 scan.py 里的分析逻辑，两边只需要维护一份代码
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    from scan import POOL, scan_pool, select_picks
    LIVE_SCAN_AVAILABLE = True
except Exception:
    LIVE_SCAN_AVAILABLE = False


def fmt_age(iso_ts):
    try:
        t = datetime.fromisoformat(iso_ts)
        mins = int((datetime.now(timezone.utc) - t).total_seconds() / 60)
        if mins < 60:
            return f"{mins} 分钟前"
        if mins < 24 * 60:
            return f"{mins // 60} 小时前"
        return f"{mins // (24*60)} 天前"
    except Exception:
        return "未知"


def render_picks(picks):
    for i, p in enumerate(picks, 1):
        rr = p.get("rr")
        with st.container(border=True):
            st.markdown(f"### #{i}　{p['symbol']}　·　评分 {p['score']:+d}")
            a, b, c, e, f = st.columns(5)
            a.metric("现价 / 入场", f"${p['entry']:.2f}")
            b.metric("止损", f"${p['stop']:.2f}", f"{(p['stop']/p['entry']-1)*100:.1f}%", delta_color="off")
            c.metric("止盈", f"${p['target']:.2f}", f"+{(p['target']/p['entry']-1)*100:.1f}%", delta_color="off")
            e.metric("风险回报比", f"{rr:.1f} : 1" if rr else "—")
            f.metric("日均波幅", f"{p.get('atr_pct', 0):.1f}%")
            risk = p["entry"] - p["stop"]
            gain = p["target"] - p["entry"]
            st.caption(f"每股风险 ${risk:.2f}，每股潜在收益 ${gain:.2f}。仓位大小请按『单笔能接受的亏损金额 ÷ 每股风险』自己计算，"
                       "或去『交易想法生成器』页面按你的账户资金自动算好股数。")


# ---------------- ① 立即重新扫描 ----------------
st.subheader("🔄 立即重新扫描")
if not LIVE_SCAN_AVAILABLE:
    st.caption("暂时无法现场扫描（找不到 scan.py），请确认仓库根目录有这个文件。下面仍会显示后台的最新结果。")
else:
    st.caption(f"现场扫描股票池（{len(POOL)} 只：{', '.join(POOL)}），不用等后台的定时任务，几秒到十几秒出结果。")
    if st.button("▶ 立即扫描", type="primary"):
        bar = st.progress(0.0, text="准备中…")

        def cb(done, total, sym):
            bar.progress(done / total, text=f"正在分析 {sym}（{done}/{total}）")

        results = scan_pool(POOL, progress_cb=cb)
        bar.empty()
        live_picks = select_picks(results)
        st.session_state["live_picks"] = live_picks
        st.session_state["live_time"] = datetime.now(timezone.utc).isoformat()
        st.session_state["live_scanned"] = len(results)

    if "live_picks" in st.session_state:
        st.success(f"✅ 扫描完成：{fmt_age(st.session_state['live_time'])}　|　成功分析 {st.session_state['live_scanned']} / {len(POOL)} 只")
        if not st.session_state["live_picks"]:
            st.warning("这次现场扫描没有找到够格的设置。**没有好机会时不出手，本身就是一种策略。**")
        else:
            render_picks(st.session_state["live_picks"])

st.divider()

# ---------------- ② 后台自动更新的结果 ----------------
st.subheader("🌙 后台自动更新（每天约 3 次）")

if not DATA_PATH.exists():
    st.warning(
        "还没有生成过后台精选结果。请确认：\n"
        "1. 仓库里有 `scan.py` 和 `.github/workflows/scan.yml`；\n"
        "2. 去 GitHub 仓库的 **Actions** 标签页，点『每日自动选股』→ **Run workflow** 手动跑一次；\n"
        "3. 跑完后（约 1–2 分钟）刷新本页面。\n\n"
        "在这之前，你可以先用上面的『立即扫描』按钮看结果。"
    )
else:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    picks = data.get("picks", [])
    st.info(f"🕐 最后更新：**{fmt_age(data.get('updated_at', ''))}**　|　本次扫描了 {data.get('scanned', 0)} / {data.get('pool_size', 0)} 只股票")
    if not picks:
        st.warning("后台最近一次扫描没有找到够格的设置。可以用上面的按钮现场再试一次。")
    else:
        render_picks(picks)

st.caption(
    "结果由固定规则（周线/日线趋势、MACD、RSI、支撑阻力）机械算出。"
    "止损止盈仅供参考，请务必自己核对当前价格，不构成投资建议。"
)
