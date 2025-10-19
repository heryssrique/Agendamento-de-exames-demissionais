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
# Copy pre-downloaded wheels into the build context so we can install from them
COPY wheels /wheels
# Ensure pip, setuptools and wheel are up-to-date and install production requirements
RUN set -eux; \
    # Pin pip and resolver-related packages to stable versions to avoid resolver/runtime regressions
    python -m pip install --upgrade pip==23.1.2 setuptools wheel packaging==23.1 resolvelib==0.9.0; \
    # Install requirements using only the local wheelhouse so pip resolves deps from the manylinux wheels
    python -m pip install --no-index --find-links=/wheels -r requirements-prod.txt

# Copy app
COPY . /app

# Expose port
EXPOSE 8000

# Run uvicorn
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
