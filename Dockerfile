FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 MPLCONFIGDIR=/tmp/matplotlib
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tzdata && \
    rm -rf /var/lib/apt/lists/*
COPY requirements-cloud.lock requirements-bootstrap.lock ./
COPY deployment/wheelhouse/ ./wheelhouse/
RUN pip install --no-cache-dir --no-index --find-links=wheelhouse --require-hashes -r requirements-bootstrap.lock && \
    pip install --no-cache-dir --no-index --find-links=wheelhouse --require-hashes -r requirements-cloud.lock
RUN python -c "from zoneinfo import ZoneInfo; ZoneInfo('Asia/Kolkata')"
COPY *.py ./
COPY research/ ./research/
COPY events.csv TRADING_PLAN.md ./
COPY data/ ./seed-data/
COPY results/ ./seed-results/
COPY dashboard/dist/ ./dashboard/dist/
RUN mkdir -p /state/data /state/results /state/paper && \
    ln -s /state/data data && ln -s /state/results results && ln -s /state/paper paper && \
    chown -R 10001:10001 /app /state
EXPOSE 8765
CMD ["python", "cloud_bootstrap.py"]
