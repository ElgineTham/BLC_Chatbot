FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN pip install poetry

# Dependency layer: rebuilt only when pyproject.toml or poetry.lock change.
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --without eval

COPY backend ./backend
COPY frontend ./frontend

EXPOSE 8000

CMD ["python", "backend/scripts/web.py", "--host", "0.0.0.0", "--port", "8000"]
