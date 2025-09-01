FROM python:3.10-slim

WORKDIR /app

COPY . .

RUN pip install cherrypy requests

EXPOSE 1500

CMD ["python", "notif.py"]
