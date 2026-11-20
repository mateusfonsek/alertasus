FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY simulador/ ./simulador/
COPY tests/ ./tests/

ENTRYPOINT ["python", "-m", "simulador"]
CMD ["--cenario", "normal", "--taxa", "10", "--duracao", "30"]
