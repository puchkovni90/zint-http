# Используем минимальный базовый образ с Zint
FROM minidocks/zint:latest

# Устанавливаем Python, создаем виртуальное окружение, обновляем setuptools и устанавливаем Flask
RUN apk add --no-cache python3 && \
    python3 -m venv /venv && \
    /venv/bin/pip install --no-cache-dir --upgrade setuptools>=78.1.1 flask

# Копируем только скрипт приложения
COPY app.py /app.py

# Копирование лицензионных файлов
COPY LICENSE NOTICE.md /app/
COPY licenses /app/licenses/

# Оптимизация переменных среды Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Метаданные образа
LABEL org.opencontainers.image.title="Zint HTTP Service" \
      org.opencontainers.image.description="HTTP wrapper for Zint barcode generator" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/puchkovni90/zint-http" \
      org.opencontainers.image.licenses="MIT, BSD-3-Clause, GPL-3.0"

# Указываем порт для доступа к сервису
EXPOSE 5000

# Запускаем приложение через виртуальное окружение
CMD ["/venv/bin/python", "/app.py"]
