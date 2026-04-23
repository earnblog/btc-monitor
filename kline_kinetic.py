# -*- coding: utf-8 -*-
"""
K线动能理论 · 三级别日内合约监控 v2
新增: 大级别方向过滤 + 第一次归零轴 + 级别升级 + 隐形形态过滤
运行: streamlit run kline_kinetic.py
依赖: pip install streamlit ccxt pandas plotly
"""

import time
import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import streamlit as st

st.set_page_config(page_title="K线动能 · 三级别", page_icon="⚡",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&family=Share+Tech+Mono&display=swap');
html,body,[class*="css"]{background-color:#080c14!important;color:#c0cce0!important;font-family:'Noto Sans SC',sans-serif;}
.stApp{background-color:#080c14;}
#MainMenu,footer,header{visibility:hidden;}
.block-container{padding-top:1rem;padding-bottom:.5rem;}
.page-title{font-family:'Share Tech Mono',monospace;font-size:.95rem;color:#4af0c4;
            letter-spacing:.18em;border-bottom:1px solid #0e2a3a;padding-bottom:7px;margin-bottom:12px;}
.level-header{font-family:'Share Tech Mono',monospace;font-size:.72rem;letter-spacing:.2em;
              text-transform:uppercase;padding:5px 10px;border-radius:4px;margin-bottom:8px;display:inline-block;}
.sig-card{border-radius:8px;padding:14px 16px;margin-bottom:8px;border-left-width:4px;border-left-style:solid;}
.sig-price{font-family:'Share Tech Mono',monospace;font-size:1.4rem;font-weight:700;color:#fff;}
.sig-title{font-family:'Share Tech Mono',monospace;font-size:1.1rem;font-weight:700;margin-top:4px;}
.sig-sub{font-size:.75rem;margin-top:4px;line-height:1.5;}
.sig-time{font-family:'Share Tech Mono',monospace;font-size:.65rem;color:#3a5a7a;margin-top:6px;}
.cond-wrap{background:#0b1828;border:1px solid #0e2035;border-radius:6px;padding:10px 14px;margin-bottom:6px;}
.cond-title{font-size:.62rem;letter-spacing:.15em;color:#3a5a7a;text-transform:uppercase;margin-bottom:5px;}
.cond-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:2px;}
.cond-label{font-size:.73rem;color:#4a6a8a;}
.cond-val{font-family:'Share Tech Mono',monospace;font-size:.82rem;}
.green{color:#00e676;} .red{color:#ff5252;} .yellow{color:#ffca28;} .gray{color:#5a7a9a;} .cyan{color:#4af0c4;}
.alert-buy{background:#091e12;border:1px solid #00e676;border-left:4px solid #00e676;border-radius:6px;padding:12px 16px;margin-bottom:6px;}
.alert-sell{background:#1e0606;border:1px solid #ff5252;border-left:4px solid #ff5252;border-radius:6px;padding:12px 16px;margin-bottom:6px;}
.alert-stop{background:#1a0808;border:1px solid #ff1744;border-left:4px solid #ff1744;border-radius:6px;padding:12px 16px;margin-bottom:6px;}
.alert-prep{background:#0d1e2e;border:1px solid #4af0c4;border-left:4px solid #4af0c4;border-radius:6px;padding:12px 16px;margin-bottom:6px;}
.alert-combo{background:#1a1000;border:1px solid #ffd740;border-left:4px solid #ffd740;border-radius:6px;padding:12px 16px;margin-bottom:6px;}
.alert-blocked{background:#0e0e0e;border:1px solid #2a2a2a;border-left:4px solid #3a3a3a;border-radius:6px;padding:10px 14px;margin-bottom:6px;}
.alert-label{font-family:'Share Tech Mono',monospace;font-size:.68rem;margin-bottom:5px;}
.alert-body{font-size:.82rem;line-height:1.8;white-space:pre-line;}
.pos-card{background:#0a1e14;border:1px solid #1a4030;border-radius:6px;padding:10px 14px;margin-bottom:6px;}
.pos-title{font-size:.62rem;letter-spacing:.15em;color:#2a7a4a;text-transform:uppercase;margin-bottom:6px;}
.pos-row{display:flex;justify-content:space-between;margin-bottom:3px;}
.pos-label{font-size:.73rem;color:#4a8a6a;}
.pos-val{font-family:'Share Tech Mono',monospace;font-size:.82rem;color:#00e676;}
.pnl-pos{font-family:'Share Tech Mono',monospace;font-size:1rem;color:#00e676;font-weight:700;}
.pnl-neg{font-family:'Share Tech Mono',monospace;font-size:1rem;color:#ff5252;font-weight:700;}
.badge{display:inline-block;font-family:'Share Tech Mono',monospace;font-size:.65rem;
       padding:2px 8px;border-radius:3px;margin-right:4px;margin-top:4px;}
.badge-first{background:#0a2a1a;color:#00e676;border:1px solid #00e67644;}
.badge-upgrade{background:#1a1000;color:#ffd740;border:1px solid #ffd74044;}
.badge-hidden{background:#1a0a00;color:#ff9800;border:1px solid #ff980044;}
.badge-blocked{background:#1a1a1a;color:#5a5a5a;border:1px solid #3a3a3a44;}
.timestamp{font-family:'Share Tech Mono',monospace;font-size:.68rem;color:#2a4a6a;}
@keyframes flash{0%,100%{opacity:1}50%{opacity:.3}}
.flashing{animation:flash .7s ease-in-out 6;}
</style>
""", unsafe_allow_html=True)

# ── Binance REST API ─────────────────────────────────────────────────────────
# 多个备用域名，任何一个成功就返回
BINANCE_HOSTS = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
]

TF_MAP = {'5m':'5m','15m':'15m','1h':'1h','4h':'4h','1d':'1d'}

# ══════════════════════════════════════════════════════════════════════════════
# 数据 & 指标
# ══════════════════════════════════════════════════════════════════════════════
def fetch_ohlcv(symbol, tf, limit=300):
    sym = symbol.replace('/','')
    last_err = ""
    for host in BINANCE_HOSTS:
        try:
            url = f"{host}/api/v3/klines"
            r   = requests.get(url,
                    params={"symbol":sym,"interval":TF_MAP[tf],"limit":limit},
                    timeout=12, headers={"User-Agent":"Mozilla/5.0"})
            r.raise_for_status()
            raw = r.json()
            if not isinstance(raw, list) or len(raw) == 0:
                last_err = f"空数据: {raw}"
                continue
            df = pd.DataFrame(raw, columns=['ts','open','high','low','close','volume',
                                            'close_time','quote_vol','trades',
                                            'taker_base','taker_quote','ignore'])
            df['time'] = pd.to_datetime(df['ts'].astype(float), unit='ms')
            for c in ['open','high','low','close','volume']:
                df[c] = df[c].astype(float)
            return df[['time','open','high','low','close','volume']]
        except Exception as e:
            last_err = str(e)
            continue
    st.error(f"K线获取失败({sym} {tf}): {last_err}")
    return pd.DataFrame()

def fetch_realtime_price(symbol):
    sym = symbol.replace('/','')
    for host in BINANCE_HOSTS:
        try:
            url = f"{host}/api/v3/ticker/price"
            r   = requests.get(url, params={"symbol":sym}, timeout=6,
                               headers={"User-Agent":"Mozilla/5.0"})
            r.raise_for_status()
            return float(r.json()['price'])
        except:
            continue
    return None

for k in ['pos_short','pos_mid','pos_long']:
    if k not in st.session_state: st.session_state[k] = None
for k in ['alert_short','alert_mid','alert_long']:
    if k not in st.session_state: st.session_state[k] = {"type":None,"time":0}

def calc_ind(df):
    if df.empty: return df
    df = df.copy()
    c = df['close']
    df['dif']  = c.ewm(span=12,adjust=False).mean() - c.ewm(span=26,adjust=False).mean()
    df['dea']  = df['dif'].ewm(span=9,adjust=False).mean()
    df['hist'] = (df['dif'] - df['dea']) * 2
    df['ema13'] = c.ewm(span=13,adjust=False).mean()
    df['ema24'] = c.ewm(span=24,adjust=False).mean()
    df['ema52'] = c.ewm(span=52,adjust=False).mean()
    return df

# ══════════════════════════════════════════════════════════════════════════════
# 核心判断
# ══════════════════════════════════════════════════════════════════════════════
def zero_axis(df):
    """归零轴检测"""
    if df.empty or len(df) < 60:
        return {"dir":"none","prox":1.0,"level":"FAR","above":True,"conv":False,
                "dif":0,"detail":"数据不足","hidden":False}
    dif     = float(df['dif'].iloc[-1])
    dif_p   = float(df['dif'].iloc[-4])
    dif_max = float(df['dif'].abs().rolling(80).max().iloc[-1])
    prox    = abs(dif) / (dif_max + 1e-9)
    conv    = abs(dif) < abs(dif_p)
    above   = dif > 0
    hn      = float(df['hist'].iloc[-1])
    hidden  = (abs(hn) / (abs(dif) + 1e-9)) < 0.05 and prox > 0.35

    if   prox < 0.10: level = "ZERO"
    elif prox < 0.22: level = "NEAR"
    elif prox < 0.40: level = "CONV"
    else:             level = "FAR"

    dire, detail = "none", ""
    if level == "ZERO":
        dire   = "long" if above else "short"
        detail = f"DIF={dif:.4f} 已归零轴{'上方' if above else '下方'} → {'做多' if above else '做空'}机会"
    elif level == "NEAR" and conv:
        dire   = "long_prep" if above else "short_prep"
        detail = f"DIF={dif:.4f} 接近零轴({'上' if above else '下'}方 {prox*100:.0f}%) 收缩中"
    elif hidden:
        detail = f"⚠ 隐形形态 DIF={dif:.4f} 预示将归零轴"
    else:
        detail = f"DIF={dif:.4f} {'上方' if above else '下方'} 距零轴{prox*100:.0f}%"

    return {"dir":dire,"prox":round(prox,3),"level":level,"above":above,
            "conv":conv,"dif":round(dif,4),"detail":detail,"hidden":hidden}

def detect_first_zero(df):
    """
    第一次归零轴检测
    判断逻辑: 过去N根K线内，DIF是否从高位第一次下来碰零轴
    返回: is_first(bool), zero_count(int), detail
    """
    if df.empty or len(df) < 80:
        return {"is_first":False,"count":0,"detail":"数据不足"}

    dif = df['dif'].values
    # 找到最近一次DIF到达零轴的次数（在当前趋势内）
    # 方法：向前找，DIF同侧的归零次数
    current_above = dif[-1] > 0
    cross_count   = 0
    max_dif       = 0.0

    # 从当前往前数，找同侧方向内归零轴的次数
    i = len(dif) - 1
    while i >= 10:
        # 如果方向反转（穿越零轴到另一侧），停止计数
        if current_above and dif[i] < 0: break
        if not current_above and dif[i] > 0: break
        # 记录DIF最高点（用来判断这轮能量有多大）
        max_dif = max(max_dif, abs(dif[i]))
        # 向前找归零点（DIF从高位回到接近零轴的位置）
        if abs(dif[i]) < abs(dif).max() * 0.12:
            # 确认是一次归零：前面有高位
            if i > 5 and abs(dif[i-5]) > abs(dif).max() * 0.3:
                cross_count += 1
        i -= 1

    is_first = cross_count <= 1
    if is_first:
        detail = "第一次归零轴 ★ 反弹力度最强"
    elif cross_count == 2:
        detail = f"第二次归零轴 力度减弱"
    else:
        detail = f"第{cross_count}次归零轴 力度较弱"

    return {"is_first":is_first,"count":cross_count,"detail":detail}

def detect_level_upgrade(df_small, df_large):
    """
    级别升级检测
    条件1: 当前小级别DIF高点 > 上一轮DIF高点（能量在增强）
    条件2: 大级别DIF接近零轴
    返回: upgraded(bool), detail
    """
    if df_small.empty or df_large.empty or len(df_small) < 80:
        return {"upgraded":False,"detail":"数据不足"}

    dif = df_small['dif'].values
    # 找最近两个DIF局部高点
    peaks = []
    for i in range(5, len(dif)-5):
        if dif[i] > dif[i-3] and dif[i] > dif[i+3] and dif[i] > 0:
            peaks.append((i, dif[i]))
    if len(peaks) < 2:
        return {"upgraded":False,"detail":"峰值数据不足"}

    last_peak   = peaks[-1][1]
    prev_peak   = peaks[-2][1]
    energy_up   = last_peak > prev_peak   # 新高点能量更强

    # 大级别DIF是否接近零轴
    large_za    = zero_axis(df_large)
    large_near  = large_za['prox'] < 0.25 and large_za['above']

    upgraded = energy_up and large_near
    if upgraded:
        detail = f"级别升级! 新DIF高点({last_peak:.3f})>{prev_peak:.3f} + 大级别归零轴"
    elif energy_up:
        detail = f"能量增强({last_peak:.3f}>{prev_peak:.3f}) 等待大级别归零轴确认"
    else:
        detail = f"能量衰减({last_peak:.3f}<{prev_peak:.3f}) 反弹力度减弱"

    return {"upgraded":upgraded,"energy_up":energy_up,"large_near":large_near,"detail":detail}

def detect_hidden(df):
    """
    隐形形态检测
    远离零轴时价格继续运动但能量柱不放大 = 隐形
    返回: is_hidden, hidden_type(top/bot), detail, should_wait
    """
    if df.empty or len(df) < 30:
        return {"is_hidden":False,"htype":"none","detail":"","should_wait":False}

    dif      = float(df['dif'].iloc[-1])
    hist_now = float(df['hist'].iloc[-1])
    hist_max = float(df['hist'].abs().rolling(30).max().iloc[-1])
    dif_max  = float(df['dif'].abs().rolling(80).max().iloc[-1])
    prox     = abs(dif) / (dif_max + 1e-9)

    # 远离零轴 + 能量柱极小 = 隐形
    hist_ratio  = abs(hist_now) / (hist_max + 1e-9)
    is_hidden   = prox > 0.35 and hist_ratio < 0.10
    above       = dif > 0
    htype       = "top" if above else "bot"

    if is_hidden:
        if above:
            detail      = "高位隐形形态: 价格在涨但能量柱萎缩 → 预示将归零轴，等待做空机会"
            should_wait = True   # 还没到零轴，先等
        else:
            detail      = "低位隐形形态: 价格在跌但能量柱萎缩 → 预示将归零轴反弹，提前关注"
            should_wait = True
    else:
        detail      = ""
        should_wait = False

    return {"is_hidden":is_hidden,"htype":htype,"detail":detail,"should_wait":should_wait}

def ema52_touch(df, realtime_price=None):
    """EMA52触碰检测，优先使用实时价格"""
    if df.empty or len(df) < 60:
        return {"touch":False,"exact":False,"gap":99,"ema52":0,"price":0,"above":True,"detail":"数据不足"}
    # 优先用实时Ticker价格，没有则用K线最新收盘价
    price = realtime_price if realtime_price else float(df['close'].iloc[-1])
    e52   = float(df['ema52'].iloc[-1])
    gap   = abs(price - e52) / e52 * 100
    return {"touch":gap<0.5,"exact":gap<0.15,"gap":round(gap,2),
            "ema52":round(e52,1),"price":round(price,1),"above":price>e52,
            "detail":f"{'精准触碰' if gap<0.15 else '接近' if gap<0.5 else '距离'}EMA52(${e52:,.0f}) 偏离{gap:.2f}%"}

def divergence(df, lb=25):
    if df.empty or len(df) < lb+5: return {"type":"NONE","detail":""}
    rp,rh = df['close'].iloc[-lb:], df['hist'].iloc[-lb:]
    pn,hn = float(df['close'].iloc[-1]), float(df['hist'].iloc[-1])
    if pn < rp.min()*1.012 and hn > rh.min()*0.75 and hn < 0:
        return {"type":"BULL","detail":"底背离 → 买点加强"}
    if pn > rp.max()*0.988 and hn < rh.max()*0.75 and hn > 0:
        return {"type":"BEAR","detail":"顶背离 → 卖点加强"}
    return {"type":"NONE","detail":""}

# ══════════════════════════════════════════════════════════════════════════════
# 大级别方向过滤
# ══════════════════════════════════════════════════════════════════════════════
def get_h4_direction(za_h4):
    """
    4小时大方向判断
    返回: 'bull'(做多方向) / 'bear'(做空方向) / 'unclear'(不明确)
    """
    if za_h4['above']:
        return "bull"
    else:
        return "bear"

def is_signal_allowed(sig_direction, h4_direction):
    """
    信号是否被大级别过滤
    sig_direction: 'long' or 'short'
    h4_direction:  'bull' or 'bear' or 'unclear'
    """
    if h4_direction == "bull" and sig_direction == "long":  return True
    if h4_direction == "bear" and sig_direction == "short": return True
    return False

# ══════════════════════════════════════════════════════════════════════════════
# 信号生成（含过滤）
# ══════════════════════════════════════════════════════════════════════════════
def make_signal(za, entry_df, pos, div_za, div_entry, label,
                h4_direction, first_r, upgrade_r, hidden_r, realtime_price=None):
    et      = ema52_touch(entry_df, realtime_price)
    alerts  = []
    sig     = "WAIT"
    title   = "等待信号"
    sub     = "条件未满足"
    color   = "#ffca28"
    bg      = "#1a1500"
    badges  = []
    blocked = False
    blocked_reason = ""

    raw_dir = "long" if za['above'] else "short"

    # ── 隐形形态过滤：远离零轴出现隐形，先等待不入场 ──────────────────
    if hidden_r['is_hidden'] and hidden_r['should_wait']:
        sig    = "HIDDEN_WAIT"
        title  = "隐形等待"
        sub    = hidden_r['detail']
        color  = "#ff9800"
        bg     = "#1a0a00"
        badges.append(("HIDDEN","badge-hidden"))
        return {"sig":sig,"title":title,"sub":sub,"color":color,"bg":bg,
                "alerts":[],"et":et,"badges":badges,"blocked":False,"blocked_reason":""}

    # ── 大级别方向过滤 ─────────────────────────────────────────────────
    if not is_signal_allowed(raw_dir, h4_direction):
        blocked        = True
        blocked_reason = f"4H方向{'看多' if h4_direction=='bull' else '看空'}，屏蔽{'做多' if raw_dir=='long' else '做空'}信号"
        sig    = "BLOCKED"
        title  = "方向过滤"
        sub    = blocked_reason
        color  = "#3a5a7a"
        bg     = "#0a0e14"
        badges.append(("已屏蔽","badge-blocked"))
        return {"sig":sig,"title":title,"sub":sub,"color":color,"bg":bg,
                "alerts":[],"et":et,"badges":badges,"blocked":True,"blocked_reason":blocked_reason}

    # ── 信号生成 ──────────────────────────────────────────────────────
    if za['dir'] == "long" and et['touch'] and et['above']:
        sig,title = "BUY","做多信号 ▲"
        sub    = f"归零轴(上方) + 触EMA52(${et['ema52']:,.0f})"
        color,bg = "#00e676","#091e12"
        msg    = f"[{label}] 做多入场!\n价格: ${et['price']:,.0f}  EMA52: ${et['ema52']:,.0f}\n止损: ${et['ema52']*0.995:,.0f}"
        # 第一次归零轴加强提示
        if first_r['is_first']:
            msg += "\n★ 第一次归零轴 反弹力度最强!"
            badges.append(("第一次归零","badge-first"))
        if upgrade_r['upgraded']:
            msg += "\n⚡ 级别升级确认!"
            badges.append(("级别升级","badge-upgrade"))
        alerts.append({"type":"buy","urgency":"urgent","msg":msg})

    elif za['dir'] == "long_prep" and et['touch'] and et['above']:
        sig,title = "BUY_PREP","做多预备 ▲"
        sub    = f"DIF接近零轴({za['prox']*100:.0f}%) + 触EMA52"
        color,bg = "#69f0ae","#071a10"
        alerts.append({"type":"prep","urgency":"normal",
            "msg":f"[{label}] 做多预备 等待归零轴确认\nEMA52: ${et['ema52']:,.0f}"})

    elif za['dir'] == "short" and et['touch'] and not et['above']:
        sig,title = "SELL","做空信号 ▼"
        sub    = f"归零轴(下方) + 触EMA52压力(${et['ema52']:,.0f})"
        color,bg = "#ff5252","#1e0606"
        msg    = f"[{label}] 做空入场!\n价格: ${et['price']:,.0f}  EMA52: ${et['ema52']:,.0f}\n止损: ${et['ema52']*1.005:,.0f}"
        if first_r['is_first']:
            msg += "\n★ 第一次归零轴 下跌动能最强!"
            badges.append(("第一次归零","badge-first"))
        alerts.append({"type":"sell","urgency":"urgent","msg":msg})

    elif za['dir'] == "short_prep" and et['touch'] and not et['above']:
        sig,title = "SELL_PREP","做空预备 ▼"
        sub    = f"DIF接近零轴下方({za['prox']*100:.0f}%) + 触EMA52"
        color,bg = "#ff8a80","#1a0808"
        alerts.append({"type":"prep","urgency":"normal",
            "msg":f"[{label}] 做空预备 等待归零轴确认\nEMA52: ${et['ema52']:,.0f}"})

    # 背离加强
    if div_za['type']=="BULL" and "BUY" in sig:
        alerts.append({"type":"prep","urgency":"normal","msg":f"[{label}] 底背离加强做多信号"})
    if div_za['type']=="BEAR" and "SELL" in sig:
        alerts.append({"type":"prep","urgency":"normal","msg":f"[{label}] 顶背离加强做空信号"})

    # 级别升级单独提醒
    if upgrade_r['upgraded'] and sig not in ("BUY","SELL"):
        alerts.append({"type":"prep","urgency":"normal",
            "msg":f"[{label}] ⚡ 级别升级信号! {upgrade_r['detail']}"})
        badges.append(("级别升级","badge-upgrade"))

    # 止损检测
    if pos:
        price,e52,entry,side = et['price'],et['ema52'],pos['entry'],pos['side']
        if side=="long":
            pnl=(price-entry)/entry*100
            if price < e52*0.997:
                alerts.append({"type":"stop","urgency":"urgent",
                    "msg":f"[{label}] 止损! 跌破EMA52(${e52:,.0f})\n盈亏: {pnl:+.2f}%"})
        elif side=="short":
            pnl=(entry-price)/entry*100
            if price > e52*1.003:
                alerts.append({"type":"stop","urgency":"urgent",
                    "msg":f"[{label}] 止损! 突破EMA52(${e52:,.0f})\n盈亏: {pnl:+.2f}%"})

    return {"sig":sig,"title":title,"sub":sub,"color":color,"bg":bg,
            "alerts":alerts,"et":et,"badges":badges,"blocked":blocked,"blocked_reason":blocked_reason}

# ══════════════════════════════════════════════════════════════════════════════
# 声音
# ══════════════════════════════════════════════════════════════════════════════
def play_sound(atype, urgency):
    if urgency=="urgent":
        if atype=="buy":   freqs,dur=[440,550,660],280
        elif atype=="sell":freqs,dur=[660,550,440],280
        elif atype=="stop":freqs,dur=[880,880,880],180
        else:              freqs,dur=[520],350
    else:
        freqs,dur=[440],320
    js=""
    for i,f in enumerate(freqs):
        js+=f"setTimeout(function(){{var o=c.createOscillator(),g=c.createGain();o.connect(g);g.connect(c.destination);o.frequency.value={f};o.type='sine';g.gain.setValueAtTime(0.35,c.currentTime);g.gain.exponentialRampToValueAtTime(0.001,c.currentTime+{dur}/1000);o.start(c.currentTime);o.stop(c.currentTime+{dur}/1000);}},{i*(dur+80)});"
    st.components.v1.html(f"<script>(function(){{try{{var c=new(window.AudioContext||window.webkitAudioContext)();{js}}}catch(e){{}}if('Notification' in window&&Notification.permission!=='denied'){{if(Notification.permission==='granted'){{new Notification('K线动能',{{body:'{atype}'}});}}else{{Notification.requestPermission();}}}}}})();</script>",height=0)

# ══════════════════════════════════════════════════════════════════════════════
# 图表
# ══════════════════════════════════════════════════════════════════════════════
def build_chart(df, title, pos=None):
    if df.empty: return go.Figure()
    n = min(80,len(df))
    d = df.iloc[-n:]
    fig = make_subplots(rows=2,cols=1,shared_xaxes=True,row_heights=[0.62,0.38],vertical_spacing=0.04)
    fig.add_trace(go.Candlestick(x=d['time'],open=d['open'],high=d['high'],low=d['low'],close=d['close'],
        name="K线",increasing_fillcolor="#00c853",increasing_line_color="#00c853",
        decreasing_fillcolor="#d50000",decreasing_line_color="#d50000",line_width=1),row=1,col=1)
    if 'ema52' in d.columns:
        fig.add_trace(go.Scatter(x=d['time'],y=d['ema52'],name="EMA52",
            line=dict(color="#00e676",width=2)),row=1,col=1)
        fig.add_trace(go.Scatter(x=d['time'],y=d['ema24'],name="EMA24",
            line=dict(color="#aa44ff",width=1,dash="dot"),opacity=0.5),row=1,col=1)
    if pos:
        fig.add_hline(y=pos['entry'],line_color="#ffca28",line_width=1.5,line_dash="dash",
            annotation_text=f"入场${pos['entry']:,.0f}",annotation_font_color="#ffca28",row=1,col=1)
        fig.add_hline(y=pos['stop'],line_color="#ff5252",line_width=1,line_dash="dot",
            annotation_text=f"止损${pos['stop']:,.0f}",annotation_font_color="#ff5252",row=1,col=1)
    fig.add_hline(y=0,line_color="#2a4a6a",line_width=1,row=2,col=1)
    cols=["#00c853" if v>=0 else "#d50000" for v in d['hist']]
    fig.add_trace(go.Bar(x=d['time'],y=d['hist'],name="能量柱",marker_color=cols,opacity=0.75),row=2,col=1)
    fig.add_trace(go.Scatter(x=d['time'],y=d['dif'],name="DIF",
        line=dict(color="#e8f0ff",width=1.5)),row=2,col=1)
    fig.add_trace(go.Scatter(x=d['time'],y=d['dea'],name="DEA",
        line=dict(color="#ffd740",width=1.2)),row=2,col=1)
    dv=float(d['dif'].iloc[-1])
    fig.add_annotation(x=d['time'].iloc[-1],y=dv,text=f" {dv:.4f}",
        font=dict(color="#e8f0ff",size=10),showarrow=False,xanchor="left",row=2,col=1)
    fig.update_layout(
        title=dict(text=title,font=dict(color="#4a8aaa",size=11),x=0.01),
        paper_bgcolor="#080c14",plot_bgcolor="#0b1220",
        font=dict(color="#5a7a9a",size=10),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h",y=1.06,x=0,font=dict(size=9),bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=8,r=8,t=30,b=8),height=320)
    for i in [1,2]:
        fig.update_xaxes(gridcolor="#0d1e2e",row=i,col=1)
        fig.update_yaxes(gridcolor="#0d1e2e",row=i,col=1)
    return fig

# ══════════════════════════════════════════════════════════════════════════════
# 渲染单个级别面板
# ══════════════════════════════════════════════════════════════════════════════
def render_level(label, accent, za, result, pos, now_str, pos_key, alert_key, h4_dir):
    now_ts    = time.time()
    last      = st.session_state[alert_key]
    sig       = result['sig']
    new_alert = (last['type']!=sig) or (now_ts-last['time']>60)
    et        = result['et']

    # 自动记录仓位（只有非屏蔽信号才记录）
    if sig=="BUY" and st.session_state[pos_key] is None and new_alert:
        st.session_state[pos_key]={"side":"long","entry":et['price'],
            "ema52":et['ema52'],"time":now_str,"stop":round(et['ema52']*0.995,1)}
        st.session_state[alert_key]={"type":sig,"time":now_ts}
    elif sig=="SELL" and st.session_state[pos_key] is None and new_alert:
        st.session_state[pos_key]={"side":"short","entry":et['price'],
            "ema52":et['ema52'],"time":now_str,"stop":round(et['ema52']*1.005,1)}
        st.session_state[alert_key]={"type":sig,"time":now_ts}
    elif new_alert:
        st.session_state[alert_key]={"type":sig,"time":now_ts}

    pos = st.session_state[pos_key]

    # 级别标题
    st.markdown(f'<div class="level-header" style="background:{accent}22;color:{accent};border:1px solid {accent}44">{label}</div>',
                unsafe_allow_html=True)

    # 徽章
    if result['badges']:
        badges_html = "".join(f'<span class="badge {bc}">{bt}</span>' for bt,bc in result['badges'])
        st.markdown(badges_html, unsafe_allow_html=True)

    # 信号卡
    flash = ' flashing' if sig in ("BUY","SELL") else ''
    st.markdown(f"""
    <div class="sig-card{flash}" style="background:{result['bg']};border-color:{result['color']}">
        <div class="sig-price">${et['price']:,.1f}</div>
        <div class="sig-title" style="color:{result['color']}">{result['title']}</div>
        <div class="sig-sub" style="color:{result['color']}99">{result['sub']}</div>
        <div class="sig-time">{now_str}</div>
    </div>""", unsafe_allow_html=True)

    # 提醒横幅
    for al in result['alerts']:
        t = al['type']
        if t=="buy":
            st.markdown(f'<div class="alert-buy"><div class="alert-label" style="color:#00e676">🟢 做多信号 {now_str}</div><div class="alert-body" style="color:#69f0ae">{al["msg"]}</div></div>',unsafe_allow_html=True)
            if new_alert: play_sound("buy","urgent")
        elif t=="sell":
            st.markdown(f'<div class="alert-sell"><div class="alert-label" style="color:#ff5252">🔴 做空信号 {now_str}</div><div class="alert-body" style="color:#ff8a80">{al["msg"]}</div></div>',unsafe_allow_html=True)
            if new_alert: play_sound("sell","urgent")
        elif t=="stop":
            st.markdown(f'<div class="alert-stop flashing"><div class="alert-label" style="color:#ff1744">⚠ 止损提醒 {now_str}</div><div class="alert-body" style="color:#ff8a80">{al["msg"]}</div></div>',unsafe_allow_html=True)
            if new_alert: play_sound("stop","urgent")
        elif t=="prep":
            st.markdown(f'<div class="alert-prep"><div class="alert-label" style="color:#4af0c4">ℹ 预备/加强 {now_str}</div><div class="alert-body" style="color:#4af0c4">{al["msg"]}</div></div>',unsafe_allow_html=True)
            if new_alert: play_sound("prep","normal")

    # 大级别过滤状态
    h4_col   = "#00e676" if h4_dir=="bull" else "#ff5252"
    h4_txt   = "看多方向 ✓" if h4_dir=="bull" else "看空方向 ✓"
    filter_ok = (h4_dir=="bull" and za['above']) or (h4_dir=="bear" and not za['above'])
    st.markdown(f"""
    <div class="cond-wrap" style="border-left:3px solid {'#00e676' if filter_ok else '#ff5252'}">
        <div class="cond-title">大级别过滤 (4小时)</div>
        <div class="cond-row"><span class="cond-label">4H方向</span>
            <span class="cond-val" style="color:{h4_col}">{h4_txt}</span></div>
        <div class="cond-row"><span class="cond-label">本级方向</span>
            <span class="cond-val {'green' if za['above'] else 'red'}">{'零轴上方 做多' if za['above'] else '零轴下方 做空'}</span></div>
        <div class="cond-row"><span class="cond-label">过滤结果</span>
            <span class="cond-val {'green' if filter_ok else 'red'}">{'✓ 方向一致 允许入场' if filter_ok else '✗ 方向相反 屏蔽信号'}</span></div>
    </div>""", unsafe_allow_html=True)

    # 归零轴状态
    lv_map={"ZERO":"✓ 已归零轴","NEAR":"接近零轴","CONV":"收缩中","FAR":"远离零轴"}
    zc = "#00e676" if za['above'] else "#ff5252"
    pc_cls = "green" if za['prox']<0.2 else "yellow" if za['prox']<0.4 else "gray"
    st.markdown(f"""
    <div class="cond-wrap" style="border-left:3px solid {'#00e676' if za['dir'] not in ('none',) else '#2a4a6a'}">
        <div class="cond-title">归零轴状态</div>
        <div class="cond-row"><span class="cond-label">DIF值</span>
            <span class="cond-val" style="color:{zc}">{za['dif']:.4f}</span></div>
        <div class="cond-row"><span class="cond-label">状态</span>
            <span class="cond-val" style="color:{zc}">{'上方' if za['above'] else '下方'} · {lv_map.get(za['level'],'')}</span></div>
        <div class="cond-row"><span class="cond-label">距零轴</span>
            <span class="cond-val {pc_cls}">{za['prox']*100:.0f}%</span></div>
        <div style="font-size:.7rem;color:#3a6a5a;margin-top:4px">{za['detail']}</div>
    </div>""", unsafe_allow_html=True)

    # EMA52状态
    ec = "#00e676" if et['above'] else "#ff5252"
    st.markdown(f"""
    <div class="cond-wrap" style="border-left:3px solid {'#00e676' if et['touch'] else '#2a4a6a'}">
        <div class="cond-title">EMA52入场位</div>
        <div class="cond-row"><span class="cond-label">当前价</span>
            <span class="cond-val">${et['price']:,.1f}</span></div>
        <div class="cond-row"><span class="cond-label">EMA52</span>
            <span class="cond-val green">${et['ema52']:,.1f}</span></div>
        <div class="cond-row"><span class="cond-label">偏离</span>
            <span class="cond-val {'green' if et['gap']<0.5 else 'yellow'}">{et['gap']:.2f}%</span></div>
        <div class="cond-row"><span class="cond-label">位置</span>
            <span class="cond-val" style="color:{ec}">{'EMA52上方' if et['above'] else 'EMA52下方'}</span></div>
    </div>""", unsafe_allow_html=True)

    # 仓位追踪
    if pos:
        cur = et['price']
        if pos['side']=='long':
            pnl=(cur-pos['entry'])/pos['entry']*100; sc,st_txt="#00e676","多单 LONG"
        else:
            pnl=(pos['entry']-cur)/pos['entry']*100; sc,st_txt="#ff5252","空单 SHORT"
        pc="pnl-pos" if pnl>=0 else "pnl-neg"
        st.markdown(f"""
        <div class="pos-card">
            <div class="pos-title">持仓追踪</div>
            <div class="pos-row"><span class="pos-label">方向</span>
                <span style="font-family:'Share Tech Mono';font-size:.82rem;color:{sc}">{st_txt}</span></div>
            <div class="pos-row"><span class="pos-label">入场价</span>
                <span class="pos-val">${pos['entry']:,.1f}</span></div>
            <div class="pos-row"><span class="pos-label">止损价</span>
                <span style="font-family:'Share Tech Mono';font-size:.82rem;color:#ff5252">${pos['stop']:,.1f}</span></div>
            <div class="pos-row"><span class="pos-label">实时盈亏</span>
                <span class="{pc}">{pnl:+.2f}%</span></div>
            <div class="timestamp" style="margin-top:4px">入场: {pos['time']}</div>
        </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 主程序
# ══════════════════════════════════════════════════════════════════════════════
def main():
    st.markdown('<div class="page-title">⚡ K线动能理论 · 三级别日内合约 v2 &nbsp;|&nbsp; 大级别过滤 · 第一次归零 · 级别升级 · 隐形过滤</div>',
                unsafe_allow_html=True)

    c1,c2,c3,c4,c5,c6 = st.columns([1.2,.7,.7,.7,.7,.7])
    with c1:
        symbol=st.selectbox("",["BTC/USDT","ETH/USDT","SOL/USDT","BNB/USDT"],
                            index=0,label_visibility="collapsed")
    with c2:
        refresh=st.number_input("",10,300,20,5,label_visibility="collapsed")
    with c3:
        st.markdown("<div style='height:4px'></div>",unsafe_allow_html=True)
        if st.button("🔄 刷新"): st.rerun()
    with c4:
        st.markdown("<div style='height:4px'></div>",unsafe_allow_html=True)
        if st.button("❌ 清短单"): st.session_state.pos_short=None
    with c5:
        st.markdown("<div style='height:4px'></div>",unsafe_allow_html=True)
        if st.button("❌ 清中单"): st.session_state.pos_mid=None
    with c6:
        st.markdown("<div style='height:4px'></div>",unsafe_allow_html=True)
        if st.button("❌ 清长单"): st.session_state.pos_long=None

    now_str = datetime.now().strftime("%H:%M:%S")

    with st.spinner("加载数据..."):
        df_h4    = calc_ind(fetch_ohlcv(symbol,'4h', 300))
        df_h1    = calc_ind(fetch_ohlcv(symbol,'1h', 300))
        df_m15   = calc_ind(fetch_ohlcv(symbol,'15m',300))
        df_m5    = calc_ind(fetch_ohlcv(symbol,'5m', 300))
        realtime = fetch_realtime_price(symbol)   # 实时价格

    if df_h4.empty or df_m15.empty:
        st.error("数据获取失败"); time.sleep(10); st.rerun(); return

    # 各级别归零轴
    za_h4  = zero_axis(df_h4)
    za_h1  = zero_axis(df_h1)
    za_m15 = zero_axis(df_m15)

    # 大级别方向
    h4_dir = get_h4_direction(za_h4)

    # 第一次归零轴检测
    first_h1  = detect_first_zero(df_h1)
    first_m15 = detect_first_zero(df_m15)
    first_h4  = detect_first_zero(df_h4)

    # 级别升级检测
    upgrade_h1  = detect_level_upgrade(df_h1,  df_h4)
    upgrade_m15 = detect_level_upgrade(df_m15, df_h1)
    upgrade_h4  = detect_level_upgrade(df_h4,  calc_ind(fetch_ohlcv(symbol,'1d',100)))

    # 隐形形态
    hidden_h1  = detect_hidden(df_h1)
    hidden_m15 = detect_hidden(df_m15)
    hidden_h4  = detect_hidden(df_h4)

    # 背离
    div_h4  = divergence(df_h4,  30)
    div_h1  = divergence(df_h1,  30)
    div_m15 = divergence(df_m15, 25)
    div_m5  = divergence(df_m5,  20)

    # 三级别信号
    res_long  = make_signal(za_h4,  df_m15, st.session_state.pos_long,
                            div_h4,  div_m15, "长单4H",  h4_dir, first_h4,  upgrade_h4,  hidden_h4,  realtime)
    res_mid   = make_signal(za_h1,  df_m15, st.session_state.pos_mid,
                            div_h1,  div_m15, "中单1H",  h4_dir, first_h1,  upgrade_h1,  hidden_h1,  realtime)
    res_short = make_signal(za_m15, df_m5,  st.session_state.pos_short,
                            div_m15, div_m5,  "短单15m", h4_dir, first_m15, upgrade_m15, hidden_m15, realtime)

    # 大方向状态栏
    h4_c = "#00e676" if h4_dir=="bull" else "#ff5252"
    h4_t = "看多 — 只提醒做多信号" if h4_dir=="bull" else "看空 — 只提醒做空信号"
    st.markdown(f"""
    <div style="background:#0b1828;border:1px solid {h4_c}33;border-left:4px solid {h4_c};
                border-radius:6px;padding:10px 16px;margin-bottom:12px;display:flex;align-items:center;gap:16px">
        <span style="font-family:'Share Tech Mono',monospace;font-size:.7rem;color:#3a5a7a;letter-spacing:.15em">4H大方向过滤</span>
        <span style="font-family:'Share Tech Mono',monospace;font-size:.95rem;color:{h4_c};font-weight:700">{h4_t}</span>
        <span style="font-size:.75rem;color:#3a6a5a">DIF={za_h4['dif']:.4f} · 距零轴{za_h4['prox']*100:.0f}%</span>
    </div>""", unsafe_allow_html=True)

    # 合力提醒
    non_blocked = [r for r in [res_long,res_mid,res_short] if not r['blocked']]
    combo_bull = len(non_blocked)>=2 and all("BUY" in r['sig'] for r in non_blocked) and h4_dir=="bull"
    combo_bear = len(non_blocked)>=2 and all("SELL" in r['sig'] for r in non_blocked) and h4_dir=="bear"
    if combo_bull:
        st.markdown(f'<div class="alert-combo flashing"><div class="alert-label" style="color:#ffd740">⚡⚡ 多级别合力做多！{now_str}</div><div class="alert-body" style="color:#ffd740">多个级别同时归零轴看多，且与4H大方向一致 — 高确信度信号</div></div>',unsafe_allow_html=True)
        play_sound("buy","urgent")
    elif combo_bear:
        st.markdown(f'<div class="alert-combo flashing" style="background:#1a0a00;border-color:#ff6d00"><div class="alert-label" style="color:#ff6d00">⚡⚡ 多级别合力做空！{now_str}</div><div class="alert-body" style="color:#ff9800">多个级别同时归零轴看空，且与4H大方向一致 — 高确信度信号</div></div>',unsafe_allow_html=True)
        play_sound("sell","urgent")

    # 三列
    col_s,col_m,col_l = st.columns(3)
    with col_s:
        render_level("短单 · 15m归零轴 + 5m EMA52","#4af0c4",
                     za_m15,res_short,st.session_state.pos_short,
                     now_str,"pos_short","alert_short",h4_dir)
    with col_m:
        render_level("中单 · 1H归零轴 + 15m EMA52","#aa88ff",
                     za_h1,res_mid,st.session_state.pos_mid,
                     now_str,"pos_mid","alert_mid",h4_dir)
    with col_l:
        render_level("长单 · 4H归零轴 + 15m EMA52","#ffca28",
                     za_h4,res_long,st.session_state.pos_long,
                     now_str,"pos_long","alert_long",h4_dir)

    # 图表
    st.markdown('<hr style="border:none;border-top:1px solid #0e2035;margin:10px 0">',unsafe_allow_html=True)
    t1,t2,t3,t4 = st.tabs(["📊 4小时","📊 1小时","📊 15分钟","📊 5分钟"])
    et_m15 = ema52_touch(df_m15, realtime)
    et_m5  = ema52_touch(df_m5,  realtime)
    with t1:
        st.plotly_chart(build_chart(df_h4,f"4H DIF={za_h4['dif']:.4f} 距零轴{za_h4['prox']*100:.0f}%",
                        st.session_state.pos_long),use_container_width=True)
    with t2:
        st.plotly_chart(build_chart(df_h1,f"1H DIF={za_h1['dif']:.4f} 距零轴{za_h1['prox']*100:.0f}%",
                        st.session_state.pos_mid),use_container_width=True)
    with t3:
        st.plotly_chart(build_chart(df_m15,f"15m DIF={za_m15['dif']:.4f} EMA52=${et_m15['ema52']:,.0f}",
                        st.session_state.pos_short),use_container_width=True)
    with t4:
        st.plotly_chart(build_chart(df_m5,f"5m EMA52=${et_m5['ema52']:,.0f}"),
                        use_container_width=True)

    st.markdown(f'<div class="timestamp" style="margin-top:6px;text-align:right">下次刷新: {refresh}s | {now_str}</div>',
                unsafe_allow_html=True)
    time.sleep(refresh)
    st.rerun()

if __name__ == "__main__":
    main()
