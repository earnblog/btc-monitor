"""
主监控脚本 v3
- 按级别共振程度分类推送
- 单周期也推，但标注可信度
- BTC/ETH/SOL/DOGE始终监控
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
from src.notifier import send_wecom

TIMEFRAMES    = ['5m', '15m', '30m', '1h', '2h', '4h']
MIN_VOLUME    = 100_000_000
MAX_SYMBOLS   = 60
COOLDOWN_HOURS = 2          # 同币种同方向同强度2小时内不重复
DIST_MIN      = 2.0         # 最低倍数门槛
PRIORITY_SYMS = ['BTC-USDT-SWAP','ETH-USDT-SWAP',
                 'SOL-USDT-SWAP','DOGE-USDT-SWAP']

WECOM_WEBHOOK = os.environ.get('WECOM_WEBHOOK', '')
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

TF_NAMES = {
    '5m':'5分', '15m':'15分', '30m':'30分',
    '1h':'1时', '2h':'2时',   '4h':'4时'
}

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

def in_cooldown(cache, key):
    if key not in cache:
        return False
    last = datetime.fromisoformat(cache[key])
    return (datetime.now() - last).total_seconds() / 3600 < COOLDOWN_HOURS

def clean_sig(s):
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

def get_resonance(sigs, direction, min_ratio=2.0):
    """
    检测多级别共振
    direction: 'short'(高空) 或 'long'(低多)
    返回：触发的周期列表，按重要性排序
    """
    triggered = []
    tf_order = ['4h', '2h', '1h', '30m', '15m', '5m']

    for tf in tf_order:
        s = sigs.get(tf)
        if s is None:
            continue
        ratio = float(s.get('dist_ratio', 0))
        macd  = float(s.get('macd', 0))

        if direction == 'short':
            # 高空：MACD在零轴上方，倍数够高，斜率向下
            if macd > 0 and ratio >= min_ratio:
                triggered.append(tf)
        else:
            # 低多：MACD在零轴下方，倍数够深，斜率向上
            if macd < 0 and abs(ratio) >= min_ratio:
                triggered.append(tf)

    return triggered

def resonance_level(tfs):
    """根据触发周期数和周期权重评估共振强度"""
    weight = {'4h': 4, '2h': 3, '1h': 3, '30m': 2, '15m': 1, '5m': 1}
    score = sum(weight.get(tf, 1) for tf in tfs)

    if score >= 10:
        return 4, '🔥🔥🔥🔥 四级别强共振', '极高', '多级别深度共振，信号可靠性极高'
    elif score >= 7:
        return 3, '🔥🔥🔥 三级别共振', '高', '三个以上级别共振，信号质量较好'
    elif score >= 4:
        return 2, '🔥🔥 双级别共振', '中', '两个级别共振，建议等待更多确认'
    elif score >= 1:
        return 1, '⚡ 单级别信号', '低', '仅单周期触发，假信号概率较高，谨慎操作'
    return 0, '', '', ''

def format_all_tfs(sigs):
    """格式化所有周期状态"""
    tf_order = ['5m', '15m', '30m', '1h', '2h', '4h']
    lines = []
    for tf in tf_order:
        s = sigs.get(tf)
        if s is None:
            continue
        ratio = float(s.get('dist_ratio', 0))
        macd  = float(s.get('macd', 0))
        dir_str = '上方' if macd > 0 else '下方'
        abs_r = abs(ratio)

        icon = '🔥' if abs_r >= 3 else ('⚡' if abs_r >= 2 else '▪')
        extra = ''
        if s.get('divergence') == -1: extra += ' ⚠顶背离'
        elif s.get('divergence') == 1: extra += ' ✅底背离'
        if s.get('near_zero'): extra += ' 🎯近零轴'
        if s.get('zero_cross') == 1: extra += ' 📈穿零↑'
        elif s.get('zero_cross') == -1: extra += ' 📉穿零↓'

        lines.append(f'> {icon} **{TF_NAMES[tf]}** {dir_str}{abs_r:.1f}倍{extra}')
    return '\n'.join(lines)

def build_message(name, price, sigs, triggered_tfs, direction, level_num, level_label, reliability, advice, conclusion):
    now = datetime.now().strftime('%m-%d %H:%M')
    dir_cn = '做空📉' if direction == 'short' else '做多📈'
    tfs_str = ' + '.join(TF_NAMES.get(tf, tf) for tf in triggered_tfs)

    # 可信度颜色
    rel_icon = {'极高':'🟢', '高':'🟡', '中':'🟠', '低':'🔴'}.get(reliability, '⚪')

    title = f'{level_label} {name} {dir_cn}'
    content = '\n'.join([
        f'## {level_label}',
        f'**{name}/USDT 永续** | {now}',
        f'**当前价：** ${price:,.4f}',
        '',
        f'**触发周期：** {tfs_str}',
        f'**方向：** {dir_cn}',
        f'**可信度：** {rel_icon} {reliability}',
        f'**说明：** {advice}',
        '',
        '**全周期状态：**',
        format_all_tfs(sigs),
        '',
        f'**综合判断：** {conclusion}',
        '',
        '---',
        f'*仅供参考，不构成投资建议*'
    ])
    return title, content

def run():
    print(f"MACD监控 v3  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    os.makedirs(DATA_DIR, exist_ok=True)
    cache = load_json(os.path.join(DATA_DIR, 'sent_cache.json'))

    symbols = get_top_symbols(MIN_VOLUME, MAX_SYMBOLS)
    # 确保优先币种在列表里
    existing = [s['symbol'] for s in symbols]
    for pid in PRIORITY_SYMS:
        if pid not in existing:
            symbols.append({
                'symbol': pid,
                'display': pid.replace('-USDT-SWAP',''),
                'last_price': 0,
                'volume_24h': 0,
            })

    print(f"监控 {len(symbols)} 个币种")

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

        # 更新价格
        if price == 0:
            for s in sigs.values():
                if s and s.get('close'):
                    price = float(s['close'])
                    break

        conclusion  = generate_conclusion(sigs, inst_id)
        sigs_clean  = {tf: clean_sig(s) for tf, s in sigs.items()}

        all_results[inst_id] = {
            'display':     name,
            'price':       float(price),
            'volume_24h':  float(sym.get('volume_24h', 0)),
            'signals':     sigs_clean,
            'conclusion':  conclusion,
            'updated_at':  datetime.now().isoformat(),
            'is_priority': inst_id in PRIORITY_SYMS,
        }

        if not WECOM_WEBHOOK:
            continue

        # ── 高概率信号（归零轴+EMA52，最高优先级）──
        # 加入上级别检查：上级别不能是反向高位
        tf_order = ['5m', '15m', '30m', '1h', '2h', '4h']
        valid_hp_tfs = []
        for tf, s in sigs.items():
            if not s or not bool(s.get('high_prob', False)):
                continue
            macd_val = float(s.get('macd', 0))
            # 找上一级别
            idx = tf_order.index(tf) if tf in tf_order else -1
            if idx < len(tf_order) - 1:
                upper_tf = tf_order[idx + 1]
                upper_s = sigs.get(upper_tf)
                if upper_s:
                    upper_macd = float(upper_s.get('macd', 0))
                    upper_ratio = abs(float(upper_s.get('dist_ratio', 0)))
                    # 做多：上级别不能是高空（零轴上方高位）
                    if macd_val < 0 and upper_macd > 0 and upper_ratio >= 2.0:
                        print(f"  ⚠️ {name} {tf} 高概率做多被过滤：上级别{upper_tf}仍在高空{upper_ratio:.1f}倍")
                        continue
                    # 做空：上级别不能是低多（零轴下方高位）
                    if macd_val > 0 and upper_macd < 0 and upper_ratio >= 2.0:
                        print(f"  ⚠️ {name} {tf} 高概率做空被过滤：上级别{upper_tf}仍在低多{upper_ratio:.1f}倍")
                        continue
            valid_hp_tfs.append(tf)

        if valid_hp_tfs:
            key = f"{inst_id}_hp"
            if not in_cooldown(cache, key):
                dir_ = 'short' if float(sigs[valid_hp_tfs[0]].get('macd',0)) > 0 else 'long'
                title, msg = build_message(
                    name, price, sigs, valid_hp_tfs, dir_,
                    4, '🎯 高概率信号', '极高',
                    '归零轴+EMA52共振，上级别方向配合', conclusion)
                if send_wecom(WECOM_WEBHOOK, title, msg):
                    cache[key] = datetime.now().isoformat()
                    print(f"  🎯 高概率: {name}")
                    push_count += 1

        # ── 做空共振检测 ──
        short_tfs = get_resonance(sigs, 'short', DIST_MIN)
        if short_tfs:
            level_num, level_label, reliability, advice = resonance_level(short_tfs)
            key = f"{inst_id}_short_l{level_num}"
            if not in_cooldown(cache, key):
                title, content = build_message(
                    name, price, sigs, short_tfs, 'short',
                    level_num, level_label, reliability, advice, conclusion)
                if send_wecom(WECOM_WEBHOOK, title, content):
                    cache[key] = datetime.now().isoformat()
                    print(f"  {level_label}: {name} 空 ({','.join(short_tfs)})")
                    push_count += 1

        # ── 做多共振检测 ──
        long_tfs = get_resonance(sigs, 'long', DIST_MIN)
        if long_tfs:
            level_num, level_label, reliability, advice = resonance_level(long_tfs)
            key = f"{inst_id}_long_l{level_num}"
            if not in_cooldown(cache, key):
                title, content = build_message(
                    name, price, sigs, long_tfs, 'long',
                    level_num, level_label, reliability, advice, conclusion)
                if send_wecom(WECOM_WEBHOOK, title, content):
                    cache[key] = datetime.now().isoformat()
                    print(f"  {level_label}: {name} 多 ({','.join(long_tfs)})")
                    push_count += 1

        time.sleep(0.2)

    # 保存数据
    save_json(os.path.join(DATA_DIR, 'signals.json'), {
        'updated_at':   datetime.now(timezone.utc).isoformat(),
        'symbol_count': len(all_results),
        'symbols':      all_results,
    })
    with open(os.path.join(DATA_DIR, 'last_run.txt'), 'w') as f:
        f.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    save_json(os.path.join(DATA_DIR, 'sent_cache.json'), cache)

    print(f"完成！{len(all_results)} 个币种，推送 {push_count} 条")

if __name__ == '__main__':
    run()
