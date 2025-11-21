FROM python:3.10-slim

# Fix apt-get failure by adding basic tools first
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        apt-transport-https \
        ca-certificates \
        libgl1-mesa-glx \
        libglib2.0-0 \
        git \
        wget \
        build-essential \
        ffmpeg \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["python", "bot.py"]
