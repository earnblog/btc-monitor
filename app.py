"""
MACD监控网页仪表盘
读取 data/signals.json 显示最新信号
"""
import streamlit as st
import json
import os
from datetime import datetime

st.set_page_config(
    page_title="MACD信号监控",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── 样式 ──────────────────────────────────────────────────────
st.markdown("""
<style>
.signal-card {
    background: #1a1a2e;
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 8px;
    border-left: 4px solid #444;
}
.signal-short { border-left-color: #ff4444; }
.signal-long  { border-left-color: #44ff88; }
.signal-wait  { border-left-color: #ffaa00; }
.signal-hp    { border-left-color: #aa44ff; }
.ratio-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: bold;
    margin: 0 2px;
}
.ratio-high { background: #ff4444; color: white; }
.ratio-mid  { background: #ff8800; color: white; }
.ratio-low  { background: #444; color: #aaa; }
.ratio-long-high { background: #44aa44; color: white; }
.ratio-long-mid  { background: #228822; color: white; }
</style>
""", unsafe_allow_html=True)


# ── 加载数据 ──────────────────────────────────────────────────
DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'signals.json')

@st.cache_data(ttl=60)
def load_signals():
    if not os.path.exists(DATA_FILE):
        return None
    try:
        with open(DATA_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def get_ratio_badge(ratio):
    """生成倍数徽章HTML"""
    abs_r = abs(ratio)
    direction = "上方" if ratio > 0 else "下方"
    if ratio > 0:
        cls = "ratio-high" if abs_r >= 3 else ("ratio-mid" if abs_r >= 2 else "ratio-low")
    else:
        cls = "ratio-long-high" if abs_r >= 3 else ("ratio-long-mid" if abs_r >= 2 else "ratio-low")
    icon = "🔥" if abs_r >= 3 else ("⚡" if abs_r >= 2 else "")
    return f'<span class="ratio-badge {cls}">{icon}{direction}{abs_r:.1f}x</span>'


def get_conclusion_color(conclusion):
    if '强烈建议做空' in conclusion or ('做空' in conclusion and '强烈' in conclusion):
        return 'signal-short'
    if '建议做空' in conclusion:
        return 'signal-short'
    if '强烈建议做多' in conclusion or ('做多' in conclusion and '强烈' in conclusion):
        return 'signal-long'
    if '建议做多' in conclusion:
        return 'signal-long'
    if '高概率' in conclusion:
        return 'signal-hp'
    return 'signal-wait'


# ── 页面标题 ──────────────────────────────────────────────────
st.title("📊 K线动能 · MACD信号监控")
st.caption("基于K线动能理论 · OKX永续合约 · 自动刷新")

# 自动刷新按钮
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    st.markdown("**监控周期：** 5m / 15m / 30m / 1h / 2h / 4h")
with col2:
    if st.button("🔄 手动刷新"):
        st.cache_data.clear()
        st.rerun()
with col3:
    auto_refresh = st.toggle("自动刷新(60s)", value=False)

if auto_refresh:
    import time
    time.sleep(60)
    st.rerun()

# 加载数据
data = load_signals()

if data is None:
    st.warning("暂无数据，GitHub Actions 每5分钟更新一次，请稍后刷新")
    st.info("如果刚部署完，第一次数据需要等5分钟生成")
    st.stop()

# 显示更新时间
updated_at = data.get('updated_at', '')
if updated_at:
    try:
        dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
        st.success(f"✅ 数据更新时间：{dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    except Exception:
        st.success(f"✅ 最后更新：{updated_at}")

symbols_data = data.get('symbols', {})
st.markdown(f"**监控币种数：** {len(symbols_data)} 个（交易量>1亿USDT）")

# ── 过滤控制 ──────────────────────────────────────────────────
st.markdown("---")
filter_col1, filter_col2, filter_col3 = st.columns(3)

with filter_col1:
    min_ratio = st.slider("最小MACD倍数", 1.0, 5.0, 2.0, 0.5,
                          help="只显示至少有一个周期达到此倍数的币种")
with filter_col2:
    direction_filter = st.selectbox("方向过滤",
                                     ["全部", "看空信号", "看多信号", "高概率信号", "等待信号"])
with filter_col3:
    sort_by = st.selectbox("排序方式", ["最大倍数", "交易量", "信号强度"])

# ── 统计概览 ──────────────────────────────────────────────────
short_count  = sum(1 for v in symbols_data.values() if '做空' in v.get('conclusion',''))
long_count   = sum(1 for v in symbols_data.values() if '做多' in v.get('conclusion',''))
hp_count     = sum(1 for v in symbols_data.values() if '高概率' in v.get('conclusion',''))
wait_count   = sum(1 for v in symbols_data.values() if '等待' in v.get('conclusion','') or '观察' in v.get('conclusion',''))

m1, m2, m3, m4 = st.columns(4)
m1.metric("🔴 做空信号", short_count)
m2.metric("🟢 做多信号", long_count)
m3.metric("🎯 高概率", hp_count)
m4.metric("⏳ 等待观察", wait_count)

st.markdown("---")

# ── 主信号列表 ──────────────────────────────────────────────────
TF_ORDER = ['5m', '15m', '30m', '1h', '2h', '4h']
TF_NAMES = {
    '5m':'5分', '15m':'15分', '30m':'30分',
    '1h':'1时', '2h':'2时',   '4h':'4时'
}

# 过滤和排序
def get_max_ratio(sym_data):
    signals = sym_data.get('signals', {})
    ratios = [abs(v['dist_ratio']) for v in signals.values() if v]
    return max(ratios) if ratios else 0

filtered = []
for inst_id, sym_data in symbols_data.items():
    conclusion = sym_data.get('conclusion', '')
    max_r = get_max_ratio(sym_data)

    if max_r < min_ratio:
        continue

    if direction_filter == "看空信号" and '做空' not in conclusion:
        continue
    if direction_filter == "看多信号" and '做多' not in conclusion:
        continue
    if direction_filter == "高概率信号" and '高概率' not in conclusion:
        continue
    if direction_filter == "等待信号" and '等待' not in conclusion and '观察' not in conclusion:
        continue

    filtered.append((inst_id, sym_data, max_r))

# 排序
if sort_by == "最大倍数":
    filtered.sort(key=lambda x: x[2], reverse=True)
elif sort_by == "交易量":
    filtered.sort(key=lambda x: x[1].get('volume_24h', 0), reverse=True)

if not filtered:
    st.info(f"当前过滤条件下无信号（最小倍数{min_ratio}x，方向:{direction_filter}）")
else:
    st.markdown(f"**符合条件的币种：{len(filtered)} 个**")

    for inst_id, sym_data, max_r in filtered:
        display   = sym_data.get('display', inst_id)
        price     = sym_data.get('price', 0)
        conclusion = sym_data.get('conclusion', '')
        signals   = sym_data.get('signals', {})
        volume    = sym_data.get('volume_24h', 0)

        card_class = get_conclusion_color(conclusion)

        # 构建多级别倍数行
        ratio_badges = ""
        for tf in TF_ORDER:
            sig = signals.get(tf)
            if sig:
                ratio_badges += get_ratio_badge(sig['dist_ratio'])
                # 额外标注
                if sig.get('divergence') == -1:
                    ratio_badges += '<span style="font-size:11px">⚠️顶背</span>'
                elif sig.get('divergence') == 1:
                    ratio_badges += '<span style="font-size:11px">✅底背</span>'
                if sig.get('near_zero'):
                    ratio_badges += '<span style="font-size:11px">🎯近零</span>'
                if sig.get('zero_cross') != 0:
                    ratio_badges += '<span style="font-size:11px">🔀穿零</span>'

        # EMA52状态
        h1_sig = signals.get('1h')
        ema52_info = ""
        if h1_sig and h1_sig.get('ema52'):
            e = h1_sig['ema52']
            pos = "价格在EMA52上方" if e['above'] else "价格在EMA52下方"
            near = " ⭐触及EMA52！" if e['near_ema52'] else ""
            ema52_info = f" | EMA52: {pos} {e['slope']}{near}"

        # 成交量格式化
        if volume >= 1e9:
            vol_str = f"{volume/1e9:.1f}B"
        else:
            vol_str = f"{volume/1e6:.0f}M"

        html = f"""
<div class="signal-card {card_class}">
    <div style="display:flex; justify-content:space-between; align-items:center;">
        <div>
            <span style="font-size:18px; font-weight:bold; color:white;">{display}</span>
            <span style="color:#aaa; margin-left:8px; font-size:13px;">${price:,.4f}</span>
            <span style="color:#666; margin-left:8px; font-size:11px;">Vol:{vol_str}</span>
        </div>
        <div style="font-size:14px; font-weight:bold;">{conclusion}</div>
    </div>
    <div style="margin-top:6px;">
        {ratio_badges}
    </div>
    <div style="margin-top:4px; color:#888; font-size:12px;">
        {ema52_info}
    </div>
</div>
"""
        st.markdown(html, unsafe_allow_html=True)

# ── 页脚 ──────────────────────────────────────────────────────
st.markdown("---")
st.caption("数据来源：OKX公开API | 信号基于K线动能理论 | 仅供参考，不构成投资建议")
st.caption("GitHub Actions 每5分钟更新数据 | 高概率信号无冷却，普通信号4小时内不重复推送")
