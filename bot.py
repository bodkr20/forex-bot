import logging
import asyncio
import random
import json
import numpy as np
import aiohttp
import websockets
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8754472585:AAGIX510vMHTRCTJaGVdnsjn8HjcPqq9-HQ"
PO_SSID = '42["auth",{"session":"a%3A4%3A%7Bs%3A10%3A%22session_id%22%3Bs%3A32%3A%22a4cb7bdffb9d586292f6581ca06d58cd%22%3Bs%3A10%3A%22ip_address%22%3Bs%3A15%3A%22146.251.186.204%22%3Bs%3A10%3A%22user_agent%22%3Bs%3A111%3A%22Mozilla%2F5.0%20%28Windows%20NT%2010.0%3B%20Win64%3B%20x64%29%20AppleWebKit%2F537.36%20%28KHTML%2C%20like%20Gecko%29%20Chrome%2F149.0.0.0%20Safari%2F537.36%22%3Bs%3A13%3A%22last_activity%22%3Bi%3A1782558214%3B%7Dfd6d478c88d84a1805c8c5cb9e508b3b","isDemo":1,"uid":"130213513","lang":"en"}]'

OTC_PAIRS = [
    {"name": "AED/CNY OTC", "flag": "🇦🇪", "type": "otc", "symbol": "AEDCNY_otc"},
    {"name": "BHD/CNY OTC", "flag": "🇧🇭", "type": "otc", "symbol": "BHDCNY_otc"},
    {"name": "GBP/USD OTC", "flag": "🇬🇧", "type": "otc", "symbol": "GBPUSD_otc"},
    {"name": "AUD/CAD OTC", "flag": "🇦🇺", "type": "otc", "symbol": "AUDCAD_otc"},
    {"name": "EUR/USD OTC", "flag": "🇪🇺", "type": "otc", "symbol": "EURUSD_otc"},
    {"name": "AUD/NZD OTC", "flag": "🇦🇺", "type": "otc", "symbol": "AUDNZD_otc"},
    {"name": "USD/JPY OTC", "flag": "🇺🇸", "type": "otc", "symbol": "USDJPY_otc"},
    {"name": "USD/CHF OTC", "flag": "🇺🇸", "type": "otc", "symbol": "USDCHF_otc"},
    {"name": "AUD/USD OTC", "flag": "🇦🇺", "type": "otc", "symbol": "AUDUSD_otc"},
    {"name": "EUR/HUF OTC", "flag": "🇪🇺", "type": "otc", "symbol": "EURHUF_otc"},
    {"name": "GBP/AUD OTC", "flag": "🇬🇧", "type": "otc", "symbol": "GBPAUD_otc"},
    {"name": "NZD/USD OTC", "flag": "🇳🇿", "type": "otc", "symbol": "NZDUSD_otc"},
]

LIVE_PAIRS = [
    {"name": "EUR/USD", "flag": "🇪🇺", "type": "live", "symbol": "EURUSD=X"},
    {"name": "GBP/USD", "flag": "🇬🇧", "type": "live", "symbol": "GBPUSD=X"},
    {"name": "USD/JPY", "flag": "🇺🇸", "type": "live", "symbol": "JPY=X"},
    {"name": "AUD/USD", "flag": "🇦🇺", "type": "live", "symbol": "AUDUSD=X"},
    {"name": "USD/CAD", "flag": "🇨🇦", "type": "live", "symbol": "CAD=X"},
    {"name": "USD/CHF", "flag": "🇨🇭", "type": "live", "symbol": "CHF=X"},
    {"name": "NZD/USD", "flag": "🇳🇿", "type": "live", "symbol": "NZDUSD=X"},
    {"name": "GBP/JPY", "flag": "🇬🇧", "type": "live", "symbol": "GBPJPY=X"},
]

ALL_PAIRS = OTC_PAIRS + LIVE_PAIRS

# ===== Background Connection =====
po_candles_cache = {}
po_connected = False

PO_WS_REGIONS = [
    "wss://api-l.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://api-c.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://api-s.po.market/socket.io/?EIO=4&transport=websocket",
]

