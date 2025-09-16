FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all adapter files
COPY . .

EXPOSE 3000

ENV PYTHONUNBUFFERED=1

CMD ["python", "databaseService.py"]