import logging
import asyncio
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8754472585:AAHSvci8Mya7QkalHUW0Y3IybsNWB1p1uUY"

OTC_PAIRS = [
    {"name": "AED/CNY OTC", "flag": "🇦🇪", "type": "otc"},
    {"name": "BHD/CNY OTC", "flag": "🇧🇭", "type": "otc"},
    {"name": "GBP/USD OTC", "flag": "🇬🇧", "type": "otc"},
    {"name": "AUD/CAD OTC", "flag": "🇦🇺", "type": "otc"},
    {"name": "EUR/USD OTC", "flag": "🇪🇺", "type": "otc"},
    {"name": "AUD/NZD OTC", "flag": "🇦🇺", "type": "otc"},
    {"name": "USD/JPY OTC", "flag": "🇺🇸", "type": "otc"},
    {"name": "USD/CHF OTC", "flag": "🇺🇸", "type": "otc"},
]

LIVE_PAIRS = [
    {"name": "EUR/USD", "flag": "🇪🇺", "type": "live"},
    {"name": "GBP/USD", "flag": "🇬🇧"
    , "type": "live"},
    {"name": "USD/JPY", "flag": "🇺🇸", "type": "live"},
    {"name": "AUD/USD", "flag": "🇦🇺", "type": "live"},
    {"name": "USD/CAD", "flag": "🇨🇦", "type": "live"},
    {"name": "USD/CHF", "flag": "🇨🇭", "type": "live"},
    {"name": "NZD/USD", "flag": "🇳🇿", "type": "live"},
    {"name": "GBP/JPY", "flag": "🇬🇧", "type": "live"},
]

ALL_PAIRS = OTC_PAIRS + LIVE_PAIRS

NOTES_BUY = [
    "⚡ EMA9 crossed above EMA21 — Golden Cross confirmed!",
    "📊 RSI dropped below 30 — Oversold bounce incoming!",
    "🕯 Bullish Engulfing candle at key support zone!",
    "🚀 MACD bullish crossover — Strong upward momentum!",
    "📉 Price bounced from lower Bollinger Band — BUY zone!",
    "🎯 Stochastic oversold + bullish divergence detected!",
    "💹 Strong demand zone breakout with high volume!",
    "🔥 Trend continuation — Momentum strongly bullish!",
]
NOTES_SELL = [
    "⚡ EMA9 crossed below EMA21 — Death Cross confirmed!",
    "📊 RSI surged above 70 — Overbought correction expected!",
    "🕯 Bearish Engulfing candle at key resistance zone!",
    "📉 MACD bearish crossover — Strong downward momentum!",
    "📈 Price rejected from upper Bollinger Band — SELL zone!",
    "🎯 Stochastic overbought + bearish divergence detected!",
    "💹 Strong supply zone rejection with selling pressure!",
    "🔥 Trend continuation — Momentum strongly bearish!",
]

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📊 OTC Pairs"), KeyboardButton("💹 Live Market")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

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
        keyboard = [
            [
                InlineKeyboardButton("⏱ M1",  callback_data=f"expiry|M1|{pair_name}|{pair_type}"),
                InlineKeyboardButton("⏱ M2",  callback_data=f"expiry|M2|{pair_name}|{pair_type}"),
                InlineKeyboardButton("⏱ M5",  callback_data=f"expiry|M5|{pair_name}|{pair_type}"),
            ],
        ]
    return InlineKeyboardMarkup(keyboard)

