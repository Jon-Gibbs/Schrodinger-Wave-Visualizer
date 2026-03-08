# syntax=docker/dockerfile:1

FROM python:3.11-slim AS builder

WORKDIR /build

# Build dependencies required only for compiling Fortran extension.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    gfortran \
    gcc \
    g++ \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /build/requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "setuptools<70" wheel "numpy==1.26.4" \
    && if [ -s /build/requirements.txt ]; then pip install --no-cache-dir -r /build/requirements.txt; fi

COPY app/fortran/schrodinger.f90 /app/fortran/schrodinger.f90

# Build schrodinger module with f2py.
RUN python -m numpy.f2py -c /app/fortran/schrodinger.f90 -m schrodinger


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Runtime dependency for Fortran shared object.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgfortran5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "numpy==1.26.4" \
    && if [ -s /app/requirements.txt ]; then pip install --no-cache-dir -r /app/requirements.txt; fi

COPY parallel_worker.py /app/parallel_worker.py
COPY --from=builder /build/schrodinger*.so /app/

CMD ["python", "parallel_worker.py"]
