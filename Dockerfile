# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

# ffmpeg is required by yt-dlp/PyTgCalls for audio transcoding into voice chats.
# unzip is required by the Deno install script below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg git curl unzip \
    && rm -rf /var/lib/apt/lists/*

# Deno is the recommended JavaScript runtime for yt-dlp-ejs, which yt-dlp
# uses to solve YouTube's client-side challenge scripts. Without it, format
# extraction fails or is severely limited on many YouTube videos.
ENV DENO_INSTALL="/usr/local/deno"
RUN curl -fsSL https://deno.land/install.sh | sh \
    && ln -s "${DENO_INSTALL}/bin/deno" /usr/local/bin/deno
ENV PATH="${DENO_INSTALL}/bin:${PATH}"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p cache logs assets/fonts assets/images

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Basic liveness signal for orchestrators that support HEALTHCHECK.
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import pathlib,sys; sys.exit(0 if pathlib.Path('cache').exists() else 1)"

CMD ["python", "main.py"]

