# Use an official Python runtime as a parent image
FROM python:3.13-slim

# Set the working directory in the container
WORKDIR /app

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Install system certificates and link certifi's bundle
RUN apt-get update && apt-get install -y ca-certificates && \
    CERTIFI_PATH=$(python -c "import certifi; print(certifi.where())") && \
    ln -s $CERTIFI_PATH /usr/local/share/ca-certificates/certifi.crt && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Copy the rest of the application code to the working directory
COPY . .

# Set environment variables for memory optimization
ENV PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONGC=1 \
    PYTHONMALLOC=malloc

# Command to run the application with memory optimizations
CMD ["sh", "-c", "gunicorn -w 1 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:${PORT:-8000} --timeout 120 --worker-tmp-dir /dev/shm"]