"""
主监控脚本
由 GitHub Actions 每5分钟调用一次
"""
import os
import json
import time
import sys
import numpy as np
from datetime import datetime, timezone

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

sys.path.insert(0, os.path.dirname(__file__))
from src.okx_data import get_top_symbols, get_all_timeframes
from src.signals import analyze_symbol_timeframe, generate_conclusion
from src.notifier import send_wecom, format_signal_message, format_zero_sticky_alert

TIMEFRAMES     = ['5m', '15m', '30m', '1h', '2h', '4h']
MIN_VOLUME_USD = 100_000_000
MAX_SYMBOLS    = 60
DIST_THRESHOLD = 2.5
COOLDOWN_HOURS = 4
MIN_TF_COUNT   = 2

WECOM_WEBHOOK = os.environ.get('WECOM_WEBHOOK', '')
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')


def load_cache():
    cache_file = os.path.join(DATA_DIR, 'sent_cache.json')
    if os.path.exists(cache_file):
        try:
            with open(cache_file) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cache(cache):
    os.makedirs(DATA_DIR, exist_ok=True)
    cache_file = os.path.join(DATA_DIR, 'sent_cache.json')
    with open(cache_file, 'w') as f:
        json.dump(cache, f)


def in_cooldown(cache, key):
    if key not in cache:
        return False
    last = datetime.fromisoformat(cache[key])
    hours = (datetime.now() - last).total_seconds() / 3600
    return hours < COOLDOWN_HOURS


def clean_signals(sigs):
    result = {}
    for tf, s in sigs.items():
        if s is None:
            continue
        clean = {}
        for k, v in s.items():
            if isinstance(v, np.bool_):
                clean[k] = bool(v)
            elif isinstance(v, np.integer):
                clean[k] = int(v)
            elif isinstance(v, np.floating):
                clean[k] = float(v)
            elif isinstance(v, dict):
                inner = {}
                for dk, dv in v.items():
                    if isinstance(dv, np.bool_):
                        inner[dk] = bool(dv)
                    elif isinstance(dv, np.integer):
                        inner[dk] = int(dv)
                    elif isinstance(dv, np.floating):
                        inner[dk] = float(dv)
                    else:
                        inner[dk] = dv
                clean[k] = inner
            else:
                clean[k] = v
        result[tf] = clean
    return result


def run():
    print(f"MACD监控 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    os.makedirs(DATA_DIR, exist_ok=True)
    cache = load_cache()

    symbols = get_top_symbols(MIN_VOLUME_USD, MAX_SYMBOLS)
    print(f"获取到 {len(symbols)} 个币种")
    if not symbols:
        return

    all_results = {}
    push_count = 0

    for i, sym in enumerate(symbols):
        inst_id = sym['symbol']
        name    = sym['display']
        price   = sym['last_price']
        print(f"[{i+1}/{len(symbols)}] {name}")

        klines = get_all_timeframes(inst_id, TIMEFRAMES)
        if not klines:
            continue

        sigs = {}
        for tf in TIMEFRAMES:
            df = klines.get(tf)
            if df is not None:
                s = analyze_symbol_timeframe(df, tf)
                if s:
                    sigs[tf] = s
        if not sigs:
            continue

        conclusion = generate_conclusion(sigs, inst_id)
        sigs_clean = clean_signals(sigs)

        all_results[inst_id] = {
            'display':    name,
            'price':      float(price),
            'volume_24h': float(sym['volume_24h']),
            'signals':    sigs_clean,
            'conclusion': conclusion,
            'updated_at': datetime.now().isoformat(),
        }

        # 高概率信号（无冷却）
        has_hp = any(bool(v.get('high_prob', False)) for v in sigs.values())
        if has_hp and WECOM_WEBHOOK:
            title, content = format_signal_message(
                name, sigs, conclusion, price, True)
            if send_wecom(WECOM_WEBHOOK, title, content):
                print(f"  🎯 高概率: {name}")
                push_count += 1

        # 普通信号：至少2个周期达到2.5倍
        high_tfs = [tf for tf, s in sigs.items()
                    if abs(float(s.get('dist_ratio', 0))) >= DIST_THRESHOLD]
        if len(high_tfs) >= MIN_TF_COUNT:
            first_sig = sigs[high_tfs[0]]
            direction = 'short' if float(first_sig.get('macd', 0)) > 0 else 'long'
            key = f"{inst_id}_multi_{direction}"
            if not in_cooldown(cache, key) and WECOM_WEBHOOK:
                title, content = format_signal_message(
                    name, sigs, conclusion, price)
                if send_wecom(WECOM_WEBHOOK, title, content):
                    cache[key] = datetime.now().isoformat()
                    print(f"  ⚡ 多级别: {name} {len(high_tfs)}周期")
                    push_count += 1

        # 零轴黏合
        tf_order = ['5m', '15m', '30m', '1h', '2h', '4h']
        for tf, s in sigs.items():
            if s and int(s.get('sticky_bars', 0)) > 0:
                key = f"{inst_id}_{tf}_sticky"
                if not in_cooldown(cache, key) and WECOM_WEBHOOK:
                    idx = tf_order.index(tf) if tf in tf_order else -1
                    upper_dir = "未知"
                    if 0 <= idx < len(tf_order) - 1:
                        up = sigs.get(tf_order[idx + 1])
                        if up:
                            upper_dir = "多头↑" if float(up.get('macd', 0)) > 0 else "空头↓"
                    title, content = format_zero_sticky_alert(
                        name, tf, int(s['sticky_bars']), upper_dir, price)
                    if send_wecom(WECOM_WEBHOOK, title, content):
                        cache[key] = datetime.now().isoformat()
                        print(f"  ⏳ 零轴黏合: {name} {tf}")
                        push_count += 1

        time.sleep(0.2)

    output = {
        'updated_at':   datetime.now(timezone.utc).isoformat(),
        'symbol_count': len(all_results),
        'symbols':      all_results,
    }

    signals_file = os.path.join(DATA_DIR, 'signals.json')
    with open(signals_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, cls=NumpyEncoder)

    last_run_file = os.path.join(DATA_DIR, 'last_run.txt')
    with open(last_run_file, 'w') as f:
        f.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    save_cache(cache)
    print(f"完成！{len(all_results)} 个币种，推送 {push_count} 条")


if __name__ == '__main__':
    run()
