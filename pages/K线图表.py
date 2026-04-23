# -*- coding: utf-8 -*-
"""
K线图表页面 - 支持多币种、多周期、多指标
"""

import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import streamlit as st

st.set_page_config(page_title="K线图表", page_icon="📊",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&family=Share+Tech+Mono&display=swap');
html,body,[class*="css"]{background-color:#080c14!important;color:#c0cce0!important;font-family:'Noto Sans SC',sans-serif;}
.stApp{background-color:#080c14;}
#MainMenu,footer,header{visibility:hidden;}
.block-container{padding-top:.8rem;padding-bottom:.5rem;}
.stMultiSelect>div>div{background:#0b1828!important;border-color:#0e2035!important;}
.stSelectbox>div>div{background:#0b1828!important;border-color:#0e2035!important;}
div[data-testid="stHorizontalBlock"]{gap:8px;}
.ctrl-label{font-family:'Share Tech Mono',monospace;font-size:.7rem;color:#ffd740;
            letter-spacing:.1em;margin-bottom:4px;}
.price-bar{background:#0b1828;border:1px solid #0e2035;border-radius:6px;
           padding:8px 16px;margin-bottom:10px;display:flex;align-items:center;gap:24px;}
.price-main{font-family:'Share Tech Mono',monospace;font-size:1.8rem;font-weight:700;}
.price-change{font-family:'Share Tech Mono',monospace;font-size:1rem;}
.price-stat{font-size:.75rem;color:#ffd740;}
.price-val{font-family:'Share Tech Mono',monospace;font-size:.88rem;color:#e0eeff;}
</style>
""", unsafe_allow_html=True)

# ── OKX API ───────────────────────────────────────────────────────────────────
OKX_BASE = "https://www.okx.com"
TF_MAP   = {'1m':'1m','3m':'3m','5m':'5m','15m':'15m','30m':'30m',
            '1H':'1H','2H':'2H','4H':'4H','6H':'6H','8H':'8H','12H':'12H',
            '1D':'1D','2D':'2D','3D':'3D','1W':'1W','1M':'1M'}

COINS = ["BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","DOT","LINK",
         "UNI","ATOM","LTC","BCH","FIL","APT","ARB","OP","INJ","TIA"]

@st.cache_data(ttl=15)
def fetch_ohlcv(symbol, tf, limit=500):
    try:
        inst = f"{symbol}-USDT"
        url  = f"{OKX_BASE}/api/v5/market/candles"
        r    = requests.get(url,
                params={"instId":inst,"bar":tf,"limit":min(limit,300)},
                timeout=12, headers={"User-Agent":"Mozilla/5.0"})
        data = r.json()
        if data.get('code') != '0' or not data.get('data'):
            return pd.DataFrame()
        rows = data['data'][::-1]
        df = pd.DataFrame(rows, columns=['ts','open','high','low','close','volume',
                                          'volCcy','volCcyQuote','confirm'])
        df['time'] = pd.to_datetime(df['ts'].astype(float), unit='ms')
        for c in ['open','high','low','close','volume']:
            df[c] = df[c].astype(float)
        return df[['time','open','high','low','close','volume']]
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3)
def fetch_ticker(symbol):
    try:
        inst = f"{symbol}-USDT-SWAP"
        url  = f"{OKX_BASE}/api/v5/public/mark-price"
        r    = requests.get(url, params={"instId":inst,"instType":"SWAP"},
                            timeout=5, headers={"User-Agent":"Mozilla/5.0"})
        data = r.json()
        if data.get('code') == '0' and data.get('data'):
            mark = float(data['data'][0]['markPx'])
            # 同时取24h行情
            url2 = f"{OKX_BASE}/api/v5/market/ticker"
            r2   = requests.get(url2, params={"instId":f"{symbol}-USDT"},
                                timeout=5, headers={"User-Agent":"Mozilla/5.0"})
            d2 = r2.json()
            if d2.get('code')=='0' and d2.get('data'):
                t = d2['data'][0]
                return {
                    "price": mark,
                    "open24": float(t.get('open24h',mark)),
                    "high24": float(t.get('high24h',mark)),
                    "low24":  float(t.get('low24h',mark)),
                    "vol24":  float(t.get('volCcy24h',0)),
                }
        return None
    except:
        return None

# ── 指标计算 ──────────────────────────────────────────────────────────────────
def calc_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def calc_macd(df, fast=12, slow=26, sig=9):
    dif  = calc_ema(df['close'], fast) - calc_ema(df['close'], slow)
    dea  = calc_ema(dif, sig)
    hist = (dif - dea) * 2
    return dif, dea, hist

def calc_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss
    return 100 - (100 / (1 + rs))

def calc_bollinger(series, period=20, std=2):
    mid   = series.rolling(period).mean()
    sigma = series.rolling(period).std()
    return mid + std*sigma, mid, mid - std*sigma

def calc_kdj(df, n=9):
    low_n  = df['low'].rolling(n).min()
    high_n = df['high'].rolling(n).max()
    rsv    = (df['close'] - low_n) / (high_n - low_n + 1e-9) * 100
    K = rsv.ewm(com=2, adjust=False).mean()
    D = K.ewm(com=2, adjust=False).mean()
    J = 3*K - 2*D
    return K, D, J

def calc_wr(df, period=14):
    high_n = df['high'].rolling(period).max()
    low_n  = df['low'].rolling(period).min()
    return -100 * (high_n - df['close']) / (high_n - low_n + 1e-9)

def calc_cci(df, period=20):
    tp  = (df['high'] + df['low'] + df['close']) / 3
    ma  = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: abs(x - x.mean()).mean())
    return (tp - ma) / (0.015 * mad + 1e-9)

def calc_atr(df, period=14):
    hl  = df['high'] - df['low']
    hc  = abs(df['high'] - df['close'].shift())
    lc  = abs(df['low']  - df['close'].shift())
    tr  = pd.concat([hl,hc,lc], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# ── 图表构建 ──────────────────────────────────────────────────────────────────
def build_chart(df, symbol, tf, indicators, n_candles):
    if df.empty:
        return go.Figure()

    d = df.iloc[-n_candles:].copy()

    # 决定子图数量
    sub_inds = [i for i in indicators if i in
                ("MACD","RSI","KDJ","W%R","CCI","ATR","成交量")]
    n_rows   = 1 + len(sub_inds)
    heights  = [0.55] + [round(0.45/max(len(sub_inds),1), 3)] * len(sub_inds) if sub_inds else [1.0]

    subplot_titles = [f"{symbol}/USDT  {tf}"] + sub_inds
    fig = make_subplots(
        rows=n_rows, cols=1,
        shared_xaxes=True,
        row_heights=heights,
        vertical_spacing=0.03,
        subplot_titles=subplot_titles,
    )

    # ── K线 ──────────────────────────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=d['time'], open=d['open'], high=d['high'],
        low=d['low'], close=d['close'], name="K线",
        increasing_fillcolor="#00c853", increasing_line_color="#00c853",
        decreasing_fillcolor="#d50000", decreasing_line_color="#d50000",
        line_width=1,
    ), row=1, col=1)

    # ── 均线 ─────────────────────────────────────────────────────────────
    ema_configs = {
        "EMA7":  ("#ff9800", 7,  1.2),
        "EMA13": ("#e040fb", 13, 1.2),
        "EMA24": ("#aa44ff", 24, 1.5),
        "EMA52": ("#00e676", 52, 2.0),
        "EMA99": ("#4af0c4", 99, 1.5),
        "EMA200":("#ffd740", 200,1.5),
    }
    for name, (color, span, width) in ema_configs.items():
        if name in indicators:
            ema = calc_ema(df['close'], span)
            fig.add_trace(go.Scatter(
                x=d['time'], y=ema.iloc[-n_candles:],
                name=name, line=dict(color=color, width=width), opacity=0.85
            ), row=1, col=1)

    # ── 布林带 ───────────────────────────────────────────────────────────
    if "布林带" in indicators:
        upper, mid, lower = calc_bollinger(df['close'])
        fig.add_trace(go.Scatter(x=d['time'], y=upper.iloc[-n_candles:],
            name="BB上", line=dict(color="#4af0c4",width=1,dash="dot"), opacity=0.6), row=1, col=1)
        fig.add_trace(go.Scatter(x=d['time'], y=mid.iloc[-n_candles:],
            name="BB中", line=dict(color="#888",width=1,dash="dot"), opacity=0.4,
            fill=None), row=1, col=1)
        fig.add_trace(go.Scatter(x=d['time'], y=lower.iloc[-n_candles:],
            name="BB下", line=dict(color="#4af0c4",width=1,dash="dot"), opacity=0.6,
            fill='tonexty', fillcolor="rgba(74,240,196,0.04)"), row=1, col=1)

    # ── 子图指标 ──────────────────────────────────────────────────────────
    for idx, ind in enumerate(sub_inds):
        row = idx + 2

        if ind == "成交量":
            vcols = ["#00c853" if c>=o else "#d50000"
                     for c,o in zip(d['close'], d['open'])]
            fig.add_trace(go.Bar(x=d['time'], y=d['volume'],
                name="成交量", marker_color=vcols, opacity=0.7), row=row, col=1)

        elif ind == "MACD":
            dif, dea, hist = calc_macd(df)
            hc = ["#00c853" if v>=0 else "#d50000" for v in hist.iloc[-n_candles:]]
            fig.add_trace(go.Bar(x=d['time'], y=hist.iloc[-n_candles:],
                name="MACD柱", marker_color=hc, opacity=0.75), row=row, col=1)
            fig.add_trace(go.Scatter(x=d['time'], y=dif.iloc[-n_candles:],
                name="DIF", line=dict(color="#e8f0ff",width=1.5)), row=row, col=1)
            fig.add_trace(go.Scatter(x=d['time'], y=dea.iloc[-n_candles:],
                name="DEA", line=dict(color="#ffd740",width=1.2)), row=row, col=1)
            fig.add_hline(y=0, line_color="#2a4a6a", line_width=1, row=row, col=1)

        elif ind == "RSI":
            rsi = calc_rsi(df['close'])
            fig.add_trace(go.Scatter(x=d['time'], y=rsi.iloc[-n_candles:],
                name="RSI", line=dict(color="#aa88ff",width=1.5)), row=row, col=1)
            fig.add_hline(y=70, line_color="#ff525244", line_width=1,
                          line_dash="dot", row=row, col=1)
            fig.add_hline(y=30, line_color="#00e67644", line_width=1,
                          line_dash="dot", row=row, col=1)
            fig.add_hline(y=50, line_color="#ffffff22", line_width=1, row=row, col=1)

        elif ind == "KDJ":
            K, D, J = calc_kdj(df)
            fig.add_trace(go.Scatter(x=d['time'], y=K.iloc[-n_candles:],
                name="K", line=dict(color="#ffd740",width=1.3)), row=row, col=1)
            fig.add_trace(go.Scatter(x=d['time'], y=D.iloc[-n_candles:],
                name="D", line=dict(color="#ff9800",width=1.3)), row=row, col=1)
            fig.add_trace(go.Scatter(x=d['time'], y=J.iloc[-n_candles:],
                name="J", line=dict(color="#4af0c4",width=1)), row=row, col=1)
            fig.add_hline(y=80, line_color="#ff525233", line_width=1, row=row, col=1)
            fig.add_hline(y=20, line_color="#00e67633", line_width=1, row=row, col=1)

        elif ind == "W%R":
            wr = calc_wr(df)
            fig.add_trace(go.Scatter(x=d['time'], y=wr.iloc[-n_candles:],
                name="W%R", line=dict(color="#ff9800",width=1.3)), row=row, col=1)
            fig.add_hline(y=-20, line_color="#ff525233", line_width=1, row=row, col=1)
            fig.add_hline(y=-80, line_color="#00e67633", line_width=1, row=row, col=1)

        elif ind == "CCI":
            cci = calc_cci(df)
            fig.add_trace(go.Scatter(x=d['time'], y=cci.iloc[-n_candles:],
                name="CCI", line=dict(color="#e040fb",width=1.3)), row=row, col=1)
            fig.add_hline(y=100,  line_color="#ff525233", line_width=1, row=row, col=1)
            fig.add_hline(y=-100, line_color="#00e67633", line_width=1, row=row, col=1)

        elif ind == "ATR":
            atr = calc_atr(df)
            fig.add_trace(go.Scatter(x=d['time'], y=atr.iloc[-n_candles:],
                name="ATR", line=dict(color="#4af0c4",width=1.3)), row=row, col=1)

    # ── 布局 ─────────────────────────────────────────────────────────────
    fig.update_layout(
        paper_bgcolor="#080c14",
        plot_bgcolor="#0b1220",
        font=dict(color="#7090b0", size=11, family="Share Tech Mono"),
        xaxis_rangeslider_visible=False,
        legend=dict(
            orientation="h", y=1.02, x=0,
            font=dict(size=10), bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=10, r=10, t=28, b=8),
        height=680 + len(sub_inds) * 150,
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#0d1e2e", font_color="#c0cce0"),
    )
    for i in range(1, n_rows+1):
        fig.update_xaxes(gridcolor="#0d1e2e", row=i, col=1, showgrid=True)
        fig.update_yaxes(gridcolor="#0d1e2e", row=i, col=1, showgrid=True)

    # 子图标题颜色
    for ann in fig.layout.annotations:
        ann.font.color = "#ffd740"
        ann.font.size  = 11

    return fig

# ══════════════════════════════════════════════════════════════════════════════
# 主页面
# ══════════════════════════════════════════════════════════════════════════════
def main():
    st.markdown('<p style="font-family:\'Share Tech Mono\',monospace;font-size:.95rem;color:#4af0c4;'
                'letter-spacing:.18em;border-bottom:1px solid #0e2a3a;padding-bottom:6px;margin-bottom:10px">'
                '📊 K线图表 · 免费实时行情</p>', unsafe_allow_html=True)

    # ── 控制栏 ────────────────────────────────────────────────────────────
    c1,c2,c3,c4,c5 = st.columns([1, 1, 1.2, 2.5, 0.8])

    with c1:
        st.markdown('<div class="ctrl-label">币种</div>', unsafe_allow_html=True)
        coin = st.selectbox("", COINS, index=0, label_visibility="collapsed")

    with c2:
        st.markdown('<div class="ctrl-label">时间周期</div>', unsafe_allow_html=True)
        tf = st.selectbox("", list(TF_MAP.keys()), index=7,
                          label_visibility="collapsed")  # 默认4H

    with c3:
        st.markdown('<div class="ctrl-label">显示K线数量</div>', unsafe_allow_html=True)
        n_candles = st.select_slider("", options=[50,100,150,200,300],
                                     value=150, label_visibility="collapsed")

    with c4:
        st.markdown('<div class="ctrl-label">叠加指标（可多选）</div>', unsafe_allow_html=True)
        all_inds = ["EMA7","EMA13","EMA24","EMA52","EMA99","EMA200",
                    "布林带","MACD","RSI","KDJ","W%R","CCI","ATR","成交量"]
        indicators = st.multiselect("", all_inds,
                                    default=["EMA52","MACD","成交量"],
                                    label_visibility="collapsed")

    with c5:
        st.markdown('<div class="ctrl-label">&nbsp;</div>', unsafe_allow_html=True)
        if st.button("🔄 刷新", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # ── 实时价格栏 ────────────────────────────────────────────────────────
    symbol  = coin
    ticker  = fetch_ticker(symbol)
    df      = fetch_ohlcv(symbol, tf, limit=500)

    if ticker:
        price     = ticker['price']
        chg       = price - ticker['open24']
        chg_pct   = chg / ticker['open24'] * 100
        chg_color = "#00e676" if chg >= 0 else "#ff5252"
        chg_sign  = "+" if chg >= 0 else ""
        st.markdown(f"""
        <div class="price-bar">
            <div>
                <div style="font-size:.65rem;color:#ffd740;letter-spacing:.1em">{symbol}/USDT 标记价格</div>
                <div class="price-main" style="color:{chg_color}">${price:,.2f}</div>
            </div>
            <div class="price-change" style="color:{chg_color}">{chg_sign}{chg_pct:.2f}%</div>
            <div style="width:1px;height:40px;background:#0e2035;margin:0 8px"></div>
            <div><div class="price-stat">24H最高</div><div class="price-val">${ticker['high24']:,.2f}</div></div>
            <div><div class="price-stat">24H最低</div><div class="price-val">${ticker['low24']:,.2f}</div></div>
            <div><div class="price-stat">24H成交量</div><div class="price-val">{ticker['vol24']:,.0f} {symbol}</div></div>
            <div style="margin-left:auto"><div class="price-stat">更新时间</div>
                <div style="font-family:'Share Tech Mono',monospace;font-size:.78rem;color:#5a8aaa">
                    {datetime.now().strftime('%H:%M:%S')}</div></div>
        </div>
        """, unsafe_allow_html=True)

    # ── K线图 ─────────────────────────────────────────────────────────────
    if df.empty:
        st.error(f"获取 {symbol}/USDT {tf} 数据失败，请稍后刷新")
        return

    fig = build_chart(df, symbol, tf, indicators, n_candles)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown(f'<div style="font-family:\'Share Tech Mono\',monospace;font-size:.68rem;'
                f'color:#ffd740;text-align:right;margin-top:-8px">'
                f'数据来源: OKX · {len(df)}根K线已加载 · 每15秒自动刷新</div>',
                unsafe_allow_html=True)

    # 自动刷新
    import time
    time.sleep(15)
    st.rerun()

if __name__ == "__main__":
    main()
