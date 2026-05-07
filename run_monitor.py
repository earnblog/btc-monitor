"""
主监控脚本 v2
- 只在信号状态变化时推送
- BTC/ETH/SOL/DOGE始终推送
"""
import os
import json
import time
import sys
import numpy as np
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

TIMEFRAMES     = ['5m', '15m', '30m', '1h', '2h', '4h']
MIN_VOLUME_USD = 100_000_000
MAX_SYMBOLS    = 60
DIST_THRESHOLD = 2.5   # 普通信号门槛
PRIORITY_SYMS  = ['BTC-USDT-SWAP', 'ETH-USDT-SWAP',
                   'SOL-USDT-SWAP', 'DOGE-USDT-SWAP']  # 始终显示

WECOM_WEBHOOK = os.environ.get('WECOM_WEBHOOK', '')
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')


def load_json(path, default=None):
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return default if default is not None else {}


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, cls=NumpyEncoder)


def clean_sig(s):
    """把numpy类型全部转成Python原生类型"""
    if s is None:
        return None
    result = {}
    for k, v in s.items():
        if isinstance(v, np.bool_): result[k] = bool(v)
        elif isinstance(v, np.integer): result[k] = int(v)
        elif isinstance(v, np.floating): result[k] = float(v)
        elif isinstance(v, dict):
            result[k] = {
                dk: (bool(dv) if isinstance(dv, np.bool_) else
                     int(dv) if isinstance(dv, np.integer) else
                     float(dv) if isinstance(dv, np.floating) else dv)
                for dk, dv in v.items()
            }
        else:
            result[k] = v
    return result


def get_signal_state(sig):
    """
    提取信号的关键状态，用于和上次对比
    返回一个简单的状态字典
    """
    if sig is None:
        return None
    ratio = float(sig.get('dist_ratio', 0))
    return {
        'ratio_level': (
            'extreme' if abs(ratio) >= 4 else
            'high'    if abs(ratio) >= 2.5 else
            'mid'     if abs(ratio) >= 1.5 else
            'low'
        ),
        'direction':  'above' if float(sig.get('macd', 0)) > 0 else 'below',
        'zero_cross': int(sig.get('zero_cross', 0)),
        'near_zero':  bool(sig.get('near_zero', False)),
        'high_prob':  bool(sig.get('high_prob', False)),
        'divergence': int(sig.get('divergence', 0)),
        'sticky':     int(sig.get('sticky_bars', 0)) > 0,
    }


def should_push(inst_id, tf, curr_state, prev_states):
    """
    判断是否需要推送
    只在以下情况推送：
    1. 高概率信号触发
    2. 倍数级别升档（low→mid→high→extreme）
    3. 零轴穿越（方向改变）
    4. 出现背离
    5. 之前没有记录（首次出现）
    """
    if curr_state is None:
        return False, ''

    prev = prev_states.get(f"{inst_id}_{tf}")

    # 高概率信号：始终推
    if curr_state['high_prob']:
        return True, '高概率信号'

    # 首次出现且倍数够高
    if prev is None:
        if curr_state['ratio_level'] in ('high', 'extreme'):
            return True, '新信号'
        return False, ''

    # 零轴穿越：方向变了，推送
    if curr_state['zero_cross'] != 0:
        return True, f"穿越零轴{'↑' if curr_state['zero_cross']==1 else '↓'}"

    # 倍数升档：low→mid, mid→high, high→extreme
    level_order = {'low': 0, 'mid': 1, 'high': 2, 'extreme': 3}
    curr_level = level_order.get(curr_state['ratio_level'], 0)
    prev_level = level_order.get(prev.get('ratio_level', 'low'), 0)
    if curr_level > prev_level and curr_level >= 2:  # 至少到high
        return True, f"倍数升级→{curr_state['ratio_level']}"

    # 新出现背离
    if curr_state['divergence'] != 0 and prev.get('divergence', 0) == 0:
        div_type = '顶背离' if curr_state['divergence'] == -1 else '底背离'
        return True, f"新增{div_type}"

    # 零轴黏合新出现
    if curr_state['sticky'] and not prev.get('sticky', False):
        return True, '零轴黏合'

    return False, ''


