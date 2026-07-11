# 1. استخدام نسخة بايثون مستقرة ومخففة لتقليل حجم الحاوية وسرعة البناء
FROM python:3.10-slim

# 2. تثبيت الأدوات الأساسية للنظام لتجنب مشاكل بناء مكتبات الأرقام مثل pandas و numpy
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 3. تحديد مجلد العمل داخل السيرفر
WORKDIR /app

# 4. نسخ ملف المكتبات أولاً للاستفادة من الـ Cache وسرعة الـ Deploy مستقبلاً
COPY requirements.txt .

# 5. تثبيت المكتبات البرمجية المطلوبة للبوت
RUN pip install --no-cache-dir -r requirements.txt

# 6. نسخ باقي ملفات المشروع (كود البوت والملفات الأخرى) إلى السيرفر
COPY . .

# 7. ضبط توقيت النظام الداخلي للحاوية على توقيت مكة المكرمة (آسيا/الرياض)
ENV TZ=Asia/Riyadh

# 8. الأمر النهائي لتشغيل البوت كخدمة خلفية (Worker) مستمرة
CMD ["python", "bot.py"]
