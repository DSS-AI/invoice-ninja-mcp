FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY in_mcp/ in_mcp/
COPY scripts/ scripts/

# L3: nicht als root laufen - relevant nur zusammen mit einer RCE in FastMCP/uvicorn/requests, dann
# hat der Prozess keinen Root-Schreibzugriff auf das gemountete Datenverzeichnis (Log, ggf. PMS-DB).
RUN useradd -r -u 10001 app && mkdir -p /data && chown app /data
USER app

EXPOSE 8539
CMD ["python", "-m", "in_mcp.server"]
