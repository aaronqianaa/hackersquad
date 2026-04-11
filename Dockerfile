FROM python:3.11-slim

WORKDIR /workspace
COPY pyproject.toml /workspace/pyproject.toml
RUN pip install --no-cache-dir -e .
COPY . /workspace

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
