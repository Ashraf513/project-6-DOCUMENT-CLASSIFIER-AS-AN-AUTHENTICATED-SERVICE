FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/docclassifier-week6

COPY pyproject.toml requirements.txt ./
COPY app ./app
COPY casbin ./casbin

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -e . \
    && python -m pip install -r requirements.txt

COPY alembic ./alembic
COPY alembic.ini ./
COPY streamlit_dashboard.py ./
COPY .streamlit ./.streamlit
COPY README.md RUNBOOK.md SECURITY.md ARCH.md DECISIONS.md COLLABORATION.md LICENSES.md ./

EXPOSE 8000 8501

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
