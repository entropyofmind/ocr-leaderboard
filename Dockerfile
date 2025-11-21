# Use slim Python image
FROM python:3.10-slim

# Install system dependencies + Tesseract
RUN apt-get update && \
    apt-get install -y tesseract-ocr libtesseract-dev libleptonica-dev pkg-config && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy only requirements first for Docker layer caching
COPY requirements.txt .

# Install Python dependencies
# --no-cache-dir keeps image size small
RUN pip install --no-cache-dir -r requirements.txt

# Copy rest of the code
COPY . .

# Set default command
CMD ["python", "bot.py"]
