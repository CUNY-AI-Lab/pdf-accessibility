# Use an official Python runtime as a parent image
FROM public.ecr.aws/docker/library/python:3.12-slim

# Set the working directory in the container to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Create required directories
RUN mkdir -p /output/images /tmp/pages

# Install Python dependencies and clean up
RUN pip install --no-cache-dir -r requirements.txt && \
    pip uninstall -y pip setuptools 2>/dev/null || true && \
    rm -rf /root/.cache /tmp/*

# Set the command to run the Python script when the container launches
CMD ["python", "./ai_tagger_processor.py"]
