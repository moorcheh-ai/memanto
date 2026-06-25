FROM python:3.11-slim

WORKDIR /benchmark

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy benchmark files
COPY . .

# Default command
CMD ["python", "run_benchmark.py"]
