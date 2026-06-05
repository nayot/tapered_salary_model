FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app.py budget_grpid.py budget_posid.py ./
COPY .streamlit/config.toml ./.streamlit/config.toml
COPY fonts/ ./fonts/

RUN useradd --create-home --shell /usr/sbin/nologin streamlit \
    && chown -R streamlit:streamlit /app

USER streamlit

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD .venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=5).read()"

CMD [".venv/bin/streamlit", "run", "app.py"]
