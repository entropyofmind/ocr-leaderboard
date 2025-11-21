FROM python:3.10-bullseye

# Install essential system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1-mesa-glx \
        libglib2.0-0 \
        ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY . .

CMD ["python", "bot.py"]
