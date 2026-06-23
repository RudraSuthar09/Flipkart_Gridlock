# Use official lightweight Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies (optional, but good for LightGBM/pandas if needed)
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY prediction_api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the data directory (needed for parquet files)
COPY data /app/data

# Copy the backend code
COPY prediction_api /app/prediction_api

# Set working directory to prediction_api so relative imports work correctly
WORKDIR /app/prediction_api

# Expose port 8080 (default for Google Cloud Run)
EXPOSE 8080

# Start the FastAPI server using Uvicorn
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
