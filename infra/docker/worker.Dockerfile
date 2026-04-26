FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/workers/copy_engine/src:/app/packages/domain/src:/app/packages/exchange_adapters/src:/app/packages/shared_events/src

COPY requirements.in ./requirements.in
RUN pip install --no-cache-dir -r requirements.in

COPY workers/copy_engine ./workers/copy_engine
COPY packages ./packages

CMD ["python", "-m", "copy_trade_copy_engine.main"]
