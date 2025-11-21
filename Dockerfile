FROM python:3.10-slim

# Install Tesseract OCR and dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends tesseract-ocr libtesseract-dev libleptonica-dev pkg-config && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy only requirements first to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy rest of the app
COPY . .

# Set environment variables (optional, can be set in Render)
ENV PYTHONUNBUFFERED=1

# Run the bot
CMD ["python", "bot.py"]
