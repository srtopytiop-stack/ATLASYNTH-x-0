FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY .env.example ./
ENV PYTHONPATH=/app/backend
EXPOSE 8000
CMD ["uvicorn", "atlasynth.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
