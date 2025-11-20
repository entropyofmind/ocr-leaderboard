# Use full Debian-based Python image
FROM python:3.11

# ----------------- INSTALL SYSTEM DEPENDENCIES -----------------
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    locales \
    && rm -rf /var/lib/apt/lists/*

# ----------------- CONFIGURE UTF-8 LOCALE (fix emojis) -----------------
RUN locale-gen en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

# ----------------- SET WORKDIR -----------------
WORKDIR /app

# ----------------- COPY FILES -----------------
COPY requirements.txt .
COPY bot.py .

# ----------------- INSTALL PYTHON DEPENDENCIES -----------------
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# ----------------- EXPOSE PORT FOR FLASK -----------------
EXPOSE 10000

# ----------------- START BOT -----------------
CMD ["python", "bot.py"]
