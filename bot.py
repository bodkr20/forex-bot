import logging
import asyncio
import json
import re
import numpy as np
import aiohttp
import websockets
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8754472585:AAGIX510vMHTRCTJaGVdnsjn8HjcPqq9-HQ"
PO_SSID = 'PO_SSID = '42["auth",{"sessionToken":"278ef5e23b1e207e7446ad5328594626","uid":"130213513","lang":"en"}]''
ADMIN_CHAT_ID = "6921641426"

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

# ===== Pocket Option Cache =====
po_candles_cache = {}
po_connected = False
ssid_last_updated = datetime.now()
ssid_alert_sent = False

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
                                logger.info("✅ PO Auth Success")
                                break
                        except asyncio.TimeoutError:
                            break

                    if not auth_ok:
                        continue

                    for pair in OTC_PAIRS:
                        now_ts = int(datetime.now().timestamp())
                        req = json.dumps(["subForHistory", {
                            "asset": pair["symbol"],
                            "period": 60,
                            "time": now_ts,
                            "index": 0,
                        }])
                        await ws.send(f"42{req}")
                        await asyncio.sleep(0.3)

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
                                            raw = (payload.get("candles") or payload.get("data") or payload.get("history") or [])
                                            candles = []
                                            for c in raw:
                                                if isinstance(c, dict) and "open" in c:
                                                    candles.append({
                                                        "open": float(c.get("open", 0)),
                                                        "close": float(c.get("close", 0)),
                                                        "high": float(c.get("high", c.get("close", 0))),
                                                        "low": float(c.get("low", c.get("close", 0))),
                                                    })
                                            if candles and asset:
                                                po_candles_cache[asset] = candles
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
    candles = po_candles_cache.get(symbol)
    if candles and len(candles) >= 20:
        return candles[-count:]
    return None

# ===== Yahoo Finance =====

async def fetch_yahoo_multi(symbol: str):
    results = {}
    configs = [
        ("1m", "1d", "short"),
        ("5m", "5d", "medium"),
        ("15m", "1mo", "long"),
    ]
    async with aiohttp.ClientSession() as session:
        for interval, range_, label in configs:
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
                params = {"interval": interval, "range": range_, "includePrePost": "false"}
                headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                result = data.get("chart", {}).get("result", [])
                if not result:
                    continue
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
                if len(candles) >= 20:
                    results[label] = candles
            except Exception as e:
                logger.warning(f"Yahoo {interval} error: {e}")
    return results

# ===== المؤشرات =====

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        return 100.0
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
        patterns.append("⚖️ Doji — Reversal")
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

def analyze_multi_timeframe(candles_dict, expiry):
    mtf_score = 0
    mtf_signals = []
    for label, candles in candles_dict.items():
        if not candles or len(candles) < 20:
            continue
        closes = [c["close"] for c in candles]
        rsi = calc_rsi(closes)
        ema9 = calc_ema(closes, 9)
        ema21 = calc_ema(closes, 21)
        trend = detect_trend(closes)
        tf_score = 0
        if rsi < 35: tf_score += 2
        elif rsi > 65: tf_score -= 2
        if ema9 > ema21: tf_score += 2
        else: tf_score -= 2
        if trend == "uptrend": tf_score += 1
        elif trend == "downtrend": tf_score -= 1
        weight = {"short": 3, "medium": 2, "long": 1}.get(label, 1)
        mtf_score += tf_score * weight
        label_ar = {"short": "1م", "medium": "5م", "long": "15م"}.get(label, label)
        direction = "🟢" if tf_score > 0 else "🔴"
        mtf_signals.append(f"{direction} TF {label_ar}: {'Bullish' if tf_score > 0 else 'Bearish'}")
    return mtf_score, mtf_signals

