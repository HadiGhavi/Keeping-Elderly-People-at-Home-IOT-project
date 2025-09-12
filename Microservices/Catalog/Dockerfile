FROM python:3.11-slim

# تنظیم دایرکتوری کاری
WORKDIR /app

# کپی فایل‌ها به کانتینر
COPY catalogService.py .
COPY resource_catalog.json .
COPY requirements.txt .

# نصب وابستگی‌ها
RUN pip install --no-cache-dir -r requirements.txt

# باز کردن پورت
EXPOSE 5001

# اجرای سرویس
CMD ["python", "catalogService.py"]
