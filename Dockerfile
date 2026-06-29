FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py store.py constants.py scope.py paths.py policy.py user_handout.py ./
COPY models/ models/
COPY repositories/ repositories/
COPY services/ services/
COPY json_io/ json_io/
COPY persistence/ persistence/
COPY templates/ templates/
COPY static/ static/

ENV DATA_DIR=/app/data
ENV PORT=80

EXPOSE 80

CMD ["python", "app.py"]
