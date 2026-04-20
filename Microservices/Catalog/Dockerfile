FROM python:3.11-slim

WORKDIR /app

# Copy only dependencies first
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY catalogService.py .
COPY resource_catalog.json .

EXPOSE 5001

CMD ["python", "catalogService.py"]