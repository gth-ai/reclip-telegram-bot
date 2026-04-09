FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir flask yt-dlp

COPY . .

EXPOSE 8899
ENV HOST=0.0.0.0
ENV DOWNLOADS_PATH=/downloads
CMD ["python", "app.py"]
