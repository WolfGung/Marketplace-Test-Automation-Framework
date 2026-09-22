FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY stand/requirements.txt ./stand/requirements.txt
RUN pip install --no-cache-dir -r stand/requirements.txt

COPY stand ./stand

EXPOSE 8092
CMD ["uvicorn", "stand.app.main:app", "--host", "0.0.0.0", "--port", "8092"]
