FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

COPY requirements.txt .

RUN pip install --upgrade pip

RUN pip install \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.3.1+cpu

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python"]