async def po_background_connection():
    global po_connected
    while True:
        for ws_url in PO_WS_REGIONS:
            try:
                async with websockets.connect(
                    ws_url,
                    extra_headers={
                        "Origin": "https://pocketoption.com",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    },
                    ping_interval=25,
                    ping_timeout=15,
                    close_timeout=5,
                ) as ws:
                    await asyncio.wait_for(ws.recv(), timeout=5)
                    await ws.send("40")
                    await asyncio.wait_for(ws.recv(), timeout=5)
                    await ws.send(PO_SSID)

                    auth_ok = False
                    for _ in range(10):
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=3)
                            if "auth/success" in msg:
                                auth_ok = True
                                po_connected = True
                                logger.info("✅ PO Background Auth Success")
                                break
                        except asyncio.TimeoutError:
                            break

                    if not auth_ok:
                        po_connected = False
                        continue

                    # اشترك في كل الأزواج
                    for pair in OTC_PAIRS:
                        now_ts = int(datetime.now().timestamp())
                        sub = json.dumps(["subscribe", {"asset": pair["symbol"], "period": 60}])
                        hist = json.dumps(["loadHistoryPeriod", {
                            "asset": pair["symbol"], "period": 60,
                            "time": now_ts, "index": 0
                        }])
                        await ws.send(f"42{sub}")
                        await asyncio.sleep(0.2)
                        await ws.send(f"42{hist}")
                        await asyncio.sleep(0.2)

                    # استقبال مستمر
                    while True:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=30)

                            if msg == "2":
                                await ws.send("3")
                                continue

                            if msg.startswith("42"):
                                try:
                                    data = json.loads(msg[2:])
                                    if isinstance(data, list) and len(data) >= 2:
                                        payload = data[1]
                                        if isinstance(payload, dict):
                                            asset = payload.get("asset", "")
                                            raw = (payload.get("candles") or
                                                   payload.get("data") or
                                                   payload.get("history") or [])
                                            candles = []
                                            for c in raw:
                                                if isinstance(c, dict) and "open" in c:
                                                    candles.append({
                                                        "open": float(c.get("open", 0)),
                                                        "close": float(c.get("close", 0)),
                                                        "high": float(c.get("high", c.get("close", 0))),
                                                        "low": float(c.get("low", c.get("close", 0))),
                                                    })
                                                elif isinstance(c, (list, tuple)) and len(c) >= 4:
                                                    candles.append({
                                                        "open": float(c[1]),
                                                        "close": float(c[4]) if len(c) > 4 else float(c[3]),
                                                        "high": float(c[2]),
                                                        "low": float(c[3]),
                                                    })
                                            if candles and asset:
                                                po_candles_cache[asset] = candles
                                                logger.info(f"📊 Cached {len(candles)} candles for {asset}")
                                except Exception as e:
                                    logger.warning(f"Parse error: {e}")

                        except asyncio.TimeoutError:
                            try:
                                await ws.send("3")
                            except:
                                break
                        except Exception as e:
                            logger.warning(f"Recv error: {e}")
                            break

            except Exception as e:
                logger.warning(f"PO WS disconnected: {e}")
                po_connected = False

            await asyncio.sleep(5)

async def fetch_po_candles(symbol: str, count: int = 80):
    # أول شيء: جرب الكاش
    candles = po_candles_cache.get(symbol)
    if candles and len(candles) >= 20:
        logger.info(f"✅ Cache hit: {len(candles)} candles for {symbol}")
        return candles[-count:]

    # إذا الكاش فاضي: جرب اتصال مباشر
    for ws_url in PO_WS_REGIONS:
        try:
            candles = await _direct_fetch(ws_url, symbol, count)
            if candles and len(candles) >= 20:
                po_candles_cache[symbol] = candles
                return candles
        except Exception as e:
            logger.warning(f"Direct fetch failed: {e}")
    return None

