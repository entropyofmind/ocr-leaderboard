# Use full Debian-based Python image (guaranteed to have all libs)
FROM python:3.11

# Install Tesseract + OpenCV system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY bot.py .

# Expose port for Render
EXPOSE 10000

# Start the bot
CMD ["python", "bot.py"]
