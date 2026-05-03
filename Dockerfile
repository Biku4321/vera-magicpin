FROM python:3.11-slim

WORKDIR /app

# Install dependencies using pre-built wheels only
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --only-binary=:all: pydantic && \
    pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}