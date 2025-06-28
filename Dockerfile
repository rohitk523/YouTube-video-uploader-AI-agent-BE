FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
        ffmpeg \
        libmagic1 \
        git \
        && apt-get clean \
        && rm -rf /var/lib/apt/lists/* \
        && apt-get autoremove -y

# Create non-root user early
RUN adduser --disabled-password --gecos '' --uid 1000 appuser

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt \
    && pip cache purge

# Create necessary directories with proper permissions
RUN mkdir -p uploads temp static logs \
    && chown -R appuser:appuser /app

# Copy application files
COPY --chown=appuser:appuser app/ ./app/

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"] 