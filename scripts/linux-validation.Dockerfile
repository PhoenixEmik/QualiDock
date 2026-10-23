# Test-only environment. QualiDock itself remains independent of containers.
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless curl unzip \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1001 qualidock
RUN curl -fsSL https://github.com/s-andrews/FastQC/releases/download/v0.13.0/fastqc_v0.13.0.zip -o /tmp/fastqc.zip \
    && unzip -q /tmp/fastqc.zip -d /opt && chmod +x /opt/FastQC/fastqc && rm /tmp/fastqc.zip
ENV PATH="/opt/FastQC:${PATH}" HOME=/home/qualidock OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
WORKDIR /workspace
COPY . .
RUN bash scripts/setup-alignment-ci.sh
ENV PATH="/tmp/qualidock-alignment-tools/samtools-1.24:${PATH}"
RUN python -m pip install --no-cache-dir -e '.[test]' multiqc==1.35
USER 1001:1001
CMD ["python", "scripts/validate-linux-execution.py", "--output", "/evidence"]