def analyze_otc(candles, expiry):
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
    support = round(min(c["low"] for c in candles[-20:]), 6)
    resistance = round(max(c["high"] for c in candles[-20:]), 6)

    buy_score = 0.0
    sell_score = 0.0
    signals_detail = []

    if rsi < 18:
        buy_score += 8; signals_detail.append(f"🟢 RSI Deep Oversold ({rsi})")
    elif rsi < 30:
        buy_score += 3; signals_detail.append(f"🟡 RSI Low ({rsi})")
    elif rsi > 82:
        sell_score += 8; signals_detail.append(f"🔴 RSI High Overbought ({rsi})")
    elif rsi > 68:
        sell_score += 3; signals_detail.append(f"🟡 RSI High ({rsi})")
    else:
        signals_detail.append(f"⚪ RSI Neutral ({rsi})")

    if rsi_fast < 14: buy_score += 4
    elif rsi_fast > 86: sell_score += 4

    if ema9 > ema21:
        buy_score += 5; signals_detail.append("🟢 Golden Cross EMA 9/21")
    else:
        sell_score += 5; signals_detail.append("🔴 Death Cross EMA 9/21")

    if current_price > ema50:
        buy_score += 3; signals_detail.append("🟢 Above EMA50")
    else:
        sell_score += 3; signals_detail.append("🔴 Below EMA50")

    if trend == "uptrend":
        buy_score += 5; signals_detail.append("🟢 Uptrend")
    elif trend == "downtrend":
        sell_score += 5; signals_detail.append("🔴 Downtrend")
    else:
        signals_detail.append("⚪ Sideways")
        buy_score -= 2; sell_score -= 2

    if macd_line > macd_signal:
        buy_score += 5; signals_detail.append("🟢 MACD Bullish")
    else:
        sell_score += 5; signals_detail.append("🔴 MACD Bearish")

    if momentum > 0:
        buy_score += 2.5; signals_detail.append("🟢 Positive Momentum")
    else:
        sell_score += 2.5; signals_detail.append("🔴 Negative Momentum")

    if current_price <= bb_low:
        buy_score += 5; signals_detail.append("🟢 BB Lower — BUY")
    elif current_price >= bb_up:
        sell_score += 5; signals_detail.append("🔴 BB Upper — SELL")

    if stoch < 12:
        buy_score += 4; signals_detail.append(f"🟢 Stoch Deep Oversold ({stoch})")
    elif stoch > 88:
        sell_score += 4; signals_detail.append(f"🔴 Stoch High Overbought ({stoch})")

    if wr < -88:
        buy_score += 4; signals_detail.append(f"🟢 W%R Deep Oversold ({wr})")
    elif wr > -12:
        sell_score += 4; signals_detail.append(f"🔴 W%R High Overbought ({wr})")

    if cci < -220:
        buy_score += 4; signals_detail.append(f"🟢 CCI Deep Oversold ({cci})")
    elif cci > 220:
        sell_score += 4; signals_detail.append(f"🔴 CCI High Overbought ({cci})")

    sr_range = resistance - support
    if sr_range > 0:
        pos = (current_price - support) / sr_range * 100
        if pos < 10:
            buy_score += 6; signals_detail.append("🟢 Strong Support 🎯")
        elif pos > 90:
            sell_score += 6; signals_detail.append("🔴 Strong Resistance 🎯")

    patterns, pscore = detect_patterns(candles)
    if pscore > 0: buy_score += abs(pscore)
    else: sell_score += abs(pscore)
    signals_detail.extend(patterns)

    net_score = buy_score - sell_score
    total_score = buy_score + sell_score

    if total_score > 0:
        ratio = max(buy_score, sell_score) / total_score
        base_conf = 50 + (ratio - 0.5) * 90
    else:
        base_conf = 60

    if atr > 0:
        base_conf += min(atr / (current_price * 0.001), 3) * 2

    if trend == "sideways":
        base_conf = min(base_conf, 68)

    if abs(net_score) < 6:
        base_conf = min(base_conf, 62)
    elif abs(net_score) > 22:
        base_conf = min(base_conf + 7, 96)

    confidence = min(96, max(55, int(base_conf)))

    if confidence < 75:
        direction = "WAIT ⏳"
        arrow = "⏳"
    else:
        direction = "BUY" if net_score >= 0 else "SELL"
        arrow = "⬆️" if direction == "BUY" else "⬇️"

    return {
        "direction": direction, "arrow": arrow, "confidence": confidence,
        "signals": signals_detail[:5],
        "rsi": rsi, "stoch": stoch, "wr": wr, "cci": cci, "atr": atr,
        "price": current_price, "trend": trend,
        "buy_score": round(buy_score, 1), "sell_score": round(sell_score, 1),
        "source": "🟢 Pocket Option (Live OTC)",
    }

