FROM caddy:2-alpine AS caddy
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY --from=caddy /usr/bin/caddy /usr/local/bin/caddy
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt 'gunicorn>=23,<24' \
    && groupadd --system classpulse \
    && useradd --system --gid classpulse --home-dir /tmp classpulse
COPY . /app
ENV PORT=8080
EXPOSE 8080
CMD ["python", "-m", "deploy.staging_server"]
