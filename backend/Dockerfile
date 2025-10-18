# Backend Dockerfile
FROM python:3.11-bullseye

# Prevent Python from writing pyc files to disc and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       curl \
       ca-certificates \
       libssl-dev \
       libffi-dev \
       libpq-dev \
       libblas-dev \
       liblapack-dev \
       gfortran \
       pkg-config \
       libjpeg-dev \
       zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt ./requirements.txt
COPY requirements-prod.txt ./requirements-prod.txt
# Ensure pip, setuptools and wheel are up-to-date and install production requirements
RUN set -eux; \
    # Pin pip to a known stable 23.x release to avoid newer resolver/runtime regressions
    python -m pip install pip==23.1.2 setuptools wheel; \
    python -m pip install --no-cache-dir -r requirements-prod.txt

# Copy app
COPY . /app

# Expose port
EXPOSE 8000

# Run uvicorn
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