def analyze_live(candles, expiry, candles_dict=None):
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

    if rsi < 25:
        buy_score += 4; signals_detail.append(f"🟢 RSI Oversold ({rsi})")
    elif rsi < 38:
        buy_score += 2; signals_detail.append(f"🟡 RSI Low ({rsi})")
    elif rsi > 75:
        sell_score += 4; signals_detail.append(f"🔴 RSI Overbought ({rsi})")
    elif rsi > 62:
        sell_score += 2; signals_detail.append(f"🟡 RSI High ({rsi})")
    else:
        signals_detail.append(f"⚪ RSI Neutral ({rsi})")

    if rsi_fast < 20: buy_score += 2
    elif rsi_fast > 80: sell_score += 2

    if ema9 > ema21:
        buy_score += 3; signals_detail.append("🟢 Golden Cross EMA 9/21")
    else:
        sell_score += 3; signals_detail.append("🔴 Death Cross EMA 9/21")

    if current_price > ema50:
        buy_score += 2; signals_detail.append("🟢 Above EMA50")
    else:
        sell_score += 2; signals_detail.append("🔴 Below EMA50")

    if trend == "uptrend":
        buy_score += 3; signals_detail.append("🟢 Uptrend")
    elif trend == "downtrend":
        sell_score += 3; signals_detail.append("🔴 Downtrend")
    else:
        signals_detail.append("⚪ Sideways")

    if macd_line > macd_signal:
        buy_score += 3; signals_detail.append("🟢 MACD Bullish")
    else:
        sell_score += 3; signals_detail.append("🔴 MACD Bearish")

    if momentum > 0:
        buy_score += 1.5; signals_detail.append("🟢 Positive Momentum")
    else:
        sell_score += 1.5; signals_detail.append("🔴 Negative Momentum")

    if current_price <= bb_low:
        buy_score += 3; signals_detail.append("🟢 BB Lower")
    elif current_price >= bb_up:
        sell_score += 3; signals_detail.append("🔴 BB Upper")

    if stoch < 20:
        buy_score += 2; signals_detail.append(f"🟢 Stoch Oversold ({stoch})")
    elif stoch > 80:
        sell_score += 2; signals_detail.append(f"🔴 Stoch Overbought ({stoch})")

    if wr < -80:
        buy_score += 2; signals_detail.append(f"🟢 W%R Oversold ({wr})")
    elif wr > -20:
        sell_score += 2; signals_detail.append(f"🔴 W%R Overbought ({wr})")

    if cci < -150:
        buy_score += 2; signals_detail.append(f"🟢 CCI Oversold ({cci})")
    elif cci > 150:
        sell_score += 2; signals_detail.append(f"🔴 CCI Overbought ({cci})")

    if current_price < vwap:
        buy_score += 2; signals_detail.append("🟢 Below VWAP")
    else:
        sell_score += 2; signals_detail.append("🔴 Above VWAP")

    sr_range = resistance - support
    if sr_range > 0:
        pos = (current_price - support) / sr_range * 100
        if pos < 15:
            buy_score += 4; signals_detail.append("🟢 At Support 🎯")
        elif pos > 85:
            sell_score += 4; signals_detail.append("🔴 At Resistance 🎯")

    patterns, pscore = detect_patterns(candles)
    if pscore > 0: buy_score += abs(pscore)
    else: sell_score += abs(pscore)
    signals_detail.extend(patterns)

    mtf_score = 0
    mtf_signals = []
    if candles_dict and len(candles_dict) > 1:
        mtf_score, mtf_signals = analyze_multi_timeframe(candles_dict, expiry)
        if mtf_score > 0: buy_score += min(abs(mtf_score) * 0.5, 5)
        else: sell_score += min(abs(mtf_score) * 0.5, 5)

    net_score = buy_score - sell_score
    direction = "BUY" if net_score >= 0 else "SELL"
    total_score = buy_score + sell_score

    if total_score > 0:
        ratio = max(buy_score, sell_score) / total_score
        base_conf = 50 + (ratio - 0.5) * 90
    else:
        base_conf = 60

    if atr > 0:
        base_conf += min(atr / (current_price * 0.001), 3) * 2

    if trend == "sideways":
        base_conf = min(base_conf, 70)

    if abs(net_score) < 3:
        base_conf = min(base_conf, 65)
    elif abs(net_score) > 15:
        base_conf = min(base_conf + 5, 96)

    if mtf_score != 0 and ((mtf_score > 0) == (net_score > 0)):
        base_conf = min(base_conf + 4, 96)

    confidence = min(96, max(55, int(base_conf)))
    arrow = "⬆️" if direction == "BUY" else "⬇️"

    if confidence < 63:
        direction = "WAIT ⏳"
        arrow = "⏳"

    return {
        "direction": direction, "arrow": arrow, "confidence": confidence,
        "signals": signals_detail[:5],
        "mtf_signals": mtf_signals[:3],
        "rsi": rsi, "stoch": stoch, "wr": wr, "cci": cci, "atr": atr,
        "price": current_price, "trend": trend,
        "buy_score": round(buy_score, 1), "sell_score": round(sell_score, 1),
        "source": "📡 Yahoo Finance (Live)",
    }

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

