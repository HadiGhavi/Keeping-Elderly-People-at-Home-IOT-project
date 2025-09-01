FROM python:3.11-slim

WORKDIR /app

COPY . .

COPY Microservices/Monitor/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "Microservices/Monitor/monitor.py"]
