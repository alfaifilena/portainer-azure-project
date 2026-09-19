FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app/ai-monitor

COPY monitor.py run_monitor.py ai_client.py report_api.py ./

CMD ["python", "run_monitor.py"]
