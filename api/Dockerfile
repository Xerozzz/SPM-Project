# Single-stage image: this is a development stack, and a build we can all read beats
# a multi-stage one we cannot. Compose bind-mounts ./api over /app and runs uvicorn
# with --reload, so edits on the host apply without a rebuild.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first: this layer is cached until the requirements files change.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