# ===== SSID Manager =====

async def check_ssid_health(app):
    global ssid_alert_sent, po_connected
    while True:
        await asyncio.sleep(60)
        if not po_connected and not ssid_alert_sent:
            ssid_alert_sent = True
            try:
                await app.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=(
                        "🔴 *تنبيه: انقطع اتصال Pocket Option*\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        "🕐 *الوقت:* " + datetime.now().strftime("%I:%M %p") + "\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        "📋 *لتجديد SSID:*\n"
                        "1️⃣ افتح pocketoption.com\n"
                        "2️⃣ سجل دخول\n"
                        "3️⃣ افتح F12 > Network > WS\n"
                        "4️⃣ ابحث عن سطر فيه `auth` وانسخه\n"
                        "5️⃣ أرسل لي:\n"
                        "`/update_ssid 42[\"auth\",{\"sessionToken\":\"xxx\",\"uid\":\"123\",\"lang\":\"en\"}]`"
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Failed to send SSID alert: {e}")
        elif po_connected and ssid_alert_sent:
            ssid_alert_sent = False
            try:
                await app.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text="🟢 *تم استعادة اتصال Pocket Option* ✅",
                    parse_mode="Markdown"
                )
            except:
                pass

async def update_ssid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PO_SSID, ssid_last_updated, ssid_alert_sent
    if not context.args:
        await update.message.reply_text(
            "❌ *استخدام خاطئ*\n\n"
            "أرسل الأمر كذا:\n"
            "`/update_ssid 42[\"auth\",{\"sessionToken\":\"xxx\",\"uid\":\"123\",\"lang\":\"en\"}]`",
            parse_mode="Markdown"
        )
        return
    new_ssid = " ".join(context.args)
    if not new_ssid.startswith("42") or "sessionToken" not in new_ssid:
        await update.message.reply_text("❌ *صيغة SSID غير صحيحة*", parse_mode="Markdown")
        return
    try:
        match = re.search(r'"sessionToken":"([^"]+)"', new_ssid)
        uid_match = re.search(r'"uid":"([^"]+)"', new_ssid)
        token = match.group(1)[:10] + "..." if match else "???"
        uid = uid_match.group(1) if uid_match else "???"
    except:
        token, uid = "???", "???"
    PO_SSID = new_ssid
    ssid_last_updated = datetime.now()
    ssid_alert_sent = False
    await update.message.reply_text(
        f"✅ *تم تحديث SSID بنجاح*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔑 *التوكن:* {token}\n"
        f"👤 *UID:* {uid}\n"
        f"🕐 *الوقت:* {datetime.now().strftime('%I:%M %p')}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔄 جاري إعادة الاتصال...",
        parse_mode="Markdown"
    )
    asyncio.create_task(po_background_connection())

async def check_ssid_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ssid_last_updated, po_connected
    time_since = datetime.now() - ssid_last_updated
    hours = time_since.seconds // 3600
    minutes = (time_since.seconds % 3600) // 60
    status = "🟢 متصل" if po_connected else "🔴 منقطع"
    await update.message.reply_text(
        f"📊 *حالة SSID*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📡 *الحالة:* {status}\n"
        f"🕐 *آخر تحديث:* منذ {hours}h {minutes}m\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{'✅ شغال' if po_connected else '⚠️ يحتاج تجديد'}\n\n"
        f"للتجديد: `/update_ssid [الكود]`",
        parse_mode="Markdown"
    )

