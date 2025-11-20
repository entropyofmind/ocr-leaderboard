FROM python:3.12-slim

# Install system deps for Tesseract/OpenCV (headless, no GUI junk)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libglx-mesa0 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "bot.py"]
