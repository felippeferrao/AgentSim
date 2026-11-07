FROM node:22-bookworm-slim AS codex
RUN npm install -g @openai/codex@0.167.0
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 AGENTSIM_BIND=0.0.0.0 AGENTSIM_DB=/app/.local/agentsim.db HOME=/app/.local BROWSER_PATH=/usr/bin/chromium
RUN apt-get update && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 chromium fonts-dejavu-core ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=codex /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=codex /usr/local/bin/node /usr/local/bin/node
RUN ln -s /usr/local/lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex
WORKDIR /app
COPY requirements.lock .
RUN pip install -r requirements.lock
COPY . .
RUN useradd -u 10001 -d /app/.local -M agentsim && mkdir -p /app/.local && chown agentsim:agentsim /app/.local
USER agentsim
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8080/login').status == 200"
CMD ["python", "server.py"]