# ===== هاندلرز =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "🟢 متصل بـ Pocket Option" if po_connected else "🔴 جاري الاتصال بـ Pocket Option..."
    await update.message.reply_text(
        f"👋 *مرحباً في VaultFX AI Bot* 🤖\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📡 *الحالة:* {status}\n"
        f"🟢 *OTC:* بيانات حقيقية من Pocket Option\n"
        f"📡 *Live:* تحليل من Yahoo Finance\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ *OTC لا يعطي إشارات وهمية أبداً*\n"
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
        text="🔍 *جاري سحب البيانات الحقيقية...*",
        parse_mode="Markdown"
    )

    if pair_type == "otc":
        steps = [
            "🟢 *جاري الاتصال بـ Pocket Option...*",
            "📊 *جاري سحب بيانات OTC الحية...*",
            "🧠 *تحليل RSI · EMA · MACD · Bollinger...*",
            "🔥 *فحص Stochastic · W%R · CCI · ATR...*",
            "🎯 *توليد الإشارة النهائية...*",
        ]
    else:
        steps = [
            "📡 *جاري سحب البيانات من 3 إطارات زمنية...*",
            "📊 *تحليل RSI · EMA · MACD · Momentum...*",
            "🔥 *فحص MTF · Williams%R · CCI · ATR...*",
            "🎯 *توليد الإشارة النهائية...*",
        ]

    if pair_type == "live":
        candles_task = asyncio.create_task(fetch_yahoo_multi(pair["symbol"]))
    else:
        candles_task = None

    for step in steps:
        await asyncio.sleep(0.8)
        try:
            await scan_msg.edit_text(step, parse_mode="Markdown")
        except:
            pass

    if pair_type == "otc":
        candles = await fetch_po_candles(pair["symbol"], 80)
        if not candles or len(candles) < 20:
            await scan_msg.delete()
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=(
                    f"⚠️ *لا توجد بيانات حقيقية كافية*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💱 {pair['flag']} *{pair_name}*\n"
                    f"📡 *المصدر:* Pocket Option\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🔴 *الحالة:* {'متصل' if po_connected else 'جاري الاتصال...'}\n"
                    f"📊 *البيانات:* {len(candles) if candles else 0} شمعة فقط\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"❌ *لا يمكن إعطاء إشارة بدون بيانات حقيقية*\n"
                    f"🔄 حاول مرة أخرى بعد قليل"
                ),
                parse_mode="Markdown",
                reply_markup=get_otc_keyboard()
            )
            return
        result = analyze_otc(candles, expiry)
    else:
        candles_dict = None
        candles = None
        if candles_task:
            candles_dict = await candles_task
            if candles_dict:
                candles = candles_dict.get("short") or candles_dict.get("medium")
        if not candles or len(candles) < 20:
            await scan_msg.delete()
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=(
                    f"⚠️ *تعذر سحب البيانات من Yahoo Finance*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💱 {pair['flag']} *{pair_name}*\n"
                    f"🔄 حاول مرة أخرى بعد قليل"
                ),
                parse_mode="Markdown",
                reply_markup=get_live_keyboard()
            )
            return
        result = analyze_live(candles, expiry, candles_dict=candles_dict)

    try:
        await scan_msg.delete()
    except:
        pass

    entry_time, candle_note = get_entry_time(expiry)

    vote_total = result['buy_score'] + result['sell_score']
    if vote_total > 0:
        bull_pct = int(result['buy_score'] / vote_total * 100)
        bear_pct = 100 - bull_pct
    else:
        bull_pct, bear_pct = 50, 50

    if result['direction'] == "WAIT ⏳":
        final_text = (
            f"⏳ *انتظر — لا توجد إشارة قوية*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💱 {pair['flag']} *{pair_name}*\n"
            f"⏱ *مدة الصفقة:* {expiry}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💯 *الثقة:* {result['confidence']}% — ضعيفة\n"
            f"📊 *الاتجاه:* غير واضح\n"
            f"📡 *المصدر:* {result['source']}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ *لا تدخل الصفقة الآن*\n"
            f"🔄 انتظر إشارة أقوى"
        )
    else:
        signal_emoji = "🟢" if result['direction'] == "BUY" else "🔴"
        direction_ar = "شراء 🟢" if result['direction'] == "BUY" else "بيع 🔴"
        trend_ar = {"uptrend": "📈 صاعد", "downtrend": "📉 هابط", "sideways": "↔️ جانبي"}.get(result['trend'], "")
        mtf_text = "\n".join(result.get('mtf_signals', []))
        mtf_section = f"🕐 *MTF Analysis:*\n{mtf_text}\n━━━━━━━━━━━━━━━━━━\n" if mtf_text else ""

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
            f"💯 *الثقة:* {result['confidence']}%\n"
            f"🗳 *التصويت:* 🟢 {bull_pct}% | 🔴 {bear_pct}%\n"
            f"📡 *المصدر:* {result['source']}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{mtf_section}"
            f"⚠️ *Trade at your own risk*\n"
            f"✅ *بيانات حقيقية 100%*"
        )

    keyboard = get_live_keyboard() if pair_type == "live" else get_otc_keyboard()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=final_text,
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def post_init(application):
    asyncio.create_task(po_background_connection())
    asyncio.create_task(check_ssid_health(application))

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("update_ssid", update_ssid))
    app.add_handler(CommandHandler("ssid_status", check_ssid_status))
    app.add_handler(CallbackQueryHandler(handle_expiry_selection, pattern="^expiry\\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 VaultFX AI Bot — OTC Real Data Only | SSID Auto-Alert")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
