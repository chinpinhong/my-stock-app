from datetime import datetime, timezone
from pathlib import Path
import sys

import streamlit as st

st.set_page_config(page_title="今日精选", page_icon="⭐", layout="wide")
st.title("⭐ 今日精选")
st.caption("打开页面自动扫描（结果缓存 5 分钟），不用去 GitHub 操作。仅供研究学习，不构成投资建议。")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    from scan import POOL, scan_pool, select_picks
    SCAN_AVAILABLE = True
except Exception as e:
    SCAN_AVAILABLE = False
    IMPORT_ERROR = str(e)


def fmt_age(iso_ts):
    try:
        t = datetime.fromisoformat(iso_ts)
        secs = int((datetime.now(timezone.utc) - t).total_seconds())
        if secs < 60:
            return "刚刚"
        if secs < 3600:
            return f"{secs // 60} 分钟前"
        return f"{secs // 3600} 小时前"
    except Exception:
        return "未知"


@st.cache_data(ttl=300, show_spinner="正在扫描股票池…")
def cached_scan():
    results = scan_pool(POOL)
    picks = select_picks(results)
    return picks, len(results), datetime.now(timezone.utc).isoformat()


def render_picks(picks):
    """用逐行文字而不是并排卡片，避免手机屏幕太窄时数字被截断看不清。"""
    for i, p in enumerate(picks, 1):
        rr = p.get("rr")
        risk = p["entry"] - p["stop"]
        gain = p["target"] - p["entry"]
        with st.container(border=True):
            st.markdown(f"#### #{i}　{p['symbol']}　·　评分 {p['score']:+d}")
            st.markdown(f"**现价 / 入场：** ${p['entry']:,.2f}")
            st.markdown(f"**止损：** ${p['stop']:,.2f}　（{(p['stop']/p['entry']-1)*100:+.1f}%，每股风险 ${risk:,.2f}）")
            st.markdown(f"**止盈：** ${p['target']:,.2f}　（{(p['target']/p['entry']-1)*100:+.1f}%，每股潜在收益 ${gain:,.2f}）")
            st.markdown(f"**风险回报比：** {f'{rr:.1f} : 1' if rr else '—'}　|　**日均波幅：** {p.get('atr_pct', 0):.1f}%")
            st.caption("仓位大小请按『单笔能接受的亏损金额 ÷ 每股风险』自己计算，或去『交易想法生成器』页面按账户资金自动算好股数。")


# ---------------- 主体：自动扫描 ----------------
if not SCAN_AVAILABLE:
    st.error(f"找不到 scan.py，无法扫描。请确认仓库根目录（不是 pages 文件夹）有这个文件。（错误信息：{IMPORT_ERROR}）")
    st.stop()

picks, scanned, ts = cached_scan()

top = st.columns([3, 1])
top[0].info(f"🕐 更新于 **{fmt_age(ts)}**　|　扫描了 {scanned} / {len(POOL)} 只股票")
if top[1].button("🔄 立即重新扫描"):
    cached_scan.clear()
    st.rerun()

if not picks:
    st.warning("这次扫描没有找到够格的设置。**没有好机会时不出手，本身就是一种策略。** 点上面的按钮可以立刻再试一次。")
else:
    st.subheader(f"🎯 今日精选（{len(picks)} 个）")
    render_picks(picks)

st.divider()
st.caption(
    "结果由固定规则（周线/日线趋势、MACD、RSI、支撑阻力）机械算出，打开页面时若缓存超过 5 分钟会自动重新扫描一次。"
    "止损止盈仅供参考，请务必自己核对当前价格，不构成投资建议。"
)
