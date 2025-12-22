FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for better caching
COPY Microservices/DataIngestion/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project structure to maintain package hierarchy
COPY . .

EXPOSE 2500

ENV PYTHONUNBUFFERED=1

ENV PYTHONPATH=/app
ENV BASE_DIR=/app/ClassificationAlgorithm

CMD ["python", "Microservices/DataIngestion/dataHandlerREST.py"]