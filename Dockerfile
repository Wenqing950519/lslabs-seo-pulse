# SEO Pulse hosted mode (Cloud Run). Configuration and deployment: docs/hosting.md
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra google --extra hosted --no-install-project
COPY seo_pulse_mcp ./seo_pulse_mcp
RUN uv sync --frozen --no-dev --extra google --extra hosted

RUN useradd --create-home seo-pulse
USER seo-pulse
ENV SEO_PULSE_CONNECTOR=google SEO_PULSE_TRANSPORT=http
# Cloud Run sets PORT; the server reads it when --port is not given.
CMD ["/app/.venv/bin/seo-pulse", "serve", "--transport", "http", "--host", "0.0.0.0"]