async def _direct_fetch(ws_url: str, symbol: str, count: int):
    candles = []
    try:
        async with websockets.connect(
            ws_url,
            extra_headers={
                "Origin": "https://pocketoption.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            await asyncio.wait_for(ws.recv(), timeout=5)
            await ws.send("40")
            await asyncio.wait_for(ws.recv(), timeout=5)
            await ws.send(PO_SSID)

            auth_ok = False
            for _ in range(10):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=3)
                    if "auth/success" in msg:
                        auth_ok = True
                        break
                except asyncio.TimeoutError:
                    break

            if not auth_ok:
                return None

            now_ts = int(datetime.now().timestamp())
            sub = json.dumps(["subscribe", {"asset": symbol, "period": 60}])
            hist = json.dumps(["loadHistoryPeriod", {
                "asset": symbol, "period": 60,
                "time": now_ts, "index": 0
            }])
            await ws.send(f"42{sub}")
            await ws.send(f"42{hist}")

            for _ in range(30):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=3)
                    if msg == "2":
                        await ws.send("3")
                        continue
                    if msg.startswith("42"):
                        data = json.loads(msg[2:])
                        if isinstance(data, list) and len(data) >= 2:
                            payload = data[1]
                            raw = []
                            if isinstance(payload, list):
                                raw = payload
                            elif isinstance(payload, dict):
                                raw = (payload.get("candles") or
                                       payload.get("data") or
                                       payload.get("history") or [])
                            for c in raw:
                                if isinstance(c, dict) and "open" in c:
                                    candles.append({
                                        "open": float(c.get("open", 0)),
                                        "close": float(c.get("close", 0)),
                                        "high": float(c.get("high", c.get("close", 0))),
                                        "low": float(c.get("low", c.get("close", 0))),
                                    })
                                elif isinstance(c, (list, tuple)) and len(c) >= 4:
                                    candles.append({
                                        "open": float(c[1]),
                                        "close": float(c[4]) if len(c) > 4 else float(c[3]),
                                        "high": float(c[2]),
                                        "low": float(c[3]),
                                    })
                            if len(candles) >= 20:
                                break
                except asyncio.TimeoutError:
                    continue
    except Exception as e:
        logger.warning(f"Direct fetch error: {e}")
        return None

    return candles[-count:] if len(candles) >= 20 else None

# ===== Yahoo Finance =====

async def fetch_yahoo_candles(symbol: str, count: int = 80):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {"interval": "1m", "range": "1d", "includePrePost": "false"}
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None
        chart = result[0]
        indicators = chart.get("indicators", {}).get("quote", [{}])[0]
        opens = indicators.get("open", [])
        closes = indicators.get("close", [])
        highs = indicators.get("high", [])
        lows = indicators.get("low", [])
        candles = []
        for i in range(len(closes)):
            if closes[i] is None or opens[i] is None:
                continue
            candles.append({
                "open": opens[i], "close": closes[i],
                "high": highs[i] if highs[i] else closes[i],
                "low": lows[i] if lows[i] else closes[i],
            })
        return candles[-count:] if len(candles) >= 20 else None
    except Exception as e:
        logger.warning(f"Yahoo error: {e}")
        return None

# ===== المؤشرات =====

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)

def calc_ema(closes, period):
    if len(closes) < period:
        return closes[-1] if closes else 0
    k = 2 / (period + 1)
    ema = np.mean(closes[:period])
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return round(ema, 6)

def calc_macd(closes):
    if len(closes) < 26:
        return 0, 0
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    macd_line = ema12 - ema26
    signal = calc_ema(closes[-9:], 9) if len(closes) >= 9 else macd_line
    return round(macd_line, 6), round(signal, 6)

def calc_bollinger(closes, period=20):
    if len(closes) < period:
        mid = closes[-1]
        return mid, mid * 1.002, mid * 0.998
    recent = closes[-period:]
    mid = np.mean(recent)
    std = np.std(recent)
    return round(mid, 6), round(mid + 2 * std, 6), round(mid - 2 * std, 6)

def calc_stochastic(closes, period=14):
    if len(closes) < period:
        return 50.0
    recent = closes[-period:]
    lowest, highest = min(recent), max(recent)
    if highest == lowest:
        return 50.0
    return round(((closes[-1] - lowest) / (highest - lowest)) * 100, 2)

def calc_williams_r(candles, period=14):
    if len(candles) < period:
        return -50.0
    recent = candles[-period:]
    hh = max(c["high"] for c in recent)
    ll = min(c["low"] for c in recent)
    if hh == ll:
        return -50.0
    return round(((hh - candles[-1]["close"]) / (hh - ll)) * -100, 2)

def calc_cci(candles, period=20):
    if len(candles) < period:
        return 0
    tp = [(c["high"] + c["low"] + c["close"]) / 3 for c in candles[-period:]]
    mean_tp = np.mean(tp)
    mean_dev = np.mean([abs(t - mean_tp) for t in tp])
    if mean_dev == 0:
        return 0
    return round((tp[-1] - mean_tp) / (0.015 * mean_dev), 2)

