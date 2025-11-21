FROM python:3.10-slim


# Install dependencies
RUN apt-get update && \
apt-get install -y tesseract-ocr libtesseract-dev && \
apt-get clean


WORKDIR /app
COPY . /app


RUN pip install --no-cache-dir -r requirements.txt


CMD ["python", "bot.py"]
