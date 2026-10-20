FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Set by CI (date + commit); shown by /version and the startup log.
# Declared after the COPY so a new version doesn't bust the pip layer cache.
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

# Run the bot
CMD ["python", "-m", "app.main"]