def run():
    print(f"MACD监控 v2 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    os.makedirs(DATA_DIR, exist_ok=True)

    # 加载上次的信号状态
    prev_states = load_json(os.path.join(DATA_DIR, 'prev_states.json'))

    # 获取币种列表
    symbols = get_top_symbols(MIN_VOLUME_USD, MAX_SYMBOLS)

    # 确保BTC/ETH/SOL/DOGE在列表里
    existing_ids = [s['symbol'] for s in symbols]
    for pid in PRIORITY_SYMS:
        if pid not in existing_ids:
            # 手动加入
            display = pid.replace('-USDT-SWAP', '')
            symbols.append({
                'symbol': pid,
                'display': display,
                'last_price': 0,
                'volume_24h': 0,
            })

    print(f"监控 {len(symbols)} 个币种")
    if not symbols:
        return

    all_results = {}
    new_states = {}
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
        sigs_clean = {tf: clean_sig(s) for tf, s in sigs.items()}

        # 更新价格（对于强制加入的优先币种）
        if price == 0 and sigs_clean:
            first_sig = next(iter(sigs_clean.values()))
            price = float(first_sig.get('close', 0))

        all_results[inst_id] = {
            'display':    name,
            'price':      float(price),
            'volume_24h': float(sym.get('volume_24h', 0)),
            'signals':    sigs_clean,
            'conclusion': conclusion,
            'updated_at': datetime.now().isoformat(),
            'is_priority': inst_id in PRIORITY_SYMS,
        }

        # ── 推送判断 ──
        pushed_this_coin = False

        # 先检查高概率信号（最高优先级）
        has_hp = any(bool(s.get('high_prob', False)) for s in sigs.values())
        if has_hp and WECOM_WEBHOOK:
            title, content = format_signal_message(
                name, sigs, conclusion, price, True)
            if send_wecom(WECOM_WEBHOOK, title, content):
                print(f"  🎯 高概率: {name}")
                push_count += 1
                pushed_this_coin = True

        # 按周期检查状态变化
        if not pushed_this_coin:
            for tf in ['4h', '2h', '1h', '30m', '15m', '5m']:
                sig = sigs.get(tf)
                if sig is None:
                    continue

                curr_state = get_signal_state(sig)
                new_states[f"{inst_id}_{tf}"] = curr_state

                need_push, reason = should_push(inst_id, tf, curr_state, prev_states)

                if need_push and WECOM_WEBHOOK:
                    title, content = format_signal_message(
                        name, sigs, conclusion, price)
                    # 在消息里加上触发原因
                    content = content.replace(
                        f"**综合判断：{conclusion}**",
                        f"**触发原因：{reason}**\n**综合判断：{conclusion}**"
                    )
                    if send_wecom(WECOM_WEBHOOK, title, content):
                        print(f"  ⚡ {name} {tf} {reason}")
                        push_count += 1
                        pushed_this_coin = True
                        break  # 每个币每次最多推一条

        time.sleep(0.2)

    # 保存当前状态供下次对比
    save_json(os.path.join(DATA_DIR, 'prev_states.json'), new_states)

    # 保存信号数据给网页
    output = {
        'updated_at':   datetime.now(timezone.utc).isoformat(),
        'symbol_count': len(all_results),
        'symbols':      all_results,
    }
    save_json(os.path.join(DATA_DIR, 'signals.json'), output)

    with open(os.path.join(DATA_DIR, 'last_run.txt'), 'w') as f:
        f.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    print(f"完成！{len(all_results)} 个币种，推送 {push_count} 条")


if __name__ == '__main__':
    run()
