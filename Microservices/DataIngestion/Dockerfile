FROM python:3.11-slim

WORKDIR /app

COPY . .

COPY Microservices/DataIngestion/requirements.txt requirements.txt

RUN pip install --no-cache-dir -r requirements.txt
COPY ClassificationAlgorithm ./ClassificationAlgorithm

EXPOSE 2500

ENV PYTHONUNBUFFERED=1
ENV BASE_DIR=/app/ClassificationAlgorithm

CMD ["python", "Microservices/DataIngestion/dataHandler.py"]
