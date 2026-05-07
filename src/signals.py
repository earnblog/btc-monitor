"""
K线动能理论信号计算模块
计算MACD远离零轴、背离、EMA52、零轴穿越等信号
"""
import numpy as np
import pandas as pd


# ── 基础指标 ──────────────────────────────────────────────────

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def calc_macd(close, fast=12, slow=26, signal=9):
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow      # 白线 DIF
    signal_line = ema(macd_line, signal) # 黄线 DEA
    histogram = (macd_line - signal_line) * 2
    return macd_line, signal_line, histogram

def calc_ema52(close):
    return ema(close, 52)

def calc_atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ── 核心信号判断 ──────────────────────────────────────────────

def calc_distance_ratio(macd_line, lookback=60):
    """
    计算MACD白线距零轴的倍数
    当前值 / 近期绝对值均值
    返回正数=上方，负数=下方
    """
    vals = macd_line.values
    n = len(vals)
    ratios = np.zeros(n)
    for i in range(lookback, n):
        scale = np.nanmean(np.abs(vals[max(0, i-lookback):i]))
        if scale > 0:
            ratios[i] = vals[i] / scale
    return pd.Series(ratios, index=macd_line.index)


def detect_divergence(close, macd_line, lookback=20):
    """
    检测背离
    返回：1=底背离，-1=顶背离，0=无
    """
    c = close.values
    m = macd_line.values
    n = len(c)
    result = np.zeros(n)

    for i in range(lookback * 2, n):
        pw = c[i-lookback:i+1]
        mid = lookback // 2

        # 顶背离：价格创新高，MACD未创新高
        if c[i] == pw.max() and c[i] > c[i-lookback] * 1.02:
            prev_m_high = np.max(m[i-lookback:i-mid])
            curr_m_high = np.max(m[i-3:i+1])
            if prev_m_high > 0 and curr_m_high < prev_m_high * 0.80:
                result[i] = -1

        # 底背离：价格创新低，MACD未创新低
        if c[i] == pw.min() and c[i] < c[i-lookback] * 0.98:
            prev_m_low = np.min(m[i-lookback:i-mid])
            curr_m_low = np.min(m[i-3:i+1])
            if prev_m_low < 0 and curr_m_low > prev_m_low * 0.80:
                result[i] = 1

    return pd.Series(result, index=close.index)


def detect_hidden_divergence(close, macd_line, lookback=20):
    """
    检测隐形背离（书里叫"送钱形态"）
    隐形顶背离：价格未创新高，但MACD更高 → 继续上涨
    隐形底背离：价格未创新低，但MACD更低 → 继续下跌
    返回：1=隐形底背离（看多），-1=隐形顶背离（看空）
    """
    c = close.values
    m = macd_line.values
    n = len(c)
    result = np.zeros(n)

    for i in range(lookback * 2, n):
        mid = lookback // 2

        # 隐形顶背离：价格回调（未破前高），但MACD比前次更强
        prev_high_p = np.max(c[i-lookback:i-mid])
        curr_high_p = np.max(c[i-mid:i+1])
        prev_high_m = np.max(m[i-lookback:i-mid])
        curr_high_m = np.max(m[i-mid:i+1])
        if (curr_high_p < prev_high_p and
                prev_high_m > 0 and curr_high_m > prev_high_m * 1.1):
            result[i] = -1  # 隐形顶背离，说明多头仍强，做空需谨慎

        # 隐形底背离：价格反弹（未破前低），但MACD比前次更弱
        prev_low_p = np.min(c[i-lookback:i-mid])
        curr_low_p = np.min(c[i-mid:i+1])
        prev_low_m = np.min(m[i-lookback:i-mid])
        curr_low_m = np.min(m[i-mid:i+1])
        if (curr_low_p > prev_low_p and
                prev_low_m < 0 and curr_low_m < prev_low_m * 1.1):
            result[i] = 1   # 隐形底背离，说明空头仍强，做多需谨慎

    return pd.Series(result, index=close.index)


def detect_zero_cross(macd_line):
    """检测零轴穿越：1=向上穿越，-1=向下穿越"""
    vals = macd_line.values
    result = np.zeros(len(vals))
    for i in range(1, len(vals)):
        if vals[i] > 0 and vals[i-1] <= 0:
            result[i] = 1
        elif vals[i] < 0 and vals[i-1] >= 0:
            result[i] = -1
    return pd.Series(result, index=macd_line.index)


