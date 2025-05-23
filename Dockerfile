# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    tar \
    gzip \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m -u 1000 appuser

# Create gcloud config directory and set permissions
RUN mkdir -p /home/appuser/.config/gcloud/configurations && \
    chown -R appuser:appuser /home/appuser/.config

# Install Google Cloud SDK with specific Python version
RUN curl -sSL https://sdk.cloud.google.com > /tmp/gcloud.sh && \
    bash /tmp/gcloud.sh --disable-prompts --install-dir=/usr/local/gcloud && \
    ln -s /usr/local/gcloud/google-cloud-sdk/bin/gsutil /usr/local/bin/gsutil && \
    ln -s /usr/local/gcloud/google-cloud-sdk/bin/gcloud /usr/local/bin/gcloud && \
    rm /tmp/gcloud.sh

# Set Python version for gsutil
ENV CLOUDSDK_PYTHON=/usr/local/bin/python3

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create necessary directories and set permissions
RUN mkdir -p data logs config && \
    chown -R appuser:appuser /app && \
    chmod -R 755 /app && \
    chmod 777 /app/data /app/logs /app/config

# Ensure config.yaml exists and is writable
RUN touch config/config.yaml && \
    chown appuser:appuser config/config.yaml && \
    chmod 666 config/config.yaml

# Make scripts executable
RUN chmod +x scripts/backup-data.sh scripts/startup-restore.sh

# Expose the port Streamlit runs on
EXPOSE 8080

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV HOME=/home/appuser

# Switch to non-root user
USER appuser

# Command to run the application
CMD ["/bin/bash", "-c", "scripts/startup-restore.sh && streamlit run app/Home.py --server.port=8080 --server.address=0.0.0.0"] 