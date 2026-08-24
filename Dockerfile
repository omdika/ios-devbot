FROM python:3.11-slim

# Install git dan dependensi sistem yang dibutuhkan
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy seluruh file project
COPY . .

# Konfigurasi Git author default di dalam container
RUN git config --global user.email "ai-agent@gcp.internal" && \
    git config --global user.name "AI Coding Agent"

# Jalankan bot
CMD ["python", "bot.py"]
