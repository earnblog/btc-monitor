"""
主监控脚本
"""
import os, json, time, sys, numpy as np
from datetime import datetime, timezone

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        if isinstance(obj, np.bool_): return bool(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        return super().default(obj)

sys.path.insert(0, os.path.dirname(__file__))
from src.okx_data import get_top_symbols, get_all_timeframes
from src.signals import analyze_symbol_timeframe, generate_conclusion
from src.notifier import send_wecom, format_signal_message, format_zero_sticky_alert

TIMEFRAMES     = ['5m','15m','30m','1h','2h','4h']
MIN_VOLUME_USD = 100_000_000
MAX_SYMBOLS    = 60
DIST_THRESHOLD = 2.5
COOLDOWN_HOURS = 4
MIN_TF_COUNT   = 2

WECOM_WEBHOOK = os.environ.get('WECOM_WEBHOOK','')
DATA_DIR = os.path.join(os.path.dirname(__file__),'data')

def load_cache():
    f = os.path.join(DATA_DIR,'sent_cache.json')
    try:
        return json.load(open(f)) if os.path.exists(f) else {}
    except: return {}

def save_cache(c):
    os.makedirs(DATA_DIR,exist_ok=True)
    json.dump(c, open(os.path.join(DATA_DIR,'sent_cache.json'),'w'))

def in_cooldown(cache, key):
    if key not in cache: return False
    return (datetime.now()-datetime.fromisoformat(cache[key])).total_seconds()/3600 < COOLDOWN_HOURS

def run():
    print(f"MACD监控 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    os.makedirs(DATA_DIR,exist_ok=True)
    cache = load_cache()
    symbols = get_top_symbols(MIN_VOLUME_USD, MAX_SYMBOLS)
    print(f"获取到 {len(symbols)} 个币种")
    if not symbols: return

    all_results = {}
    push_count = 0

    for i,sym in enumerate(symbols):
        inst_id = sym['symbol']
        name = sym['display']
        price = sym['last_price']
        print(f"[{i+1}/{len(symbols)}] {name}")

        klines = get_all_timeframes(inst_id, TIMEFRAMES)
        if not klines: continue

        sigs = {}
        for tf in TIMEFRAMES:
            df = klines.get(tf)
            if df is not None:
                s = analyze_symbol_timeframe(df, tf)
                if s: sigs[tf] = s
        if not sigs: continue

        conclusion = generate_conclusion(sigs, inst_id)

        # 转换为可序列化的dict
        sigs_clean = {}
        for tf, s in sigs.items():
            sigs_clean[tf] = {k: (bool(v) if isinstance(v, np.bool_) else
                                  int(v) if isinstance(v, np.integer) else
                                  float(v) if isinstance(v, np.floating) else v)
                              for k, v in s.items()}

        all_results[inst_id] = {
            'display': name, 'price': price,
            'volume_24h': sym['volume_24h'],
            'signals': sigs_clean,
            'conclusion': conclusion,
            'updated_at': datetime.now().isoformat(),
        }

        # 高概率信号（无冷却）
        if any(v.get('high_prob') for v in sigs.values()) and WECOM_WEBHOOK:
            title, content = format_signal_message(name, sigs, conclusion, price, True)
            if send_wecom(WECOM_WEBHOOK, title, content):
                print(f"  🎯 高概率: {name}")
                push_count += 1

        # 普通信号：至少2个周期≥2.5倍才推
        high_tfs = [tf for tf,s in sigs.items() if abs(s['dist_ratio']) >= DIST_THRESHOLD]
        if len(high_tfs) >= MIN_TF_COUNT:
            direction = 'short' if sigs[high_tfs[0]]['macd'] > 0 else 'long'
            key = f"{inst_id}_multi_{direction}"
            if not in_cooldown(cache, key) and WECOM_WEBHOOK:
                title, content = format_signal_message(name, sigs, conclusion, price)
                if send_wecom(WECOM_WEBHOOK, title, content):
                    cache[key] = datetime.now().isoformat()
                    print(f"  ⚡ 多级别信号: {name} {len(high_tfs)}个周期")
                    push_count += 1

        # 零轴黏合
        for tf, s in sigs.items():
            if s and s.get('sticky_bars',0) > 0:
                key = f"{inst_id}_{tf}_sticky"
                if not in_cooldown(cache, key) and WECOM_WEBHOOK:
                    tf_order = ['5m','15m','30m','1h','2h','4h']
                    idx = tf_order.index(tf) if tf in tf_order else -1
                    upper_dir = "未知"
                    if idx < len(tf_order)-1:
                        up = sigs.get(tf_order[idx+1])
                        if up: upper_dir = "多头↑" if up['macd']>0 else "空头↓"
                    title, content = format_zero_sticky_alert(name, tf, s['sticky_bars'], upper_dir, price)
                    if send_wecom(WECOM_WEBHOOK, title, content):
                        cache[key] = datetime.now().isoformat()
                        print(f"  ⏳ 零轴黏合: {name} {tf}")
                        push_count += 1

        time.sleep(0.2)

    output = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'symbol_coun