def count_zero_crossings(macd_line, lookback=200):
    """
    统计当前方向下是第几次归零轴
    从最近一次大幅离开零轴开始数
    """
    vals = macd_line.values
    n = len(vals)
    counts = np.zeros(n)

    for i in range(lookback, n):
        # 当前方向
        direction = 1 if vals[i] > 0 else -1
        count = 0
        j = i
        while j > max(i-lookback, 0):
            # 找零轴穿越点
            if direction == 1:
                # 往回找从负到正的穿越
                if vals[j] <= 0 and vals[j-1] > 0 if j > 0 else False:
                    count += 1
            else:
                if vals[j] >= 0 and vals[j-1] < 0 if j > 0 else False:
                    count += 1
            j -= 1
        counts[i] = count + 1  # 当前是第count+1次
    return pd.Series(counts, index=macd_line.index)


def detect_zero_axis_sticky(macd_line, lookback=30, threshold_ratio=0.3):
    """
    检测零轴黏合：MACD在零轴附近反复穿越
    返回黏合持续根数，0=无黏合
    """
    vals = macd_line.values
    n = len(vals)
    result = np.zeros(n)
    scale_series = pd.Series(vals).abs().rolling(60).mean().values

    for i in range(lookback, n):
        scale = scale_series[i] if scale_series[i] > 0 else 1
        thr = scale * threshold_ratio
        # 近lookback根K线都在零轴附近
        window = vals[i-lookback:i+1]
        if np.all(np.abs(window) < thr * 2):
            # 统计穿越次数
            crosses = sum(
                1 for k in range(1, len(window))
                if window[k] * window[k-1] < 0
            )
            if crosses >= 3:
                result[i] = lookback

    return pd.Series(result, index=macd_line.index)


def check_ema52_state(close, ema52):
    """
    检查EMA52状态
    返回：方向（上/下），斜率（向上/水平/向下），距离百分比
    """
    latest_close = close.iloc[-1]
    latest_ema52 = ema52.iloc[-1]

    # 价格在EMA52上方还是下方
    above = latest_close > latest_ema52
    dist_pct = abs(latest_close - latest_ema52) / latest_ema52 * 100

    # EMA52斜率（用最近10根K线判断）
    if len(ema52) >= 10:
        slope = (ema52.iloc[-1] - ema52.iloc[-10]) / ema52.iloc[-10] * 100
        if slope > 0.5:
            slope_label = "向上↑"
        elif slope < -0.5:
            slope_label = "向下↓"
        else:
            slope_label = "水平→"
    else:
        slope_label = "水平→"

    # 价格是否触及EMA52（误差1%以内）
    near_ema52 = dist_pct < 1.0

    return {
        "above": above,
        "dist_pct": round(dist_pct, 2),
        "slope": slope_label,
        "near_ema52": near_ema52,
        "ema52_value": round(latest_ema52, 4)
    }


# ── 综合信号分析 ──────────────────────────────────────────────

def analyze_symbol_timeframe(df, timeframe):
    """
    对单个币种单个周期进行完整分析
    返回信号字典
    """
    if len(df) < 100:
        return None

    close = df['close']
    high  = df['high']
    low   = df['low']
    volume = df['volume']

    # 计算所有指标
    macd_line, signal_line, histogram = calc_macd(close)
    ema52 = calc_ema52(close)
    atr_val = calc_atr(high, low, close)
    dist_ratio = calc_distance_ratio(macd_line)
    divergence = detect_divergence(close, macd_line)
    hidden_div = detect_hidden_divergence(close, macd_line)
    zero_cross = detect_zero_cross(macd_line)
    sticky = detect_zero_axis_sticky(macd_line)

    # 最新值
    latest_macd = macd_line.iloc[-1]
    latest_dist = dist_ratio.iloc[-1]
    latest_div = divergence.iloc[-1]
    latest_hidden = hidden_div.iloc[-1]
    latest_cross = zero_cross.iloc[-1]
    latest_sticky = sticky.iloc[-1]
    latest_close = close.iloc[-1]
    latest_atr = atr_val.iloc[-1]

    # EMA52状态
    ema52_state = check_ema52_state(close, ema52)

    # 是否即将触及零轴（距离 < 0.3倍均值）
    scale = float(macd_line.abs().rolling(60).mean().iloc[-1])
    near_zero = abs(latest_macd) < scale * 0.3 if scale > 0 else False

    # 归零轴次数（简化版：看最近100根内从当前方向穿越零轴次数）
    direction = 1 if latest_macd > 0 else -1
    recent_macd = macd_line.iloc[-100:].values
    cross_count = 0
    for k in range(1, len(recent_macd)):
        if direction == 1 and recent_macd[k] > 0 and recent_macd[k-1] <= 0:
            cross_count += 1
        elif direction == -1 and recent_macd[k] < 0 and recent_macd[k-1] >= 0:
            cross_count += 1
    zero_cross_nth = cross_count if cross_count > 0 else 1

    # 高概率信号：归零轴 + EMA52
    high_prob = (
        near_zero and
        ema52_state['near_ema52'] and
        zero_cross_nth <= 2
    )

    return {
        "timeframe":       timeframe,
        "macd":            round(float(latest_macd), 4),
        "dist_ratio":      round(float(latest_dist), 2),
        "direction":       "上方" if latest_macd > 0 else "下方",
        "divergence":      int(latest_div),      # 1=底背离 -1=顶背离
        "hidden_div":      int(latest_hidden),
        "zero_cross":      int(latest_cross),    # 本根K线是否穿越零轴
        "near_zero":       near_zero,
        "sticky_bars":     int(latest_sticky),
        "zero_cross_nth":  zero_cross_nth,
        "ema52":           ema52_state,
        "high_prob":       high_prob,
        "close":           round(float(latest_close), 4),
        "atr":             round(float(latest_atr), 4) if not np.isnan(latest_atr) else 0,
        "histogram":       round(float(histogram.iloc[-1]), 4),
        "hist_shrinking":  float(histogram.iloc[-1]) < float(histogram.iloc[-2]) if len(histogram) >= 2 else False,
    }


