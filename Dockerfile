FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source
COPY . .

# Create output directories (articles/, state/, logs/ may not exist in repo)
RUN mkdir -p articles state logs

# Run the sync pipeline; exits with code 0 on success, 1 on error
CMD ["python", "main.py"]
