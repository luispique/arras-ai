# Self-host image for the arras-ai CLI (core layer: local fastembed embeddings).
FROM python:3.12-slim

# Install the package (exposes the `arras` console script + runtime deps incl. fastembed).
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Route large caches (fastembed model via the HF hub + the KB index) into a mountable
# volume so they persist across runs. First run downloads the model (~large) once.
ENV HOME=/cache \
    HF_HOME=/cache/hf \
    ARRAS_KB_INDEX_DIR=/cache/kb_index
RUN mkdir -p /cache && chmod 0777 /cache

# Analyze files mounted at /data, e.g. `-v "$PWD:/data" ... analyze /data/contrato.pdf`.
WORKDIR /data
ENTRYPOINT ["arras"]
CMD ["--help"]
