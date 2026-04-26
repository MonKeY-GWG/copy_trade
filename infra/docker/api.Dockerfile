FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/apps/api/src:/app/packages/domain/src:/app/packages/exchange_adapters/src:/app/packages/shared_events/src

COPY requirements.in ./requirements.in
RUN pip install --no-cache-dir -r requirements.in

COPY apps/api ./apps/api
COPY packages ./packages

CMD ["uvicorn", "copy_trade_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
