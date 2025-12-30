FROM python:3.11-slim

WORKDIR /app

# Install requirements first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project to maintain 'Microservices' as a package
COPY . .

# Set the environment so 'import Microservices' works 
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 1500

# Ensure the folder name matches your directory exactly (Notification vs monitor)
CMD ["python", "notifREST.py"]