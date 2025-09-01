FROM python:3.11-slim

WORKDIR /app

RUN pip install cherrypy requests

COPY ./Microservices /app/Microservices

EXPOSE 9000

CMD ["python", "Microservices/Report/panel.py"]
