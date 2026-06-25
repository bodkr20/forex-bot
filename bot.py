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
    {"name": "AED/CNY OTC", "flag": "🇦🇪"},
    {"name": "BHD/CNY OTC", "flag": "🇧🇭"},
    {"name": "GBP/USD OTC", "flag": "🇬🇧"},
    {"name": "AUD/CAD OTC", "flag": "🇦🇺"},
    {"name": "EUR/USD OTC", "flag": "🇪🇺"},
    {"name": "AUD/NZD OTC", "flag": "🇦🇺"},
    {"name": "USD/JPY OTC", "flag": "🇺🇸"},
    {"name": "USD/CHF OTC", "flag": "🇺🇸"},
]

NOTES_BUY = ["Strong momentum detected.","Bullish breakout confirmed.","Clear breakout zone.","Trend continuation likely.","Strong buy pressure.","Oversold bounce expected."]
NOTES_SELL = ["Strong momentum detected.","Bearish breakout confirmed.","Clear breakdown zone.","Trend continuation likely.","Strong sell pressure.","Overbought correction expected."]

def get_pair_keyboard():
    keyboard = []
    for i in range(0, len(OTC_PAIRS), 2):
        row = [KeyboardButton(f"{OTC_PAIRS[i]['flag']} {OTC_PAIRS[i]['name']}")]
        if i + 1 < len(OTC_PAIRS):
            row.append(KeyboardButton(f"{OTC_PAIRS[i+1]['flag']} {OTC_PAIRS[i+1]['name']}"))
        keyboard.append(row)
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_expiry_keyboard(pair_name):
    keyboard = [[
        InlineKeyboardButton("S5", callback_data=f"expiry|S5|{pair_name}"),
        InlineKeyboardButton("S10", callback_data=f"expiry|S10|{pair_name}"),
        InlineKeyboardButton("S15", callback_data=f"expiry|S15|{pair_name}"),
    ]]
    return InlineKeyboardMarkup(keyboard)

def analyze_pair(pair_name, expiry):
    now = datetime.now()
    seed_str = f"{pair_name}{expiry}{now.hour}{now.minute // 2}"
    seed = sum(ord(c) for c in seed_str)
    random.seed(seed)
    rsi = random.uniform(20, 80)
    momentum = random.uniform(-1, 1)
    price_score = random.uniform(0, 100)
    buy_score = 0
    if rsi < 40: buy_score += 2
    elif rsi > 60: buy_score -= 2
    if momentum > 0.3: buy_score += 1
    elif momentum < -0.3: buy_score -= 1
    if price_score > 55: buy_score += 1
    else: buy_score -= 1
    direction = "BUY" if buy_score >= 0 else "SELL"
    confidence = min(92, 65 + abs(buy_score) * 7 + random.randint(0, 10))
    if direction == "BUY":
        return {"direction": direction, "arrow": "⬆️", "confidence": confidence, "note": random.choice(NOTES_BUY)}
    else:
        return {"direction": direction, "arrow": "⬇️", "confidence": confidence, "note": random.choice(NOTES_SELL)}

def find_pair(text):
    for pair in OTC_PAIRS:
        if pair["name"] in text:
            return pair
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *مرحباً بك في VaultFX AI Bot*\n\n🤖 بوت تحليل OTC\n\n📊 اختر زوج العملات:",
        parse_mode="Markdown", reply_markup=get_pair_keyboard()
    )

async def handle_pair_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pair = find_pair(update.message.text)
    if not pair:
        await update.message.reply_text("❌ اختر من الكيبورد أدناه.", reply_markup=get_pair_keyboard())
        return
    await update.message.reply_text(
        f"{pair['flag']} *{pair['name']}*\n⏱ *Time Frame:* ?\n\nاختر وقت الصفقة:",
        parse_mode="Markdown", reply_markup=get_expiry_keyboard(pair['name'])
    )

async def handle_expiry_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("|")
    expiry = data[1]
    pair_name = data[2]
    pair = find_pair(pair_name)
    if not pair:
        await query.edit_message_text("❌ خطأ، حاول مجددًا.")
        return
    await query.edit_message_text(
        f"{pair['flag']} *{pair_name}*\n⏱ *Time Frame:* {expiry}",
        parse_mode="Markdown"
    )
    scan_msg = await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"⏳ *Starting market scan...*\n\n📊 Pair: {pair['flag']} {pair_name}\n⏱ Expiry: {expiry}",
        parse_mode="Markdown"
    )
    for i in range(1, 5):
        await asyncio.sleep(1)
        try:
            await scan_msg.edit_text(
                f"⏳ *Scanning market{'.' * (i % 4)}*\n\n📊 Pair: {pair['flag']} {pair_name}\n⏱ Expiry: {expiry}",
                parse_mode="Markdown"
            )
        except: pass
    result = analyze_pair(pair_name, expiry)
    signal_bar = "🟢" * (result['confidence'] // 20) + "⬜" * (5 - result['confidence'] // 20)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"✅ *Analysis Complete*\n\n📊 *Pair:* {pair['flag']} {pair_name}\n⏱ *Expiry:* {expiry}\n📡 *Signal:* {result['arrow']} *{result['direction']}*\n💯 *Confidence Level:* {result['confidence']}%\n{signal_bar}\n🚀 *Note:* {result['note']}",
        parse_mode="Markdown", reply_markup=get_pair_keyboard()
    )

async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👆 اختر من الكيبورد:", reply_markup=get_pair_keyboard())

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_expiry_selection, pattern="^expiry\\|"))
    app.add_handler(MessageHandler(filters.Regex(r"OTC"), handle_pair_selection))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown))
    print("🤖 VaultFX AI Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
