FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir flask pyyaml

# Copy application
COPY example_app.py .

# Create log directory
RUN mkdir -p /var/log/app

# Create config directory and default config
RUN mkdir -p /etc/app && \
    echo 'message: "Hello from Sidecar Demo"' > /etc/app/config.yaml && \
    echo 'version: "1.0"' >> /etc/app/config.yaml

EXPOSE 8080

CMD ["python", "example_app.py"]
