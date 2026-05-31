FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py store.py ./
COPY templates/ templates/
COPY static/ static/

ENV DATA_DIR=/app/data
ENV PORT=5000

EXPOSE 5000

CMD ["python", "app.py"]
