FROM python:3.11-slim

# Create non-root user
RUN useradd -m -u 1000 benchuser && mkdir -p /benchmark && chown -R benchuser:benchuser /benchmark

WORKDIR /benchmark

# Copy only necessary files
COPY --chown=benchuser:benchuser requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=benchuser:benchuser run_benchmark.py generate_report.py synthetic_adversarial_dataset.json ./

# Switch to non-root user
USER benchuser

# Default command
CMD ["python", "run_benchmark.py"]
