# Set the base image with pinned version for security
FROM continuumio/miniconda3:23.9.0 AS builder

# Set security and optimization environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/home/hummingbot

# Install system dependencies with pinned versions
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        sudo=1.9.* \
        libusb-1.0-0=2:1.0.* \
        gcc=4:12.* \
        g++=4:12.* \
        python3-dev=3.11.* \
        curl=7.* \
        ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash hummingbot && \
    echo "hummingbot ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

WORKDIR /home/hummingbot

# Copy dependency files first for better layer caching
COPY --chown=hummingbot:hummingbot setup/environment.yml /tmp/environment.yml
COPY --chown=hummingbot:hummingbot setup/pip_packages.txt /tmp/pip_packages.txt

# Switch to non-root user
USER hummingbot

# Create conda environment with pinned dependencies
RUN conda env create -f /tmp/environment.yml && \
    conda clean -afy && \
    rm /tmp/environment.yml

# Activate hummingbot env when entering the container
SHELL [ "/bin/bash", "-lc" ]
RUN echo "conda activate hummingbot" >> ~/.bashrc

# Install Python packages
RUN conda activate hummingbot && \
    python3 -m pip install --no-deps -r /tmp/pip_packages.txt && \
    rm /tmp/pip_packages.txt

# Copy application code
COPY --chown=hummingbot:hummingbot bin/ bin/
COPY --chown=hummingbot:hummingbot hummingbot/ hummingbot/
COPY --chown=hummingbot:hummingbot scripts/ scripts/
COPY --chown=hummingbot:hummingbot controllers/ controllers/
COPY --chown=hummingbot:hummingbot setup.py .
COPY --chown=hummingbot:hummingbot LICENSE .
COPY --chown=hummingbot:hummingbot README.md .

# Build Cython extensions
RUN conda activate hummingbot && \
    python3 setup.py build_ext --inplace -j 8 && \
    rm -rf build/ && \
    find . -type f -name "*.cpp" -delete

# Runtime stage - multi-stage build for smaller final image
FROM continuumio/miniconda3:23.9.0 AS runtime

# Metadata labels
LABEL maintainer="Fede Cardoso @dardonacci <federico@hummingbot.org>" \
      org.opencontainers.image.title="Hummingbot" \
      org.opencontainers.image.description="Hummingbot trading bot" \
      org.opencontainers.image.url="https://hummingbot.org/" \
      org.opencontainers.image.source="https://github.com/hummingbot/hummingbot" \
      org.opencontainers.image.vendor="Hummingbot Foundation"

# Build arguments
ARG BRANCH=""
ARG COMMIT=""
ARG BUILD_DATE=""
LABEL branch=${BRANCH} \
      commit=${COMMIT} \
      date=${BUILD_DATE}

# Set environment variables
ENV COMMIT_SHA=${COMMIT} \
    COMMIT_BRANCH=${BRANCH} \
    BUILD_DATE=${BUILD_DATE} \
    INSTALLATION_TYPE=docker \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/home/hummingbot \
    PATH="/opt/conda/envs/hummingbot/bin:$PATH"

# Install minimal runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        sudo=1.9.* \
        libusb-1.0-0=2:1.0.* \
        curl=7.* \
        ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash --uid 1000 hummingbot && \
    echo "hummingbot ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Create necessary directories with proper permissions
RUN mkdir -p /home/hummingbot/{conf,logs,data,certs,scripts,controllers} \
             /home/hummingbot/conf/{connectors,strategies,controllers,scripts} && \
    chown -R hummingbot:hummingbot /home/hummingbot

# Copy conda environment and application from builder
COPY --from=builder --chown=hummingbot:hummingbot /opt/conda/ /opt/conda/
COPY --from=builder --chown=hummingbot:hummingbot /home/hummingbot/ /home/hummingbot/

# Switch to non-root user
USER hummingbot
WORKDIR /home/hummingbot

# Set up shell environment
SHELL [ "/bin/bash", "-lc" ]
RUN echo "conda activate hummingbot" >> ~/.bashrc

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Expose default port (if applicable)
EXPOSE 8080

# Set resource limits and security options
STOPSIGNAL SIGTERM

# Set the default command with proper signal handling
CMD ["bash", "-c", "conda activate hummingbot && mkdir -p ./logs && exec ./bin/hummingbot_quickstart.py 2>> ./logs/errors.log"]
