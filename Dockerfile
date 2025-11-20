FROM python:3.11-slim

# Prevent interactive tzdata prompt
ENV DEBIAN_FRONTEND=noninteractive

# Install system packages and Tesseract OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-osd \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Working directory
WORKDIR /app

# Install Python dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source files
COPY . .

# Expose Flask port
EXPOSE 10000

# Start bot + webserver (both run inside bot.py)
CMD ["python", "bot.py"]
