# Official Python slim image (small + has apt)
FROM python:3.11-slim

# Install system packages: Tesseract OCR + OpenCV dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the bot code
COPY bot.py .

# Tell pytesseract where tesseract binary is (critical!)
RUN python -c "import pytesseract; pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'"

# Expose port for Render's health checks
EXPOSE 10000

# Start the bot
CMD ["python", "bot.py"]
