FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential: insightface compiles a small Cython extension.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt constraints.txt ./
RUN pip install -c constraints.txt -r requirements.txt \
    && pip install -c constraints.txt --no-build-isolation --no-binary insightface "insightface==0.7.3" \
    && python -c "import numpy, insightface.app; print('numpy', numpy.__version__, '- insightface import ok')"
COPY . .

EXPOSE 8000

# --reload is on because ./api is bind-mounted in docker-compose.yml.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