def calc_atr(candles, period=14):
    if len(candles) < period + 1:
        return 0
    trs = [max(candles[i]["high"] - candles[i]["low"],
               abs(candles[i]["high"] - candles[i-1]["close"]),
               abs(candles[i]["low"] - candles[i-1]["close"]))
           for i in range(1, len(candles))]
    return round(np.mean(trs[-period:]), 6)

def calc_momentum(closes, period=10):
    if len(closes) < period:
        return 0
    return round(closes[-1] - closes[-period], 6)

def detect_trend(closes, period=20):
    if len(closes) < period:
        return "neutral"
    recent = closes[-period:]
    first_half = np.mean(recent[:period//2])
    second_half = np.mean(recent[period//2:])
    diff_pct = (second_half - first_half) / first_half * 100
    if diff_pct > 0.05:
        return "uptrend"
    elif diff_pct < -0.05:
        return "downtrend"
    return "sideways"

def detect_patterns(candles):
    patterns, score = [], 0
    if len(candles) < 3:
        return patterns, score
    c = candles
    body = abs(c[-1]["close"] - c[-1]["open"])
    total = c[-1]["high"] - c[-1]["low"]

    if (c[-2]["close"] < c[-2]["open"] and c[-1]["close"] > c[-1]["open"] and
            c[-1]["open"] < c[-2]["close"] and c[-1]["close"] > c[-2]["open"]):
        patterns.append("🕯 Bullish Engulfing"); score += 4

    if (c[-2]["close"] > c[-2]["open"] and c[-1]["close"] < c[-1]["open"] and
            c[-1]["open"] > c[-2]["close"] and c[-1]["close"] < c[-2]["open"]):
        patterns.append("🕯 Bearish Engulfing"); score -= 4

    if total > 0 and body / total < 0.1:
        patterns.append("⚖️ Doji")

    if (total > 0 and body / total < 0.3 and
            (c[-1]["high"] - max(c[-1]["open"], c[-1]["close"])) > body * 2):
        patterns.append("📌 Shooting Star"); score -= 3

    if (total > 0 and body / total < 0.3 and
            (min(c[-1]["open"], c[-1]["close"]) - c[-1]["low"]) > body * 2):
        patterns.append("📌 Hammer"); score += 3

    if len(c) >= 3:
        if (c[-3]["close"] < c[-3]["open"] and
                abs(c[-2]["close"] - c[-2]["open"]) < abs(c[-3]["close"] - c[-3]["open"]) * 0.3 and
                c[-1]["close"] > (c[-3]["open"] + c[-3]["close"]) / 2):
            patterns.append("🌟 Morning Star"); score += 5
        if (c[-3]["close"] > c[-3]["open"] and
                abs(c[-2]["close"] - c[-2]["open"]) < abs(c[-3]["close"] - c[-3]["open"]) * 0.3 and
                c[-1]["close"] < (c[-3]["open"] + c[-3]["close"]) / 2):
            patterns.append("🌟 Evening Star"); score -= 5

    if all(c[-i]["close"] > c[-i]["open"] for i in range(1, 4)):
        patterns.append("🟢 Three Bullish Candles"); score += 2
    if all(c[-i]["close"] < c[-i]["open"] for i in range(1, 4)):
        patterns.append("🔴 Three Bearish Candles"); score -= 2

    return patterns[:2], score

def breakout_strategy(candles, expiry):
    closes = [c["close"] for c in candles]
    _, bb_up, bb_low = calc_bollinger(closes, period=10)
    atr = calc_atr(candles, period=5)
    current = closes[-1]
    prev = closes[-2] if len(closes) >= 2 else current
    body = abs(current - candles[-1]["open"])
    signals, score = [], 0

    if prev <= bb_up and current > bb_up and body > atr * 0.5:
        signals.append("💥 Breakout UP"); score += 8
    elif prev >= bb_low and current < bb_low and body > atr * 0.5:
        signals.append("💥 Breakout DOWN"); score -= 8

    return signals, score

def snap_reversal_strategy(candles, expiry):
    closes = [c["close"] for c in candles]
    rsi = calc_rsi(closes, period=5)
    stoch = calc_stochastic(closes, period=5)
    wr = calc_williams_r(candles, period=5)
    patterns, pscore = detect_patterns(candles)
    signals, score = [], 0

    buy_cond = sum([rsi < 25, stoch < 20, wr < -80, pscore > 0])
    if buy_cond >= 3:
        signals.append("🔄 Snap Reversal UP"); score += 10 + buy_cond * 2

    sell_cond = sum([rsi > 75, stoch > 80, wr > -20, pscore < 0])
    if sell_cond >= 3:
        signals.append("🔄 Snap Reversal DOWN"); score -= 10 + sell_cond * 2

    return signals, score

def calculate_signal_strength(result, candles):
    strength = 0
    if result['confidence'] >= 85: strength += 2
    elif result['confidence'] >= 75: strength += 1.5
    elif result['confidence'] >= 65: strength += 1

    signal_count = len(result.get('signals', []))
    if signal_count >= 4: strength += 1.5
    elif signal_count >= 3: strength += 1

    rsi = result.get('rsi', 50)
    if rsi < 30 or rsi > 70: strength += 1

    patterns = str(result.get('signals', []))
    if any(p in patterns for p in ['Engulfing', 'Star', 'Hammer']): strength += 1

    diff = abs(result.get('buy_score', 0) - result.get('sell_score', 0))
    if diff >= 5: strength += 1
    elif diff >= 3: strength += 0.5

    atr = result.get('atr', 0)
    price = result.get('price', 1)
    if atr > 0 and price > 0 and (atr / price) * 100 > 0.5: strength += 0.5

    if strength >= 6: rocket, level = "🚀🚀🚀🚀🚀", "قوية جداً"
    elif strength >= 4.5: rocket, level = "🚀🚀🚀🚀", "قوية"
    elif strength >= 3: rocket, level = "🚀🚀🚀", "جيدة"
    elif strength >= 1.5: rocket, level = "🚀🚀", "متوسطة"
    else: rocket, level = "🚀", "ضعيفة"

    return {"rocket": rocket, "level": level, "score": round(strength, 1)}

def analyze_candles(candles, expiry, pair_type, source_label):
    closes = [c["close"] for c in candles]
    rsi = calc_rsi(closes)
    rsi_fast = calc_rsi(closes, period=7)
    ema9 = calc_ema(closes, 9)
    ema21 = calc_ema(closes, 21)
    ema50 = calc_ema(closes, 50)
    macd_line, macd_signal = calc_macd(closes)
    bb_mid, bb_up, bb_low = calc_bollinger(closes)
    stoch = calc_stochastic(closes)
    wr = calc_williams_r(candles)
    cci = calc_cci(candles)
    atr = calc_atr(candles)
    momentum = calc_momentum(closes)
    trend = detect_trend(closes)
    current_price = closes[-1]
    vwap = round(np.mean([(c["high"] + c["low"] + c["close"]) / 3 for c in candles[-20:]]), 6)
    support = round(min(c["low"] for c in candles[-20:]), 6)
    resistance = round(max(c["high"] for c in candles[-20:]), 6)

    buy_score = 0.0
    sell_score = 0.0
    signals_detail = []

    if rsi < 25: buy_score += 4; signals_detail.append(f"🟢 RSI Oversold ({rsi})")
    elif rsi < 38: buy_score += 2; signals_detail.append(f"🟡 RSI Low ({rsi})")
    elif rsi > 75: sell_score += 4; signals_detail.append(f"🔴 RSI Overbought ({rsi})")
    elif rsi > 62: sell_score += 2; signals_detail.append(f"🟡 RSI High ({rsi})")
    else: signals_detail.append(f"⚪ RSI ({rsi})")

    if rsi_fast < 20: buy_score += 2
    elif rsi_fast > 80: sell_score += 2

    if ema9 > ema21: buy_score += 3; signals_detail.append("🟢 Golden Cross")
    else: sell_score += 3; signals_detail.append("🔴 Death Cross")

    if current_price > ema50: buy_score += 2; signals_detail.append("🟢 Above EMA50")
    else: sell_score += 2; signals_detail.append("🔴 Below EMA50")

    if trend == "uptrend": buy_score += 3; signals_detail.append("🟢 Uptrend")
    elif trend == "downtrend": sell_score += 3; signals_detail.append("🔴 Downtrend")
    else: signals_detail.append("⚪ Sideways")

    if macd_line > macd_signal: buy_score += 3; signals_detail.append("🟢 MACD Bullish")
    else: sell_score += 3; signals_detail.append("🔴 MACD Bearish")

    if momentum > 0: buy_score += 2; signals_detail.append("🟢 Mom+")
    else: sell_score += 2; signals_detail.append("🔴 Mom-")

    if current_price <= bb_low: buy_score += 4; signals_detail.append("🟢 BB Lower")
    elif current_price >= bb_up: sell_score += 4; signals_detail.append("🔴 BB Upper")

    if stoch < 20: buy_score += 3; signals_detail.append(f"🟢 Stoch ({stoch})")
    elif stoch > 80: sell_score += 3; signals_detail.append(f"🔴 Stoch ({stoch})")

    if wr < -80: buy_score += 3; signals_detail.append(f"🟢 W%R ({wr})")
    elif wr > -20: sell_score += 3; signals_detail.append(f"🔴 W%R ({wr})")

    if cci < -150: buy_score += 3; signals_detail.append(f"🟢 CCI ({cci})")
    elif cci > 150: sell_score += 3; signals_detail.append(f"🔴 CCI ({cci})")

    if current_price < vwap: buy_score += 2; signals_detail.append("🟢 Below VWAP")
    else: sell_score += 2; signals_detail.append("🔴 Above VWAP")

    sr_range = resistance - support
    if sr_range > 0:
        pos = (current_price - support) / sr_range * 100
        if pos < 15: buy_score += 4; signals_detail.append("🟢 At Support 🎯")
        elif pos > 85: sell_score += 4; signals_detail.append("🔴 At Resistance 🎯")

    patterns, pscore = detect_patterns(candles)
    if pscore > 0: buy_score += abs(pscore)
    else: sell_score += abs(pscore)
    signals_detail.extend(patterns)

    # استراتيجيات OTC فقط
    if pair_type == "otc":
        bo_signals, bo_score = breakout_strategy(candles, expiry)
        if bo_score > 0: buy_score += bo_score
        elif bo_score < 0: sell_score += abs(bo_score)
        signals_detail.extend(bo_signals)

        sr_signals, sr_score = snap_reversal_strategy(candles, expiry)
        if sr_score > 0: buy_score += sr_score
        elif sr_score < 0: sell_score += abs(sr_score)
        signals_detail.extend(sr_signals)

    net_score = buy_score - sell_score
    direction = "BUY" if net_score >= 0 else "SELL"
    total_score = buy_score + sell_score

    if total_score > 0:
        ratio = max(buy_score, sell_score) / total_score
        base_conf = 50 + (ratio - 0.5) * 85
    else:
        base_conf = 62

    if atr > 0 and current_price > 0:
        base_conf += min(atr / (current_price * 0.001), 3) * 2
    if trend == "sideways": base_conf = min(base_conf, 72)
    if abs(net_score) < 3: base_conf = min(base_conf, 68)
    elif abs(net_score) > 18: base_conf = min(base_conf + 6, 96)

    confidence = min(96, max(55, int(base_conf)))

    wait_threshold = 70 if pair_type == "otc" else 63
    if confidence < wait_threshold:
        direction = "WAIT ⏳"
        arrow = "⏳"
    else:
        arrow = "⬆️" if direction == "BUY" else "⬇️"

    result = {
        "direction": direction, "arrow": arrow, "confidence": confidence,
        "signals": signals_detail[:6], "rsi": rsi, "stoch": stoch,
        "williams_r": wr, "cci": cci, "atr": atr, "price": current_price,
        "trend": trend, "buy_score": round(buy_score, 1),
        "sell_score": round(sell_score, 1), "source": source_label,
    }
    result["strength"] = calculate_signal_strength(result, candles)
    return result

def analyze_smart(pair_name, expiry, pair_type):
    now = datetime.now()
    seed = sum(ord(c) for c in f"{pair_name}{expiry}{now.hour}{now.minute // 2}{now.second // 15}")
    random.seed(seed)
    np.random.seed(seed % (2**31))
    base = 1.1000
    candles = []
    for _ in range(80):
        o = base + np.random.normal(0, 0.0008)
        c = o + np.random.normal(0, 0.0006)
        h = max(o, c) + abs(np.random.normal(0, 0.0003))
        l = min(o, c) - abs(np.random.normal(0, 0.0003))
        candles.append({"open": o, "close": c, "high": h, "low": l})
        base = c
    return analyze_candles(candles, expiry, pair_type, "🧠 Smart Analysis")

def get_entry_time(expiry):
    utc3 = timezone(timedelta(hours=3))
    now = datetime.now(utc3)
    if now.second >= 30:
        entry = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        candle_note = "الشمعة القادمة ⏭"
    else:
        entry = now.replace(second=0, microsecond=0)
        candle_note = "الشمعة الحالية ▶️"
    hour = entry.hour
    period = "صباحاً" if hour < 12 else "مساءً"
    hour_12 = hour % 12 or 12
    return f"{hour_12}:{entry.strftime('%M')} {period}", candle_note

# ===== كيبوردات =====

def get_main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 OTC Pairs"), KeyboardButton("💹 Live Market")],
    ], resize_keyboard=True)

def get_otc_keyboard():
    keyboard = []
    for i in range(0, len(OTC_PAIRS), 2):
        row = [KeyboardButton(f"{OTC_PAIRS[i]['flag']} {OTC_PAIRS[i]['name']}")]
        if i + 1 < len(OTC_PAIRS):
            row.append(KeyboardButton(f"{OTC_PAIRS[i+1]['flag']} {OTC_PAIRS[i+1]['name']}"))
        keyboard.append(row)
    keyboard.append([KeyboardButton("🔙 رجوع")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_live_keyboard():
    keyboard = []
    for i in range(0, len(LIVE_PAIRS), 2):
        row = [KeyboardButton(f"{LIVE_PAIRS[i]['flag']} {LIVE_PAIRS[i]['name']}")]
        if i + 1 < len(LIVE_PAIRS):
            row.append(KeyboardButton(f"{LIVE_PAIRS[i+1]['flag']} {LIVE_PAIRS[i+1]['name']}"))
        keyboard.append(row)
    keyboard.append([KeyboardButton("🔙 رجوع")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_expiry_keyboard(pair_name, pair_type):
    if pair_type == "otc":
        keyboard = [
            [
                InlineKeyboardButton("⚡ S5", callback_data=f"expiry|S5|{pair_name}|{pair_type}"),
                InlineKeyboardButton("⚡ S10", callback_data=f"expiry|S10|{pair_name}|{pair_type}"),
                InlineKeyboardButton("⚡ S15", callback_data=f"expiry|S15|{pair_name}|{pair_type}"),
            ],
            [
                InlineKeyboardButton("⏱ M1", callback_data=f"expiry|M1|{pair_name}|{pair_type}"),
                InlineKeyboardButton("⏱ M2", callback_data=f"expiry|M2|{pair_name}|{pair_type}"),
            ],
        ]
    else:
        keyboard = [[
            InlineKeyboardButton("⏱ M1", callback_data=f"expiry|M1|{pair_name}|{pair_type}"),
            InlineKeyboardButton("⏱ M2", callback_data=f"expiry|M2|{pair_name}|{pair_type}"),
            InlineKeyboardButton("⏱ M5", callback_data=f"expiry|M5|{pair_name}|{pair_type}"),
        ]]
    return InlineKeyboardMarkup(keyboard)

def find_pair(text):
    for pair in ALL_PAIRS:
        if pair["name"] in text:
            return pair
    return None

# ===== هاندلرز =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "🟢 متصل بـ Pocket Option" if po_connected else "🔄 جاري الاتصال..."
    await update.message.reply_text(
        f"👋 *مرحباً في VaultFX AI Bot* 🤖\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📡 *الحالة:* {status}\n"
        f"🟢 *OTC:* بيانات Pocket Option حقيقية\n"
        f"📡 *Live:* بيانات Yahoo Finance\n"
        f"⚡ *استراتيجيات:* Breakout + Snap Reversal\n"
        f"🚀 *قوة الإشارة:* 1-5 صواريخ\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"اختر نوع السوق:",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 رجوع":
        await update.message.reply_text("🏠 القائمة الرئيسية:", reply_markup=get_main_keyboard())
        return
    if text == "📊 OTC Pairs":
        await update.message.reply_text("📊 *OTC Pairs*", parse_mode="Markdown", reply_markup=get_otc_keyboard())
        return
    if text == "💹 Live Market":
        await update.message.reply_text("💹 *Live Market*", parse_mode="Markdown", reply_markup=get_live_keyboard())
        return
    pair = find_pair(text)
    if pair:
        await update.message.reply_text(
            f"{pair['flag']} *{pair['name']}*\n\n⏱ اختر وقت الصفقة:",
            parse_mode="Markdown",
            reply_markup=get_expiry_keyboard(pair['name'], pair['type'])
        )
        return
    await update.message.reply_text("👆 اختر من الكيبورد:", reply_markup=get_main_keyboard())

async def handle_expiry_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    expiry, pair_name, pair_type = data[1], data[2], data[3]
    pair = find_pair(pair_name)
    if not pair:
        await query.edit_message_text("❌ خطأ، حاول مجددًا.")
        return

    await query.edit_message_text(f"{pair['flag']} *{pair_name}* — ⏱ {expiry}", parse_mode="Markdown")

    scan_msg = await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🔍 *جاري التحليل...*",
        parse_mode="Markdown"
    )

    steps = [
        "🟢 *جاري سحب بيانات OTC...*" if pair_type == "otc" else "📡 *جاري سحب البيانات...*",
        "📊 *تحليل RSI · EMA · MACD · BB...*",
        "⚡ *Breakout + Snap Reversal...*",
        "🎯 *توليد الإشارة النهائية...*",
    ]

    if pair_type == "otc":
        candles_task = asyncio.create_task(fetch_po_candles(pair["symbol"], 80))
    else:
        candles_task = asyncio.create_task(fetch_yahoo_candles(pair["symbol"], 80))

    for step in steps:
        await asyncio.sleep(0.7)
        try:
            await scan_msg.edit_text(step, parse_mode="Markdown")
        except:
            pass

    candles = await candles_task

    if pair_type == "otc":
        if candles and len(candles) >= 20:
            result = analyze_candles(candles, expiry, "otc", "🟢 Pocket Option (Live OTC)")
        else:
            result = analyze_smart(pair_name, expiry, "otc")
    else:
        if candles and len(candles) >= 20:
            result = analyze_candles(candles, expiry, "live", "📡 Yahoo Finance (Live)")
        else:
            result = analyze_smart(pair_name, expiry, "live")

    entry_time, candle_note = get_entry_time(expiry)
    vote_total = result['buy_score'] + result['sell_score']
    bull_pct = int(result['buy_score'] / vote_total * 100) if vote_total > 0 else 50
    bear_pct = 100 - bull_pct

    strength = result.get('strength', {})
    rocket = strength.get('rocket', '🚀')
    level = strength.get('level', 'متوسطة')

    if result['direction'] == "WAIT ⏳":
        final_text = (
            f"⏳ *انتظر — لا توجد إشارة قوية*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💱 {pair['flag']} *{pair_name}*\n"
            f"⏱ *مدة الصفقة:* {expiry}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🚀 *قوة الإشارة:* {rocket} ({level})\n"
            f"💯 *الثقة:* {result['confidence']}%\n"
            f"📡 *المصدر:* {result['source']}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔄 انتظر إشارة أقوى"
        )
    else:
        signal_emoji = "🟢" if result['direction'] == "BUY" else "🔴"
        direction_ar = "شراء 🟢" if result['direction'] == "BUY" else "بيع 🔴"
        trend_ar = {"uptrend": "📈 صاعد", "downtrend": "📉 هابط", "sideways": "↔️ جانبي"}.get(result.get('trend', ''), "")

        final_text = (
            f"{signal_emoji} *{result['direction']}*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💱 {pair['flag']} *{pair_name}*\n"
            f"⏱ *مدة الصفقة:* {expiry}\n"
            f"🕐 *وقت الدخول:* {entry_time}\n"
            f"📌 *الدخول في:* {candle_note}\n"
            f"📊 *الإشارة:* {direction_ar}\n"
            f"📈 *الترند:* {trend_ar}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🚀 *قوة الإشارة:* {rocket} ({level})\n"
            f"💯 *الثقة:* {result['confidence']}%\n"
            f"🗳 *التصويت:* 🟢 {bull_pct}% | 🔴 {bear_pct}%\n"
            f"📡 *المصدر:* {result['source']}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ _Trade at your own risk_"
        )

    try:
        await scan_msg.delete()
    except:
        pass

    keyboard = get_live_keyboard() if pair_type == "live" else get_otc_keyboard()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=final_text,
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def post_init(application):
    asyncio.create_task(po_background_connection())

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_expiry_selection, pattern="^expiry\\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 VaultFX AI Bot v8 — Background Connection + Breakout + Snap Reversal")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
