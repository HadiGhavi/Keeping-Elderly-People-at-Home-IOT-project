FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy files to the container
COPY catalogService.py .
COPY resource_catalog.json .
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Port to expose
EXPOSE 5001

# Service execution
CMD ["python", "catalogService.py"]
