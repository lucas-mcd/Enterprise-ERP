FROM python:3.12-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements.lock .
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.lock
COPY pyproject.toml .
COPY src ./src
RUN /opt/venv/bin/pip install --no-cache-dir --no-deps .

FROM python:3.12-slim AS runtime
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN groupadd --gid 10001 erp && useradd --uid 10001 --gid erp --create-home erp
RUN mkdir -p /home/erp/beat /home/erp/reports && chown -R erp:erp /home/erp/beat /home/erp/reports
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=erp:erp alembic.ini .
COPY --chown=erp:erp migrations ./migrations
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "erp.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
