"""
主监控脚本
由 GitHub Actions 每5分钟调用一次
计算信号，推送钉钉，保存结果到 data/signals.json
"""
import os
import json
import time
from datetime import datetime, timezone

# 确保src目录在路径中
import sys
sys.path.insert(0, os.path.dirname(__file__))

from src.okx_data import get_top_symbols, get_all_timeframes
from src.signals import analyze_symbol_timeframe, generate_conclusion
from src.notifier import (send_dingtalk, format_signal_message,
                           format_zero_sticky_alert)

# ── 配置 ──────────────────────────────────────────────────────
TIMEFRAMES      = ['5m', '15m', '30m', '1h', '2h', '4h']
MIN_VOLUME_USD  = 100_000_000   # 最低交易量1亿USDT
MAX_SYMBOLS     = 60            # 最多监控60个币种
DIST_THRESHOLD  = 2.0           # 距零轴倍数触发阈值
URGENT_THRESHOLD = 3.5          # 高优先级阈值

# 冷却：同币种同周期同方向4小时内不重复推送
COOLDOWN_HOURS  = 4

WECOM_WEBHOOK = os.environ.get('WECOM_WEBHOOK', '')
DATA_DIR         = os.path.join(os.path.dirname(__file__), 'data')


def load_sent_cache():
    """加载已推送记录，用于冷却判断"""
    cache_file = os.path.join(DATA_DIR, 'sent_cache.json')
    if os.path.exists(cache_file):
        try:
            with open(cache_file) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_sent_cache(cache):
    os.makedirs(DATA_DIR, exist_ok=True)
    cache_file = os.path.join(DATA_DIR, 'sent_cache.json')
    with open(cache_file, 'w') as f:
        json.dump(cache, f)


def is_cooldown(cache, key):
    """检查是否在冷却期内"""
    if key not in cache:
        return False
    last_sent = datetime.fromisoformat(cache[key])
    now = datetime.now()
    hours_passed = (now - last_sent).total_seconds() / 3600
    return hours_passed < COOLDOWN_HOURS


def run_monitor():
    print(f"\n{'='*50}")
    print(f"MACD监控运行中 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")

    os.makedirs(DATA_DIR, exist_ok=True)

    # 加载推送缓存
    sent_cache = load_sent_cache()

    # 获取热门币种
    print("获取热门币种...")
    symbols = get_top_symbols(MIN_VOLUME_USD, MAX_SYMBOLS)
    print(f"筛选出 {len(symbols)} 个交易量过亿的永续合约")

    if not symbols:
        print("未获取到币种数据，退出")
        return

    all_results = {}
    push_count  = 0

    for i, sym in enumerate(symbols):
        inst_id      = sym['symbol']
        display_name = sym['display']
        price        = sym['last_price']

        print(f"[{i+1}/{len(symbols)}] 分析 {display_name}...")

        # 获取所有周期K线
        klines = get_all_timeframes(inst_id, TIMEFRAMES)
        if not klines:
            continue

        # 分析每个周期
        signals_by_tf = {}
        for tf in TIMEFRAMES:
            df = klines.get(tf)
            if df is not None:
                sig = analyze_symbol_timeframe(df, tf)
                if sig:
                    signals_by_tf[tf] = sig

        if not signals_by_tf:
            continue

        # 生成综合结论
        conclusion = generate_conclusion(signals_by_tf, inst_id)

        # 保存结果
        all_results[inst_id] = {
            'display':    display_name,
            'price':      price,
            'volume_24h': sym['volume_24h'],
            'signals':    signals_by_tf,
            'conclusion': conclusion,
            'updated_at': datetime.now().isoformat(),
        }

        # ── 判断是否需要推送 ──

        # 1. 高概率信号（最高优先级，无冷却）
        has_high_prob = any(
            v['high_prob'] for v in signals_by_tf.values()
        )
        if has_high_prob and WECOM_WEBHOOK:
            title, content = format_signal_message(
                display_name, signals_by_tf, conclusion, price, is_high_prob=True
            )
            if send_dingtalk(WECOM_WEBHOOK, title, content, is_urgent=True):
                print(f"  🎯 高概率信号推送: {display_name}")
                push_count += 1

        # 2. 普通远离零轴信号（有冷却）
        for tf, sig in signals_by_tf.items():
            if sig is None:
                continue
            ratio = abs(sig['dist_ratio'])
            if ratio < DIST_THRESHOLD:
                continue

            direction = 'short' if sig['macd'] > 0 else 'long'
            cache_key = f"{inst_id}_{tf}_{direction}"

            # 冷却检查
            if is_cooldown(sent_cache, cache_key):
                continue

            # 高优先级（≥3.5倍）或普通（≥2倍）
            if ratio >= DIST_THRESHOLD and WECOM_WEBHOOK:
                title, content = format_signal_message(
                    display_name, signals_by_tf, conclusion, price
                )
                if send_dingtalk(WECOM_WEBHOOK, title, content):
                    sent_cache[cache_key] = datetime.now().isoformat()
                    print(f"  ⚡ 信号推送: {display_name} {tf} {ratio:.1f}倍")
                    push_count += 1
                    break  # 每个币种每次最多推一条普通信号

        # 3. 零轴黏合预警（有冷却）
        for tf, sig in signals_by_tf.items():
            if sig and sig['sticky_bars'] > 0:
                cache_key = f"{inst_id}_{tf}_sticky"
                if not is_cooldown(sent_cache, cache_key):
                    # 找上级别方向
                    tf_order = ['5m', '15m', '30m', '1h', '2h', '4h']
                    tf_idx = tf_order.index(tf) if tf in tf_order else -1
                    upper_dir = "未知"
                    if tf_idx < len(tf_order) - 1:
                        upper_tf = tf_order[tf_idx + 1]
                        upper_sig = signals_by_tf.get(upper_tf)
                        if upper_sig:
                            upper_dir = "多头↑" if upper_sig['macd'] > 0 else "空头↓"

                    if WECOM_WEBHOOK:
                        title, content = format_zero_sticky_alert(
                            display_name, tf, sig['sticky_bars'], upper_dir, price
                        )
                        if send_dingtalk(WECOM_WEBHOOK, title, content):
                            sent_cache[cache_key] = datetime.now().isoformat()
                            print(f"  ⏳ 零轴黏合推送: {display_name} {tf}")
                            push_count += 1

        time.sleep(0.2)  # 避免请求太快

    # 保存信号数据（供网页读取）
    output = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'symbol_count': len(all_results),
        'symbols': all_results,
    }

    signals_file = os.path.join(DATA_DIR, 'signals.json')
    with open(signals_file, 'w') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 记录运行时间
    with open(os.path.join(DATA_DIR, 'last_run.txt'), 'w') as f:
        f.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # 保存推送缓存
    save_sent_cache(sent_cache)

    print(f"\n完成！分析 {len(all_results)} 个币种，推送 {push_count} 条消息")


if __name__ == '__main__':
    run_monitor()
