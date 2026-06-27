# نستخدم صورة Python رسمية
FROM python:3.11-slim

# نحدد مجلد العمل داخل الحاوية
WORKDIR /app

# ننسخ ملف المكتبات أولاً للاستفادة من الـ Cache
COPY requirements.txt .

# نثبت المكتبات
RUN pip install --no-cache-dir -r requirements.txt

# ننسخ باقي ملفات المشروع
COPY . .

# الأمر اللي يشتغل البوت
CMD ["python", "bot.py"]
