FROM python:3.12-slim
ARG INSTALL_AI=0
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-ai.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN if [ "$INSTALL_AI" = "1" ]; then pip install --no-cache-dir -r requirements-ai.txt; fi
COPY . .
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data CONFIG_DIR=/app/config
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD curl -fs http://localhost:8000/api/health || exit 1
CMD ["python", "-m", "app"]