def generate_conclusion(signals_by_tf, symbol):
    """
    根据多个周期的信号，生成综合判断结论
    signals_by_tf: {timeframe: signal_dict}
    """
    if not signals_by_tf:
        return "⏳ 数据不足"

    valid = {k: v for k, v in signals_by_tf.items() if v is not None}
    if not valid:
        return "⏳ 数据不足"

    # 统计各周期方向
    above_count = sum(1 for v in valid.values() if v['macd'] > 0)
    below_count = sum(1 for v in valid.values() if v['macd'] < 0)
    total = len(valid)

    # 高距离周期数（倍数≥2）
    high_dist_above = sum(1 for v in valid.values() if v['dist_ratio'] >= 2)
    high_dist_below = sum(1 for v in valid.values() if v['dist_ratio'] <= -2)

    # 背离情况
    has_top_div    = any(v['divergence'] == -1 for v in valid.values())
    has_bot_div    = any(v['divergence'] == 1  for v in valid.values())
    has_hidden_top = any(v['hidden_div'] == -1 for v in valid.values())
    has_hidden_bot = any(v['hidden_div'] == 1  for v in valid.values())

    # 4H方向
    h4_signal = valid.get('4h') or valid.get('4H')
    h4_above = h4_signal and h4_signal['macd'] > 0 if h4_signal else None

    # 高概率信号
    has_high_prob = any(v['high_prob'] for v in valid.values())

    # 零轴黏合
    has_sticky = any(v['sticky_bars'] > 0 for v in valid.values())

    # ── 生成结论 ──
    if has_high_prob:
        # 找触发高概率信号的周期
        hp_tfs = [tf for tf, v in valid.items() if v['high_prob']]
        hp_tf  = hp_tfs[0] if hp_tfs else ''
        hp_sig = valid[hp_tf]
        if hp_sig['macd'] > 0:
            return "🎯 高概率做多【归零轴+EMA52共振】"
        else:
            return "🎯 高概率做空【归零轴+EMA52共振】"

    if has_sticky:
        return "⏳ 零轴黏合，等待方向突破"

    # 做空判断
    if above_count >= 3 and high_dist_above >= 2:
        if has_top_div and (h4_above is True):
            return "🔴 强烈建议做空（多级别高位+顶背离+4H配合）"
        elif has_top_div:
            return "🔴 建议做空（多级别高位+顶背离）"
        elif has_hidden_top:
            return "⚠️ 观察做空（检测到隐形顶背离，可能继续涨）"
        elif h4_above is True:
            return "🟠 建议做空，注意风险（4H多头环境，逆势）"
        else:
            return "🟠 建议做空（小周期高位共振）"

    # 做多判断
    if below_count >= 3 and high_dist_below >= 2:
        if has_bot_div and (h4_above is False):
            return "🟢 强烈建议做多（多级别低位+底背离+4H配合）"
        elif has_bot_div:
            return "🟢 建议做多（多级别低位+底背离）"
        elif has_hidden_bot:
            return "⚠️ 观察做多（检测到隐形底背离，可能继续跌）"
        elif h4_above is False:
            return "🟡 建议做多，注意风险（4H空头环境，逆势）"
        else:
            return "🟡 建议做多（小周期低位共振）"

    # 单级别信号
    if high_dist_above >= 1:
        return "🟠 部分周期高位，信号较弱，可观察"
    if high_dist_below >= 1:
        return "🟡 部分周期低位，信号较弱，可观察"

    return "⏳ 暂无明显信号，建议等待"
