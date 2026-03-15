#!/bin/bash
# הרץ פעם אחת: chmod +x start.sh
# לאחר מכן: ./start.sh

cd "$(dirname "$0")"

# Load .env if exists
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# Install dependencies if needed
pip install -r requirements.txt -q

# Create data directory
mkdir -p data

# Run with gunicorn (production)
gunicorn server:app \
  --bind 0.0.0.0:${PORT:-8080} \
  --workers 2 \
  --timeout 60 \
  --access-logfile - \
  --error-logfile -
