FROM python:3.10-slim

# Add sources & essential tools
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gnupg \
        ca-certificates \
        apt-transport-https \
        software-properties-common \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies for PaddleOCR
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1-mesa-glx \
        libglib2.0-0 \
        git \
        wget \
        build-essential \
        ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["python", "bot.py"]
