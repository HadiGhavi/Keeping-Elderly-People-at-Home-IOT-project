FROM python:3.11-slim

WORKDIR /app

COPY Microservices/Monitor/requirements.txt . 
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 3500

CMD ["python", "Microservices/Monitor/monitorREST.py"]