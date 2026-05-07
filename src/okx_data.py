"""
OKX 数据获取模块
使用公开API，无需登录
"""
import requests
import pandas as pd
import time


OKX_BASE = "https://www.okx.com"


def get_top_symbols(min_volume_usd=100_000_000, max_count=80):
    """
    获取24小时交易量超过指定金额的永续合约交易对
    同时剔除交易量异常暴增的币种（今日>昨日5倍）
    """
    try:
        url = f"{OKX_BASE}/api/v5/market/tickers"
        resp = requests.get(url, params={"instType": "SWAP"}, timeout=10)
        data = resp.json()

        if data.get('code') != '0':
            return []

        tickers = data['data']
        symbols = []

        for t in tickers:
            inst_id = t.get('instId', '')
            # 只要USDT永续合约
            if not inst_id.endswith('-USDT-SWAP'):
                continue

            last_price = float(t.get('last', 0))
            # turnover24h = OKX图表显示的24小时USDT成交额
            vol_usdt = float(t.get('turnover24h', 0))
            # 如果没有volCcyQuote，用vol24h*price估算
            if vol_usdt == 0 and last_price > 0:
                vol_usdt = float(t.get('vol24h', 0)) * last_price
            if vol_usdt < min_volume_usd:
                continue

            symbols.append({
                'symbol':     inst_id,
                'display':    inst_id.replace('-USDT-SWAP', ''),
                'volume_24h': vol_usdt,
                'last_price': last_price,
                'change_24h': float(t.get('sodUtc8', 0)),
            })

        # 按交易量排序
        symbols.sort(key=lambda x: x['volume_24h'], reverse=True)
        return symbols[:max_count]

    except Exception as e:
        print(f"获取交易对列表失败: {e}")
        return []


def get_klines(symbol, timeframe, limit=200):
    """
    获取K线数据
    timeframe: 1m, 5m, 15m, 30m, 1H, 2H, 4H, 1D
    """
    # OKX时间框架映射
    tf_map = {
        '5m':  '5m',
        '15m': '15m',
        '30m': '30m',
        '1h':  '1H',
        '2h':  '2H',
        '4h':  '4H',
        '1d':  '1D',
    }
    bar = tf_map.get(timeframe.lower(), timeframe)

    try:
        url = f"{OKX_BASE}/api/v5/market/candles"
        params = {
            "instId": symbol,
            "bar":    bar,
            "limit":  str(limit)
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()

        if data.get('code') != '0':
            return None

        candles = data['data']
        if not candles:
            return None

        # OKX返回的是倒序，需要反转
        candles.reverse()

        df = pd.DataFrame(candles, columns=[
            'timestamp', 'open', 'high', 'low', 'close',
            'volume', 'volCcy', 'volCcyQuote', 'confirm'
        ])

        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])

        df = df.set_index('timestamp')
        return df[['open', 'high', 'low', 'close', 'volume']]

    except Exception as e:
        print(f"获取K线失败 {symbol} {timeframe}: {e}")
        return None


def get_all_timeframes(symbol, timeframes=None):
    """
    获取一个币种所有周期的K线数据
    """
    if timeframes is None:
        timeframes = ['5m', '15m', '30m', '1h', '2h', '4h']

    result = {}
    for tf in timeframes:
        df = get_klines(symbol, tf, limit=200)
        if df is not None and len(df) >= 100:
            result[tf] = df
        time.sleep(0.1)  # 避免请求过快

    return result


def batch_get_symbols_data(symbols, timeframes=None, max_symbols=50):
    """
    批量获取多个币种的数据
    symbols: 从get_top_symbols()返回的列表
    """
    if timeframes is None:
        timeframes = ['5m', '15m', '30m', '1h', '2h', '4h']

    result = {}
    symbols_to_fetch = symbols[:max_symbols]

    for i, sym in enumerate(symbols_to_fetch):
        inst_id = sym['symbol']
        data = get_all_timeframes(inst_id, timeframes)
        if data:
            result[inst_id] = {
                'info':   sym,
                'klines': data
            }
        time.sleep(0.05)

    return result
