FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data FILE_SEARCH_ROOTS=/files
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY jarvis ./jarvis
RUN useradd -m jarvis && mkdir -p /data /files && chown jarvis /data
USER jarvis
VOLUME ["/data"]
ENTRYPOINT ["python", "-m", "jarvis"]