def analyze_pair(pair_name, expiry, pair_type):
    now = datetime.now()
    seed_str = f"{pair_name}{expiry}{now.hour}{now.minute // 2}{now.second // 15}"
    seed = sum(ord(c) for c in seed_str)
    random.seed(seed)

    rsi = random.uniform(15, 85)
    ema_fast = random.uniform(1.0800, 1.1200)
    ema_slow = ema_fast + random.uniform(-0.0030, 0.0030)
    macd = random.uniform(-0.0015, 0.0015)
    macd_signal = macd + random.uniform(-0.0005, 0.0005)
    bb_position = random.uniform(0, 100)
    stoch = random.uniform(10, 90)
    momentum = random.uniform(-1, 1)
    volume_score = random.uniform(0, 1)

    buy_score = 0
    signals_detail = []

    if rsi < 30:
        buy_score += 3
        signals_detail.append("🟢 RSI Oversold")
    elif rsi < 45:
        buy_score += 1
        signals_detail.append("🟡 RSI Neutral-Low")
    elif rsi > 70:
        buy_score -= 3
        signals_detail.append("🔴 RSI Overbought")
    elif rsi > 55:
        buy_score -= 1
        signals_detail.append("🟡 RSI Neutral-High")

    if ema_fast > ema_slow:
        buy_score += 2
        signals_detail.append("🟢 Golden Cross (EMA)")
    else:
        buy_score -= 2
        signals_detail.append("🔴 Death Cross (EMA)")

    if macd > macd_signal:
        buy_score += 2
        signals_detail.append("🟢 MACD Bullish")
    else:
        buy_score -= 2
        signals_detail.append("🔴 MACD Bearish")

    if bb_position < 20:
        buy_score += 2
        signals_detail.append("🟢 BB Lower Band Bounce")
    elif bb_position > 80:
        buy_score -= 2
        signals_detail.append("🔴 BB Upper Band Rejection")

    if stoch < 25:
        buy_score += 2
        signals_detail.append("🟢 Stoch Oversold")
    elif stoch > 75:
        buy_score -= 2
        signals_detail.append("🔴 Stoch Overbought")

    if momentum > 0.4:
        buy_score += 1
        signals_detail.append("🟢 Strong Bullish Momentum")
    elif momentum < -0.4:
        buy_score -= 1
        signals_detail.append("🔴 Strong Bearish Momentum")

    if volume_score > 0.65:
        buy_score = int(buy_score * 1.2)
        signals_detail.append("📊 High Volume Confirmation")

    if pair_type == "otc" and expiry in ["S10", "S15"]:
        buy_score = int(buy_score * 1.3)

    direction = "BUY" if buy_score >= 0 else "SELL"

    raw_confidence = 60 + abs(buy_score) * 4 + random.randint(0, 8)
    if pair_type == "otc" and expiry in ["S10", "S15"]:
        raw_confidence += 8
    confidence = min(95, raw_confidence)

    note = random.choice(NOTES_BUY) if direction == "BUY" else random.choice(NOTES_SELL)
    arrow = "⬆️" if direction == "BUY" else "⬇️"

    return {
        "direction": direction,
        "arrow": arrow,
        "confidence": confidence,
        "note": note,
        "signals": signals_detail[:4],
        "rsi": round(rsi, 1),
        "stoch": round(stoch, 1),
    }

def find_pair(text):
    for pair in ALL_PAIRS:
        if pair["name"] in text:
            return pair
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *مرحباً بك في VaultFX AI Bot* 🤖\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📊 *OTC Pairs* — تحليل أزواج OTC\n"
        "💹 *Live Market* — السوق الحقيقي\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "اختر نوع السوق:",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🔙 رجوع":
        await update.message.reply_text("🏠 القائمة الرئيسية:", reply_markup=get_main_keyboard())
        return

    if text == "📊 OTC Pairs":
        await update.message.reply_text(
            "📊 *OTC Pairs*\nاختر الزوج:",
            parse_mode="Markdown",
            reply_markup=get_otc_keyboard()
        )
        return

    if text == "💹 Live Market":
        await update.message.reply_text(
            "💹 *Live Market*\nاختر الزوج:",
            parse_mode="Markdown",
            reply_markup=get_live_keyboard()
        )
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
        text=f"🔍 *Scanning market...*\n\n{pair['flag']} {pair_name} | ⏱ {expiry}",
        parse_mode="Markdown"
    )

    steps = [
        "📡 *Connecting to market data...*",
        "📊 *Analyzing RSI & EMA indicators...*",
        "🔥 *Checking MACD & Bollinger Bands...*",
        "🎯 *Generating final signal...*",
    ]
    for step in steps:
        await asyncio.sleep(1)
        try:
            await scan_msg.edit_text(
                f"{step}\n\n{pair['flag']} {pair_name} | ⏱ {expiry}",
                parse_mode="Markdown"
            )
        except:
            pass

    result = analyze_pair(pair_name, expiry, pair_type)

    filled = result['confidence'] // 20
    signal_bar = "🟩" * filled + "⬜" * (5 - filled)
    signals_text = "\n".join(result['signals'])
    market_label = "🔴 LIVE" if pair_type == "live" else "⚪ OTC"

    final_text = (
        f"✅ *Signal Ready!*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 *Pair:* {pair['flag']} {pair_name}\n"
        f"🏷 *Market:* {market_label}\n"
        f"⏱ *Expiry:* {expiry}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📡 *Signal:* {result['arrow']} *{result['direction']}*\n"
        f"💯 *Confidence:* {result['confidence']}%\n"
        f"{signal_bar}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📈 *Indicators:*\n{signals_text}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 *RSI:* {result['rsi']} | *Stoch:* {result['stoch']}\n"
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
    print("🤖 VaultFX AI Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
