"""
推送通知模块
支持企业微信群机器人 Webhook
"""
import requests
import json
from datetime import datetime


def send_wecom(webhook_url, title, content, is_urgent=False):
    """
    发送企业微信群机器人消息
    webhook_url: 企业微信群机器人的webhook地址
    """
    if not webhook_url:
        return False

    # 企业微信 markdown 消息
    msg = {
        "msgtype": "markdown",
        "markdown": {
            "content": content
        }
    }

    try:
        resp = requests.post(
            webhook_url,
            data=json.dumps(msg),
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        result = resp.json()
        return result.get('errcode') == 0
    except Exception as e:
        print(f"企业微信推送失败: {e}")
        return False


def format_signal_message(symbol_display, signals_by_tf, conclusion, price, is_high_prob=False):
    """格式化信号消息"""
    now = datetime.now().strftime("%m-%d %H:%M")

    if is_high_prob:
        title = f"🎯 高概率信号 {symbol_display}"
    else:
        title = f"⚡ MACD信号 {symbol_display}"

    tf_display = {
        '5m':'5分', '15m':'15分', '30m':'30分',
        '1h':'1时', '2h':'2时',   '4h':'4时'
    }
    tf_order = ['5m', '15m', '30m', '1h', '2h', '4h']

    lines = [
        f"## {title}",
        f"**{symbol_display}/USDT 永续** | {now}",
        "",
        "**多级别MACD状态：**",
    ]

    for tf in tf_order:
        sig = signals_by_tf.get(tf)
        if sig is None:
            continue
        ratio = sig['dist_ratio']
        direction = sig['direction']
        tf_name = tf_display.get(tf, tf)

        icon = "🔥" if abs(ratio) >= 3 else ("⚡" if abs(ratio) >= 2 else "▪")

        div_note = ""
        if sig['divergence'] == -1:
            div_note = " ⚠顶背离"
        elif sig['divergence'] == 1:
            div_note = " ✅底背离"
        if sig['hidden_div'] == -1:
            div_note += " 🔶隐形顶"
        elif sig['hidden_div'] == 1:
            div_note += " 🔶隐形底"

        cross_note = ""
        if sig['zero_cross'] == 1:
            cross_note = " 📈穿零轴↑"
        elif sig['zero_cross'] == -1:
            cross_note = " 📉穿零轴↓"

        near_note = " 🎯近零轴" if sig['near_zero'] else ""

        lines.append(
            f"> {icon} **{tf_name}** {direction}{abs(ratio):.1f}倍"
            f"{div_note}{cross_note}{near_note}"
        )

    lines.append("")

    # 4H环境
    h4 = signals_by_tf.get('4h')
    if h4:
        h4_dir = "多头↑" if h4['macd'] > 0 else "空头↓"
        lines.append(f"**4H环境：** {h4_dir}（{h4['dist_ratio']:.1f}倍）")

    # EMA52
    h1 = signals_by_tf.get('1h')
    if h1 and h1.get('ema52'):
        e = h1['ema52']
        pos = "上方" if e['above'] else "下方"
        near = " ⭐触EMA52！" if e['near_ema52'] else ""
        lines.append(f"**EMA52：** 价格在{pos} {e['dist_pct']:.1f}% 斜率{e['slope']}{near}")

    # 零轴黏合
    sticky_tfs = [tf for tf, sig in signals_by_tf.items()
                  if sig and sig['sticky_bars'] > 0]
    if sticky_tfs:
        lines.append(f"**零轴黏合：** {', '.join(sticky_tfs)} 注意突破方向")

    lines.append("")
    lines.append(f"**综合判断：{conclusion}**")
    lines.append(f"**当前价：** ${price:,.4f}")

    # 高概率信号止损止盈
    if is_high_prob:
        for tf, sig in signals_by_tf.items():
            if sig and sig['high_prob'] and sig['atr'] > 0:
                atr = sig['atr']
                if '做多' in conclusion:
                    sl = round(price - atr * 1.5, 4)
                    tp = round(price + atr * 3.0, 4)
                    lines.append(f"**参考止损：** ${sl:,.4f}")
                    lines.append(f"**参考目标：** ${tp:,.4f}")
                elif '做空' in conclusion:
                    sl = round(price + atr * 1.5, 4)
                    tp = round(price - atr * 3.0, 4)
                    lines.append(f"**参考止损：** ${sl:,.4f}")
                    lines.append(f"**参考目标：** ${tp:,.4f}")
                break

    content = "\n".join(lines)
    return title, content


def format_zero_sticky_alert(symbol_display, timeframe, bars, upper_tf_direction, price):
    """格式化零轴黏合预警"""
    now = datetime.now().strftime("%m-%d %H:%M")
    tf_display = {
        '5m':'5分钟', '15m':'15分钟', '30m':'30分钟',
        '1h':'1小时', '2h':'2小时',   '4h':'4小时'
    }
    tf_name = tf_display.get(timeframe, timeframe)
    title = f"⏳ 零轴黏合 {symbol_display}"
    content = (
        f"## ⏳ 零轴黏合预警\n"
        f"**{symbol_display}/USDT** | {now}\n\n"
        f"**{tf_name}** MACD零轴黏合 **{bars}根K线**\n"
        f"上级别方向：{upper_tf_direction}\n"
        f"建议：等待方向突破后跟进\n\n"
        f"**当前价：** ${price:,.4f}"
    )
    return title, content


# 兼容旧接口名称
send_dingtalk = send_wecom
