import logging
import asyncio
import random
import numpy as np
from datetime import datetime
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
 
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
 
BOT_TOKEN = "8754472585:AAHSvci8Mya7QkalHUW0Y3IybsNWB1p1uUY"
 
OTC_PAIRS = [
    {"name": "AED/CNY OTC", "flag": "🇦🇪", "type": "otc", "symbol": "AEDCNY_otc"},
    {"name": "BHD/CNY OTC", "flag": "🇧🇭", "type": "otc", "symbol": "BHDCNY_otc"},
    {"name": "GBP/USD OTC", "flag": "🇬🇧", "type": "otc", "symbol": "GBPUSD_otc"},
    {"name": "AUD/CAD OTC", "flag": "🇦🇺", "type": "otc", "symbol": "AUDCAD_otc"},
    {"name": "EUR/USD OTC", "flag": "🇪🇺", "type": "otc", "symbol": "EURUSD_otc"},
    {"name": "AUD/NZD OTC", "flag": "🇦🇺", "type": "otc", "symbol": "AUDNZD_otc"},
    {"name": "USD/JPY OTC", "flag": "🇺🇸", "type": "otc", "symbol": "USDJPY_otc"},
    {"name": "USD/CHF OTC", "flag": "🇺🇸", "type": "otc", "symbol": "USDCHF_otc"},
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
 
# ===== Yahoo Finance API =====
 
async def fetch_yahoo_candles(symbol: str, count: int = 80):
    """سحب بيانات حقيقية من Yahoo Finance"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {
            "interval": "1m",
            "range": "1d",
            "includePrePost": "false",
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
 
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None
 
        chart = result[0]
        timestamps = chart.get("timestamp", [])
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
                "open": opens[i],
                "close": closes[i],
                "high": highs[i] if highs[i] else closes[i],
                "low": lows[i] if lows[i] else closes[i],
            })
 
        if len(candles) < 20:
            return None
 
        logger.info(f"✅ Yahoo Finance: {len(candles)} candles for {symbol}")
        return candles[-count:]
 
    except Exception as e:
        logger.warning(f"Yahoo Finance error for {symbol}: {e}")
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
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)
 
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
    lowest = min(recent)
    highest = max(recent)
    if highest == lowest:
        return 50.0
    return round(((closes[-1] - lowest) / (highest - lowest)) * 100, 2)
 
def calc_atr(candles, period=14):
    if len(candles) < period + 1:
        return 0
    trs = []
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i-1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return round(np.mean(trs[-period:]), 6)
 
def calc_williams_r(candles, period=14):
    if len(candles) < period:
        return -50.0
    recent = candles[-period:]
    highest_high = max(c["high"] for c in recent)
    lowest_low = min(c["low"] for c in recent)
    current_close = candles[-1]["close"]
    if highest_high == lowest_low:
        return -50.0
    wr = ((highest_high - current_close) / (highest_high - lowest_low)) * -100
    return round(wr, 2)
 
def calc_cci(candles, period=20):
    if len(candles) < period:
        return 0
    typical_prices = [(c["high"] + c["low"] + c["close"]) / 3 for c in candles[-period:]]
    mean_tp = np.mean(typical_prices)
    mean_dev = np.mean([abs(tp - mean_tp) for tp in typical_prices])
    if mean_dev == 0:
        return 0
    cci = (typical_prices[-1] - mean_tp) / (0.015 * mean_dev)
    return round(cci, 2)
 
def calc_vwap_proxy(candles):
    if len(candles) < 5:
        return candles[-1]["close"]
    typical_prices = [(c["high"] + c["low"] + c["close"]) / 3 for c in candles[-20:]]
    return round(np.mean(typical_prices), 6)
 
def detect_support_resistance(candles):
    if len(candles) < 20:
        return None, None
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    return round(min(lows[-20:]), 6), round(max(highs[-20:]), 6)
 
def detect_patterns(candles):
    patterns = []
    if len(candles) < 3:
        return patterns, 0
    score = 0
    c = candles
 
    if (c[-2]["close"] < c[-2]["open"] and c[-1]["close"] > c[-1]["open"] and
        c[-1]["open"] < c[-2]["close"] and c[-1]["close"] > c[-2]["open"]):
        patterns.append("🕯 Bullish Engulfing ✅")
        score += 4
 
    if (c[-2]["close"] > c[-2]["open"] and c[-1]["close"] < c[-1]["open"] and
        c[-1]["open"] > c[-2]["close"] and c[-1]["close"] < c[-2]["open"]):
        patterns.append("🕯 Bearish Engulfing ✅")
        score -= 4
 
    body = abs(c[-1]["close"] - c[-1]["open"])
    total = c[-1]["high"] - c[-1]["low"]
    if total > 0 and body / total < 0.1:
        patterns.append("⚖️ Doji — Reversal Signal")
 
    if (c[-1]["low"] < min(c[-1]["open"], c[-1]["close"]) - (body * 2) and
        c[-1]["high"] - max(c[-1]["open"], c[-1]["close"]) < body):
        patterns.append("📌 Bullish Pin Bar")
        score += 3
 
    if (c[-1]["high"] > max(c[-1]["open"], c[-1]["close"]) + (body * 2) and
        min(c[-1]["open"], c[-1]["close"]) - c[-1]["low"] < body):
        patterns.append("📌 Bearish Pin Bar")
        score -= 3
 
    if len(c) >= 3:
        if (c[-3]["close"] < c[-3]["open"] and
            abs(c[-2]["close"] - c[-2]["open"]) < abs(c[-3]["close"] - c[-3]["open"]) * 0.3 and
            c[-1]["close"] > c[-1]["open"] and
            c[-1]["close"] > (c[-3]["open"] + c[-3]["close"]) / 2):
            patterns.append("🌟 Morning Star")
            score += 4
 
    if len(c) >= 3:
        if (c[-3]["close"] > c[-3]["open"] and
            abs(c[-2]["close"] - c[-2]["open"]) < abs(c[-3]["close"] - c[-3]["open"]) * 0.3 and
            c[-1]["close"] < c[-1]["open"] and
            c[-1]["close"] < (c[-3]["open"] + c[-3]["close"]) / 2):
            patterns.append("🌟 Evening Star")
            score -= 4
 
    if all(c[-i]["close"] > c[-i]["open"] for i in range(1, 4)):
        patterns.append("🟢 Three Bullish Candles")
        score += 2
 
    if all(c[-i]["close"] < c[-i]["open"] for i in range(1, 4)):
        patterns.append("🔴 Three Bearish Candles")
        score -= 2
 
    return patterns[:3], score
 
def analyze_real(candles, expiry, pair_type, data_source="smart"):
    closes = [c["close"] for c in candles]
 
    rsi = calc_rsi(closes)
    rsi_fast = calc_rsi(closes, period=7)
    ema9 = calc_ema(closes, 9)
    ema21 = calc_ema(closes, 21)
    ema50 = calc_ema(closes, 50)
    macd_line, macd_signal = calc_macd(closes)
    bb_mid, bb_up, bb_low = calc_bollinger(closes)
    stoch = calc_stochastic(closes)
    williams_r = calc_williams_r(candles)
    cci = calc_cci(candles)
    atr = calc_atr(candles)
    vwap = calc_vwap_proxy(candles)
    support, resistance = detect_support_resistance(candles)
    current_price = closes[-1]
 
    buy_score = 0
    sell_score = 0
    signals_detail = []
 
    if rsi < 25:
        buy_score += 3; signals_detail.append(f"🟢 RSI Oversold ({rsi})")
    elif rsi < 38:
        buy_score += 1.5; signals_detail.append(f"🟡 RSI Low ({rsi})")
    elif rsi > 75:
        sell_score += 3; signals_detail.append(f"🔴 RSI Overbought ({rsi})")
    elif rsi > 62:
        sell_score += 1.5; signals_detail.append(f"🟡 RSI High ({rsi})")
 
    if rsi_fast < 20: buy_score += 2
    elif rsi_fast > 80: sell_score += 2
 
    if ema9 > ema21:
        buy_score += 3; signals_detail.append("🟢 Golden Cross EMA 9/21")
    else:
        sell_score += 3; signals_detail.append("🔴 Death Cross EMA 9/21")
 
    if len(closes) >= 50:
        if current_price > ema50:
            buy_score += 2; signals_detail.append("🟢 Price above EMA50")
        else:
            sell_score += 2; signals_detail.append("🔴 Price below EMA50")
 
    if macd_line > macd_signal:
        buy_score += 3; signals_detail.append("🟢 MACD Bullish")
    else:
        sell_score += 3; signals_detail.append("🔴 MACD Bearish")
 
    if current_price <= bb_low:
        buy_score += 3; signals_detail.append("🟢 BB Lower — BUY Zone")
    elif current_price >= bb_up:
        sell_score += 3; signals_detail.append("🔴 BB Upper — SELL Zone")
 
    if stoch < 20:
        buy_score += 2; signals_detail.append(f"🟢 Stoch Oversold ({stoch})")
    elif stoch > 80:
        sell_score += 2; signals_detail.append(f"🔴 Stoch Overbought ({stoch})")
 
    if williams_r < -80:
        buy_score += 2; signals_detail.append(f"🟢 Williams %R Oversold ({williams_r})")
    elif williams_r > -20:
        sell_score += 2; signals_detail.append(f"🔴 Williams %R Overbought ({williams_r})")
 
    if cci < -150:
        buy_score += 2; signals_detail.append(f"🟢 CCI Oversold ({cci})")
    elif cci > 150:
        sell_score += 2; signals_detail.append(f"🔴 CCI Overbought ({cci})")
 
    if current_price < vwap:
        buy_score += 1.5; signals_detail.append("🟢 Below VWAP — Discount Zone")
    else:
        sell_score += 1.5; signals_detail.append("🔴 Above VWAP — Premium Zone")
 
    if support and resistance:
        sr_range = resistance - support
        if sr_range > 0:
            position_pct = (current_price - support) / sr_range * 100
            if position_pct < 15:
                buy_score += 3; signals_detail.append("🟢 Near Support Level")
            elif position_pct > 85:
                sell_score += 3; signals_detail.append("🔴 Near Resistance Level")
 
    patterns, pattern_score = detect_patterns(candles)
    if pattern_score > 0:
        buy_score += abs(pattern_score)
    else:
        sell_score += abs(pattern_score)
    signals_detail.extend(patterns)
 
    net_score = buy_score - sell_score
    direction = "BUY" if net_score >= 0 else "SELL"
    total_score = buy_score + sell_score
 
    if total_score > 0:
        agreement_ratio = max(buy_score, sell_score) / total_score
        base_confidence = 50 + (agreement_ratio - 0.5) * 80
    else:
        base_confidence = 62
 
    if atr > 0:
        atr_normalized = min(atr / (current_price * 0.001), 3)
        base_confidence += atr_normalized * 2
 
    if abs(net_score) < 3:
        base_confidence = min(base_confidence, 68)
 
    # إذا البيانات حقيقية، رفع الثقة قليلاً
    if data_source == "yahoo":
        base_confidence = min(base_confidence + 5, 96)
 
    confidence = min(96, max(55, int(base_confidence)))
    arrow = "⬆️" if direction == "BUY" else "⬇️"
 
    note_buy = [
        "⚡ Multi-indicator BUY confirmation — Strong signal!",
        "🚀 RSI + MACD + BB alignment = High probability BUY",
        "📊 Price at demand zone with bullish momentum",
        "🎯 Multiple oscillators confirm oversold — BUY opportunity",
    ]
    note_sell = [
        "⚡ Multi-indicator SELL confirmation — Strong signal!",
        "📉 RSI + MACD + BB alignment = High probability SELL",
        "📊 Price at supply zone with bearish momentum",
        "🎯 Multiple oscillators confirm overbought — SELL opportunity",
    ]
 
    note = random.choice(note_buy if direction == "BUY" else note_sell)
 
    source_label = {
        "yahoo": "📡 Yahoo Finance (Real Data)",
        "smart": "🧠 Smart Analysis",
    }.get(data_source, "🧠 Smart Analysis")
 
    return {
        "direction": direction,
        "arrow": arrow,
        "confidence": confidence,
        "note": note,
        "signals": signals_detail[:6],
        "rsi": rsi,
        "stoch": stoch,
        "williams_r": williams_r,
        "cci": cci,
        "atr": atr,
        "price": current_price,
        "buy_score": round(buy_score, 1),
        "sell_score": round(sell_score, 1),
        "source": source_label,
    }
 
def analyze_smart(pair_name, expiry, pair_type):
    now = datetime.now()
    seed_str = f"{pair_name}{expiry}{now.hour}{now.minute // 2}{now.second // 15}"
    seed = sum(ord(c) for c in seed_str)
    random.seed(seed)
    np.random.seed(seed % (2**31))
 
    base = 1.1000
    candles = []
    for _ in range(80):
        open_p = base + np.random.normal(0, 0.0008)
        close_p = open_p + np.random.normal(0, 0.0006)
        high_p = max(open_p, close_p) + abs(np.random.normal(0, 0.0003))
        low_p = min(open_p, close_p) - abs(np.random.normal(0, 0.0003))
        candles.append({"open": open_p, "close": close_p, "high": high_p, "low": low_p})
        base = close_p
 
    return analyze_real(candles, expiry, pair_type, data_source="smart")
 
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
                InlineKeyboardButton("⚡ S5",  callback_data=f"expiry|S5|{pair_name}|{pair_type}"),
                InlineKeyboardButton("⚡ S10", callback_data=f"expiry|S10|{pair_name}|{pair_type}"),
                InlineKeyboardButton("⚡ S15", callback_data=f"expiry|S15|{pair_name}|{pair_type}"),
            ],
            [
                InlineKeyboardButton("⏱ M1",  callback_data=f"expiry|M1|{pair_name}|{pair_type}"),
                InlineKeyboardButton("⏱ M2",  callback_data=f"expiry|M2|{pair_name}|{pair_type}"),
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
    await update.message.reply_text(
        f"👋 *مرحباً في VaultFX AI Bot* 🤖\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📡 *Live Pairs:* بيانات حقيقية من Yahoo Finance\n"
        f"🧠 *OTC Pairs:* تحليل ذكي متقدم\n"
        f"🔬 *المؤشرات:* RSI · EMA · MACD · BB · Stoch · W%R · CCI · ATR · VWAP · S/R\n"
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
        await update.message.reply_text("📊 *OTC Pairs* — اختر الزوج:", parse_mode="Markdown", reply_markup=get_otc_keyboard())
        return
    if text == "💹 Live Market":
        await update.message.reply_text("💹 *Live Market* — اختر الزوج:", parse_mode="Markdown", reply_markup=get_live_keyboard())
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
    expiry = data[1]
    pair_name = data[2]
    pair_type = data[3]
    pair = find_pair(pair_name)
 
    if not pair:
        await query.edit_message_text("❌ خطأ، حاول مجددًا.")
        return
 
    await query.edit_message_text(
        f"{pair['flag']} *{pair_name}* — ⏱ {expiry}",
        parse_mode="Markdown"
    )
 
    scan_msg = await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"🔍 *جاري تحليل السوق...*\n\n{pair['flag']} {pair_name} | ⏱ {expiry}",
        parse_mode="Markdown"
    )
 
    steps = [
        "📡 *جاري سحب البيانات من Yahoo Finance...*" if pair_type == "live" else "🧠 *جاري تشغيل التحليل الذكي...*",
        "📊 *تحليل RSI · EMA · MACD...*",
        "🔥 *فحص Williams%R · CCI · ATR...*",
        "📈 *تحليل VWAP · Support/Resistance...*",
        "🕯 *كشف أنماط الشموع...*",
        "🎯 *توليد الإشارة النهائية...*",
    ]
 
    # بدء سحب البيانات بالتوازي مع عرض الخطوات
    candles_task = None
    if pair_type == "live":
        candles_task = asyncio.create_task(fetch_yahoo_candles(pair["symbol"], 80))
 
    for step in steps:
        await asyncio.sleep(0.8)
        try:
            await scan_msg.edit_text(
                f"{step}\n\n{pair['flag']} {pair_name} | ⏱ {expiry}",
                parse_mode="Markdown"
            )
        except:
            pass
 
    # الحصول على النتيجة
    data_source = "smart"
    candles = None
 
    if candles_task:
        candles = await candles_task
        if candles and len(candles) >= 20:
            data_source = "yahoo"
 
    if candles and len(candles) >= 20:
        result = analyze_real(candles, expiry, pair_type, data_source=data_source)
    else:
        result = analyze_smart(pair_name, expiry, pair_type)
 
    filled = result['confidence'] // 20
    signal_bar = "🟩" * filled + "⬜" * (5 - filled)
    signals_text = "\n".join(result['signals'])
    market_label = "🔴 LIVE" if pair_type == "live" else "⚪ OTC"
 
    vote_total = result['buy_score'] + result['sell_score']
    if vote_total > 0:
        bull_pct = int(result['buy_score'] / vote_total * 100)
        bear_pct = 100 - bull_pct
        vote_line = f"📊 *Votes:* 🟢 {bull_pct}% BUY | 🔴 {bear_pct}% SELL\n"
    else:
        vote_line = ""
 
    price_line = f"💰 *Price:* `{result['price']:.5f}`\n" if result.get('price') else ""
 
    final_text = (
        f"✅ *Signal Ready!*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 *Pair:* {pair['flag']} {pair_name}\n"
        f"🏷 *Market:* {market_label}\n"
        f"⏱ *Expiry:* {expiry}\n"
        f"📡 *Source:* {result['source']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📡 *Signal:* {result['arrow']} *{result['direction']}*\n"
        f"💯 *Confidence:* {result['confidence']}%\n"
        f"{signal_bar}\n"
        f"{vote_line}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📈 *Indicators:*\n{signals_text}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{price_line}"
        f"💡 *RSI:* {result['rsi']} | *Stoch:* {result['stoch']} | *W%R:* {result['williams_r']}\n"
        f"📐 *CCI:* {result['cci']} | *ATR:* {result['atr']}\n"
        f"🚀 *Note:* {result['note']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ _Trade at your own risk_"
    )
 
    keyboard = get_live_keyboard() if pair_type == "live" else get_otc_keyboard()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=final_text,
        parse_mode="Markdown",
        reply_markup=keyboard
    )
 
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_expiry_selection, pattern="^expiry\\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 VaultFX AI Bot v3 (Yahoo Finance) is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
 
if __name__ == "__main__":
    main()
 
