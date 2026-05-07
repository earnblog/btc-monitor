"""
MACD监控网页 v2
BTC/ETH/SOL/DOGE始终显示
"""
import streamlit as st
import json, os
from datetime import datetime

st.set_page_config(
    page_title="MACD信号监控",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
.signal-card{background:#1a1a2e;border-radius:10px;padding:12px 16px;
  margin-bottom:8px;border-left:4px solid #444}
.signal-short{border-left-color:#ff4444}
.signal-long{border-left-color:#44ff88}
.signal-wait{border-left-color:#ffaa00}
.signal-hp{border-left-color:#aa44ff}
.signal-priority{border:1px solid #555}
.ratio-badge{display:inline-block;padding:2px 8px;border-radius:4px;
  font-size:12px;font-weight:bold;margin:0 2px}
.ratio-high{background:#ff4444;color:white}
.ratio-mid{background:#ff8800;color:white}
.ratio-low{background:#444;color:#aaa}
.ratio-long-high{background:#44aa44;color:white}
.ratio-long-mid{background:#228822;color:white}
.priority-tag{display:inline-block;padding:1px 6px;border-radius:3px;
  font-size:10px;background:#333;color:#aaa;margin-left:6px}
</style>
""", unsafe_allow_html=True)

DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'signals.json')
PRIORITY_SYMS = ['BTC-USDT-SWAP','ETH-USDT-SWAP','SOL-USDT-SWAP','DOGE-USDT-SWAP']

@st.cache_data(ttl=60)
def load_signals():
    if not os.path.exists(DATA_FILE):
        return None
    try:
        with open(DATA_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

def get_ratio_badge(ratio):
    abs_r = abs(ratio)
    direction = "上方" if ratio > 0 else "下方"
    if ratio > 0:
        cls = "ratio-high" if abs_r>=3 else ("ratio-mid" if abs_r>=2 else "ratio-low")
    else:
        cls = "ratio-long-high" if abs_r>=3 else ("ratio-long-mid" if abs_r>=2 else "ratio-low")
    icon = "🔥" if abs_r>=3 else ("⚡" if abs_r>=2 else "")
    return f'<span class="ratio-badge {cls}">{icon}{direction}{abs_r:.1f}x</span>'

def get_card_class(conclusion):
    if '做空' in conclusion and '强烈' in conclusion: return 'signal-short'
    if '做空' in conclusion: return 'signal-short'
    if '做多' in conclusion and '强烈' in conclusion: return 'signal-long'
    if '做多' in conclusion: return 'signal-long'
    if '高概率' in conclusion: return 'signal-hp'
    return 'signal-wait'

st.title("📊 K线动能 · MACD信号监控")
st.caption("基于K线动能理论 · OKX永续合约 · GitHub Actions每5分钟更新")

col1, col2, col3 = st.columns([2,1,1])
with col1:
    st.markdown("**监控周期：** 5m / 15m / 30m / 1h / 2h / 4h")
with col2:
    if st.button("🔄 手动刷新"):
        st.cache_data.clear()
        st.rerun()
with col3:
    auto = st.toggle("自动刷新(60s)", value=False)

if auto:
    import time; time.sleep(60); st.rerun()

data = load_signals()
if data is None:
    st.warning("暂无数据，等待GitHub Actions首次运行（约5分钟）")
    st.stop()

updated_at = data.get('updated_at','')
if updated_at:
    try:
        dt = datetime.fromisoformat(updated_at.replace('Z','+00:00'))
        st.success(f"✅ 数据更新：{dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    except Exception:
        st.success(f"✅ 最后更新：{updated_at}")

symbols_data = data.get('symbols', {})
st.markdown(f"**监控币种：** {len(symbols_data)} 个（交易量>1亿USDT）")

st.markdown("---")
fc1, fc2, fc3 = st.columns(3)
with fc1:
    min_ratio = st.slider("最小MACD倍数", 0.5, 5.0, 2.0, 0.5)
with fc2:
    direction_filter = st.selectbox("方向过滤",
        ["全部","看空信号","看多信号","高概率信号","等待信号"])
with fc3:
    sort_by = st.selectbox("排序方式", ["最大倍数","交易量","优先币种优先"])

short_c = sum(1 for v in symbols_data.values() if '做空' in v.get('conclusion',''))
long_c  = sum(1 for v in symbols_data.values() if '做多' in v.get('conclusion',''))
hp_c    = sum(1 for v in symbols_data.values() if '高概率' in v.get('conclusion',''))
wait_c  = sum(1 for v in symbols_data.values() if '等待' in v.get('conclusion','') or '观察' in v.get('conclusion',''))

m1,m2,m3,m4 = st.columns(4)
m1.metric("🔴 做空", short_c)
m2.metric("🟢 做多", long_c)
m3.metric("🎯 高概率", hp_c)
m4.metric("⏳ 等待", wait_c)
st.markdown("---")

TF_ORDER = ['5m','15m','30m','1h','2h','4h']

def get_max_ratio(sym_data):
    sigs = sym_data.get('signals',{})
    ratios = [abs(v['dist_ratio']) for v in sigs.values() if v]
    return max(ratios) if ratios else 0

filtered = []
for inst_id, sym_data in symbols_data.items():
    conclusion = sym_data.get('conclusion','')
    max_r = get_max_ratio(sym_data)
    is_priority = inst_id in PRIORITY_SYMS

    # 优先币种始终显示，不受倍数过滤
    if not is_priority and max_r < min_ratio:
        continue
    if direction_filter == "看空信号" and '做空' not in conclusion: continue
    if direction_filter == "看多信号" and '做多' not in conclusion: continue
    if direction_filter == "高概率信号" and '高概率' not in conclusion: continue
    if direction_filter == "等待信号" and '等待' not in conclusion and '观察' not in conclusion: continue

    filtered.append((inst_id, sym_data, max_r, is_priority))

if sort_by == "最大倍数":
    filtered.sort(key=lambda x: (x[3], x[2]), reverse=True)
elif sort_by == "交易量":
    filtered.sort(key=lambda x: x[1].get('volume_24h',0), reverse=True)
elif sort_by == "优先币种优先":
    filtered.sort(key=lambda x: (not x[3], -x[2]))

st.markdown(f"**显示币种：{len(filtered)} 个**（优先币种BTC/ETH/SOL/DOGE始终显示）")

for inst_id, sym_data, max_r, is_priority in filtered:
    display    = sym_data.get('display', inst_id)
    price      = sym_data.get('price', 0)
    conclusion = sym_data.get('conclusion','')
    signals    = sym_data.get('signals',{})
    volume     = sym_data.get('volume_24h', 0)

    card_cls = get_card_class(conclusion)
    priority_tag = '<span class="priority-tag">⭐主流</span>' if is_priority else ''

    ratio_badges = ""
    for tf in TF_ORDER:
        sig = signals.get(tf)
        if sig:
            ratio_badges += get_ratio_badge(sig['dist_ratio'])
            if sig.get('divergence') == -1:
                ratio_badges += '<span style="font-size:11px">⚠️顶背</span>'
            elif sig.get('divergence') == 1:
                ratio_badges += '<span style="font-size:11px">✅底背</span>'
            if sig.get('near_zero'):
                ratio_badges += '<span style="font-size:11px">🎯近零</span>'
            if sig.get('zero_cross') not in (0, None):
                cross_dir = "↑" if sig['zero_cross']==1 else "↓"
                ratio_badges += f'<span style="font-size:11px">🔀穿零{cross_dir}</span>'

    h1_sig = signals.get('1h')
    ema52_info = ""
    if h1_sig and h1_sig.get('ema52'):
        e = h1_sig['ema52']
        pos = "EMA52上方" if e.get('above') else "EMA52下方"
        near = " ⭐触及EMA52！" if e.get('near_ema52') else ""
        ema52_info = f" | {pos} {e.get('dist_pct',0):.1f}% 斜率{e.get('slope','')}{near}"

    vol_str = f"{volume/1e9:.1f}B" if volume>=1e9 else f"{volume/1e6:.0f}M"

    # 价格格式化
    if price >= 1000:
        price_str = f"${price:,.2f}"
    elif price >= 1:
        price_str = f"${price:.4f}"
    else:
        price_str = f"${price:.6f}"

    html = f"""
<div class="signal-card {card_cls}">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div>
      <span style="font-size:18px;font-weight:bold;color:white">{display}</span>
      {priority_tag}
      <span style="color:#aaa;margin-left:8px;font-size:13px">{price_str}</span>
      <span style="color:#666;margin-left:8px;font-size:11px">Vol:{vol_str}</span>
    </div>
    <div style="font-size:13px;font-weight:bold">{conclusion}</div>
  </div>
  <div style="margin-top:6px">{ratio_badges}</div>
  <div style="margin-top:4px;color:#888;font-size:12px">{ema52_info}</div>
</div>"""
    st.markdown(html, unsafe_allow_html=True)

st.markdown("---")
st.caption("数据来源：OKX公开API | 基于K线动能理论 | 仅供参考，不构成投资建议")
st.caption("⭐主流币（BTC/ETH/SOL/DOGE）不受倍数过滤限制，始终显示")
