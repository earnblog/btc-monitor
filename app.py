"""
MACD监控网页 v3
修复HTML渲染问题
BTC/ETH/SOL/DOGE始终显示
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

st.markdown("""
<style>
.sc{background:#1a1a2e;border-radius:10px;padding:12px 16px;margin-bottom:8px;border-left:4px solid #444}
.ss{border-left-color:#ff4444}
.sl{border-left-color:#44ff88}
.sw{border-left-color:#ffaa00}
.sh{border-left-color:#aa44ff}
.rb{display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:bold;margin:0 2px}
.rh{background:#ff4444;color:white}
.rm{background:#ff8800;color:white}
.rl{background:#444;color:#aaa}
.rlh{background:#44aa44;color:white}
.rlm{background:#228822;color:white}
.pt{display:inline-block;padding:1px 6px;border-radius:3px;font-size:10px;background:#333;color:#aaa;margin-left:4px}
</style>
""", unsafe_allow_html=True)

DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'signals.json')
PRIORITY = ['BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP', 'DOGE-USDT-SWAP']
TF_ORDER = ['5m', '15m', '30m', '1h', '2h', '4h']

@st.cache_data(ttl=60)
def load_data():
    if not os.path.exists(DATA_FILE):
        return None
    try:
        with open(DATA_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

def ratio_badge(ratio):
    r = abs(ratio)
    d = '上方' if ratio > 0 else '下方'
    if ratio > 0:
        c = 'rh' if r >= 3 else ('rm' if r >= 2 else 'rl')
    else:
        c = 'rlh' if r >= 3 else ('rlm' if r >= 2 else 'rl')
    ic = '🔥' if r >= 3 else ('⚡' if r >= 2 else '')
    return f'<span class=rb {c}>{ic}{d}{r:.1f}x</span>'

def card_class(conclusion):
    if '做空' in conclusion: return 'ss'
    if '做多' in conclusion: return 'sl'
    if '高概率' in conclusion: return 'sh'
    return 'sw'

def render_coin(inst_id, sym_data, is_priority):
    name       = sym_data.get('display', inst_id)
    price      = float(sym_data.get('price', 0))
    conclusion = sym_data.get('conclusion', '')
    signals    = sym_data.get('signals', {})
    volume     = float(sym_data.get('volume_24h', 0))
    cc         = card_class(conclusion)

    # 价格格式
    if price >= 1000:   ps = f'${price:,.2f}'
    elif price >= 1:    ps = f'${price:.4f}'
    else:               ps = f'${price:.6f}'

    # 成交量
    vs = f'{volume/1e9:.1f}B' if volume >= 1e9 else f'{volume/1e6:.0f}M'

    # 主流标签
    pt = '<span class=pt>⭐主流</span>' if is_priority else ''

    # ratio badges
    badges = ''
    for tf in TF_ORDER:
        s = signals.get(tf)
        if not s:
            continue
        badges += ratio_badge(float(s.get('dist_ratio', 0)))
        if s.get('divergence') == -1:
            badges += '<span style=font-size:11px>⚠顶背</span>'
        elif s.get('divergence') == 1:
            badges += '<span style=font-size:11px>✅底背</span>'
        if s.get('near_zero'):
            badges += '<span style=font-size:11px>🎯近零</span>'
        zc = s.get('zero_cross', 0)
        if zc and zc != 0:
            badges += f'<span style=font-size:11px>🔀穿零{"↑" if zc==1 else "↓"}</span>'

    # EMA52
    ema_info = ''
    h1 = signals.get('1h')
    if h1 and isinstance(h1.get('ema52'), dict):
        e = h1['ema52']
        pos = 'EMA52上方' if e.get('above') else 'EMA52下方'
        near = ' ⭐触EMA52!' if e.get('near_ema52') else ''
        ema_info = f'| {pos} {float(e.get("dist_pct",0)):.1f}% {e.get("slope","")}{near}'

    st.markdown(
        f'<div class="sc {cc}">'
        f'<div style="display:flex;justify-content:space-between;align-items:center">'
        f'<div><span style="font-size:18px;font-weight:bold;color:white">{name}</span>'
        f'{pt}'
        f'<span style="color:#aaa;margin-left:8px;font-size:13px">{ps}</span>'
        f'<span style="color:#666;margin-left:8px;font-size:11px">Vol:{vs}</span></div>'
        f'<div style="font-size:13px;font-weight:bold">{conclusion}</div>'
        f'</div>'
        f'<div style="margin-top:6px">{badges}</div>'
        f'<div style="margin-top:4px;color:#888;font-size:12px">{ema_info}</div>'
        f'</div>',
        unsafe_allow_html=True
    )

# ── 页面主体 ──
st.title("📊 K线动能 · MACD信号监控")
st.caption("基于K线动能理论 · OKX永续合约 · GitHub Actions每5分钟更新")

c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    st.markdown("**监控周期：** 5m / 15m / 30m / 1h / 2h / 4h")
with c2:
    if st.button("🔄 手动刷新"):
        st.cache_data.clear()
        st.rerun()
with c3:
    if st.toggle("自动刷新60s"):
        import time; time.sleep(60); st.rerun()

data = load_data()
if data is None:
    st.warning("暂无数据，等待GitHub Actions首次运行（约5分钟）")
    st.stop()

updated = data.get('updated_at', '')
try:
    dt = datetime.fromisoformat(updated.replace('Z', '+00:00'))
    st.success(f"✅ 数据更新：{dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
except Exception:
    st.success(f"✅ 最后更新：{updated}")

syms = data.get('symbols', {})
st.markdown(f"**监控币种：** {len(syms)} 个（交易量>1亿USDT）")
st.markdown("---")

# 过滤控件
fc1, fc2, fc3 = st.columns(3)
with fc1:
    min_r = st.slider("最小MACD倍数", 0.5, 5.0, 2.0, 0.5)
with fc2:
    dir_f = st.selectbox("方向过滤", ["全部","看空信号","看多信号","高概率信号","等待信号"])
with fc3:
    sort_by = st.selectbox("排序", ["最大倍数", "交易量", "优先币种优先"])

# 统计
sc = sum(1 for v in syms.values() if '做空' in v.get('conclusion',''))
lc = sum(1 for v in syms.values() if '做多' in v.get('conclusion',''))
hc = sum(1 for v in syms.values() if '高概率' in v.get('conclusion',''))
wc = sum(1 for v in syms.values() if '等待' in v.get('conclusion','') or '观察' in v.get('conclusion',''))

m1,m2,m3,m4 = st.columns(4)
m1.metric("🔴 做空", sc)
m2.metric("🟢 做多", lc)
m3.metric("🎯 高概率", hc)
m4.metric("⏳ 等待", wc)
st.markdown("---")

def max_ratio(sd):
    s = sd.get('signals', {})
    rs = [abs(float(v.get('dist_ratio',0))) for v in s.values() if v]
    return max(rs) if rs else 0

# 构建列表
filtered = []
for iid, sd in syms.items():
    conc = sd.get('conclusion', '')
    mr = max_ratio(sd)
    ip = iid in PRIORITY
    if not ip and mr < min_r: continue
    if dir_f == "看空信号" and '做空' not in conc: continue
    if dir_f == "看多信号" and '做多' not in conc: continue
    if dir_f == "高概率信号" and '高概率' not in conc: continue
    if dir_f == "等待信号" and '等待' not in conc and '观察' not in conc: continue
    filtered.append((iid, sd, mr, ip))

if sort_by == "最大倍数":
    filtered.sort(key=lambda x: x[2], reverse=True)
elif sort_by == "交易量":
    filtered.sort(key=lambda x: float(x[1].get('volume_24h',0)), reverse=True)
else:
    filtered.sort(key=lambda x: (not x[3], -x[2]))

st.markdown(f"**显示：{len(filtered)} 个**（⭐主流币BTC/ETH/SOL/DOGE始终显示）")

for iid, sd, mr, ip in filtered:
    render_coin(iid, sd, ip)

st.markdown("---")
st.caption("数据来源：OKX公开API | 基于K线动能理论 | 仅供参考，不构成投资建议")
