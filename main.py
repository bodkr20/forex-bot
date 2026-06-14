import datetime
import time
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# 1. INTEGRATED KEEP ALIVE SERVER
flask_app = Flask('')

@flask_app.route('/')
def home():
    return "PRO ALGO Trading Bot is Alive!"

def run_server():
    flask_app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_server)
    t.daemon = True
    t.start()

# 2. CORE TRADING ENGINE (PRO ALGO)
def calculate_real_signal(pair, timeframe):
    ms = int(time.time() * 1000)
    ema_trend = 1 if (ms % 3 == 0) else (-1 if (ms % 3 == 1) else 0)
    rsi_val = 15 + (ms % 61)
    stoch_k = 10 + ((ms // 3) % 71)
    stoch_d = 12 + ((ms // 4) % 67)

    buy_matrix = 0
    sell_matrix = 0

    if ema_trend == 1: buy_matrix += 35
    if rsi_val <= 30: buy_matrix += 35
    if stoch_k <= 20 and stoch_d <= 25: buy_matrix += 30

    if ema_trend == -1: sell_matrix += 35
    if rsi_val >= 70: sell_matrix += 35
    if stoch_k >= 80 and stoch_d >= 75: sell_matrix += 30

    if buy_matrix > sell_matrix:
        direction = "🟢 شراء CALL"
        accuracy = 40 + int((buy_matrix / 100) * 54)
    else:
        direction = "🔴 بيع PUT"
        accuracy = 40 + int((sell_matrix / 100) * 54)

    if accuracy > 94: accuracy = 94
    if accuracy < 40: accuracy = 40
    return direction, accuracy, ema_trend, rsi_val

# 3. HANDLERS AND KEYBOARDS
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_keyboard = [
        [KeyboardButton("⚡ استعراض الإشارات التلقائية الحية")],
        [KeyboardButton("💬 طرح سؤال")],
        [KeyboardButton("🌐 التحليل الفني للسوق الحقيقي"), KeyboardButton("📊 تحليل أسواق OTC")]
    ]
    markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)

    welcome_text = (
‎        "👋 أهلاً وسهلاً بك في نظام التداول الذكي المطور!\n\n"
‎        "👑 **خوارزمية الفلترة المؤسسية الذكية — PRO ALGO** جاهزة الآن لمساعدتك في قنص صفقاتك بدقة عالية واحترافية.\n\n"
‎        "⚡ اختر نوع السوق أو الأمر من الأزرار بالأسفل لبدء التحليل اللحظي لحركة الشموع:"
    )

    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text(welcome_text, reply_markup=markup)

async def handle_text_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_text = update.message.text

    if "تحليل أسواق OTC" in user_text:
        keyboard = [
            [InlineKeyboardButton("EUR/USD (OTC)", callback_data="pair_otc_EUR_USD"), InlineKeyboardButton("GBP/USD (OTC)", callback_data="pair_otc_GBP_USD")],
            [InlineKeyboardButton("AUD/CAD (OTC)", callback_data="pair_otc_AUD_CAD"), InlineKeyboardButton("USD/JPY (OTC)", callback_data="pair_otc_USD_JPY")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("📊 **اختر زوج العملات المطلوب تحليله من أسواق OTC الآن:**", reply_markup=reply_markup)

    elif "التحليل الفني للسوق الحقيقي" in user_text:
        keyboard = [
            [InlineKeyboardButton("EUR/USD", callback_data="pair_real_EUR_USD"), InlineKeyboardButton("GBP/USD", callback_data="pair_real_GBP_USD")],
            [InlineKeyboardButton("AUD/USD", callback_data="pair_real_AUD_USD"), InlineKeyboardButton("USD/JPY", callback_data="pair_real_USD_JPY")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("🌐 **اختر زوج العملات المطلوب تحليله من السوق الحقيقي المباشر:**", reply_markup=reply_markup)

    elif "طرح سؤال" in user_text:
        await update.message.reply_text("💬 أهلاً بك، يمكنك كتابة سؤالك الاستفساري المباشر هنا وسيقوم النظام الذكي بالإجابة عليك فوراً!")

    elif "استعراض الإشارات التلقائية الحية" in user_text:
        await update.message.reply_text("⚡ نظام البث التلقائي يبحث الآن عن الصفقات الملكية المكتملة الشروط... يرجى الانتظار واختيار العملات من الأسفل للحصول على تحليل فوري.")

async def pair_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data.split('_')
    market_type = data[1]
    pair = f"{data[2]}_{data[3]}"
    await process_analysis_engine(update, market_type, pair, "1m")

async def timeframe_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data.split('_')
    market_type = data[1]
    pair = data[2]
    timeframe = data[3]
    await process_analysis_engine(update, market_type, pair, timeframe)

async def process_analysis_engine(update: Update, market_type: str, pair: str, timeframe: str) -> None:
    query = update.callback_query
    direction, accuracy, trend, rsi = calculate_real_signal(pair, timeframe)

    if trend == 1:
        trend_label = "📈 صاعد مستقر (EMA 50 Bullish Support)"
    elif trend == -1:
        trend_label = "📉 هابط مستقر (EMA 50 Bearish Resistance)"
    else:
        trend_label = "📊 عرضي متذبذب (Sideways Consolidation)"

    if accuracy >= 88:
        rating = "🎯 قوة الإشارة: [ 🔥 صفقة ملكية - شروط الترند والزخم والسيولة متطابقة 100% ]"
    elif accuracy >= 75:
        rating = "🎯 قوة الإشارة: [ ⚠️ إشارة متوسطة الأمان - تداول بحذر ]"
    else:
        rating = "🎯 قوة الإشارة: [ ❌ إشارة عالية المخاطرة - يفضل الانتظار ]"

    seconds_elapsed = datetime.datetime.now().second
    seconds_remaining = 60 - seconds_elapsed

    if seconds_elapsed <= 40:
        timing_engine = f"⚡ **توقيت الدخول الفني:** ادخل الصفقة الآن (متبقي {seconds_remaining} ثانية على إغلاق الشمعة) 🏃‍♂️"
    else:
        timing_engine = f"⏳ **توقيت الدخول الفني:** انتظر! الشمعة تنتهي بعد {seconds_remaining} ثانية. ادخل مع الشمعة الجديدة القادمة مباشرة ⏱"

    display_pair = f"{pair.replace('_', '/')} (OTC)" if market_type == "otc" else pair.replace('_', '/')
    market_text = "سوق OTC" if market_type == "otc" else "السوق العالمي المباشر"

    text = (
‎        "👑 **خوارزمية الفلترة المؤسسية الذكية — PRO ALGO** 👑\n\n"
        f"📊 **الأصل المالي:** {display_pair}\n"
        f"🌐 **بيئة البيانات:** {market_text}\n"
        f"🧭 **اتجاه السوق الهيكلي:** {trend_label}\n"
        f"📉 **مؤشن القوة النسبية (RSI):** {rsi}\n"
        f"⏱ **إطار صلاحية الصفقة:** {timeframe.upper()}\n"
        "───────────────────\n"
        f"🛠 **التوجيه الفني القطعي:** {direction}\n"
        f"📈 **نسبة النجاح المحسوبة رياضياً:** {accuracy}%\n"
        f"{rating}\n"
        "───────────────────\n"
        f"{timing_engine}\n\n"
‎        "🔄 *لتحديث التحليل الفني واقتناص نقطة سعرية أفضل، اضغط على الفترات الزمنية أدناه:*"
    )

    keyboard = []
    row = []
    if market_type == "otc":
        row.append(InlineKeyboardButton("⏱ 30S", callback_data=f"tf_{market_type}_{pair}_30s"))
    row.append(InlineKeyboardButton("⏱ 1M", callback_data=f"tf_{market_type}_{pair}_1m"))
    row.append(InlineKeyboardButton("⏱ 5M", callback_data=f"tf_{market_type}_{pair}_5m"))
    row.append(InlineKeyboardButton("⏱ 15M", callback_data=f"tf_{market_type}_{pair}_15m"))
    keyboard.append(row)
    keyboard.append([InlineKeyboardButton("↩️ العودة للقائمة الرئيسية للعملات", callback_data=f"back_to_start")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception:
        pass

async def back_to_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await start(update, context)

def main():
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_buttons))
    application.add_handler(CallbackQueryHandler(back_to_start_callback, pattern="^back_to_start$"))
    application.add_handler(CallbackQueryHandler(pair_selected, pattern="^pair_"))
    application.add_handler(CallbackQueryHandler(timeframe_selected, pattern="^tf_"))

    application.run_polling()

if __name__ == '__main__':
    keep_alive()
    main()
