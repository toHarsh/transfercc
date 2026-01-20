#!/bin/bash
# Production startup script for Transfercc

set -e

echo "🚀 Starting Transfercc in production mode..."

# Check if we're in the right directory
if [ ! -f "app.py" ]; then
    echo "❌ Error: app.py not found. Please run this script from the transfercc directory."
    exit 1
fi

# Check required environment variables
if [ -z "$FIREBASE_CONFIG" ] && [ ! -f "firebase-service-account.json" ]; then
    echo "⚠️  Warning: FIREBASE_CONFIG not set and firebase-service-account.json not found"
    echo "   Authentication will be disabled"
fi

if [ -z "$FIREBASE_WEB_CONFIG" ]; then
    echo "⚠️  Warning: FIREBASE_WEB_CONFIG not set"
    echo "   Google Sign-In will not work"
fi

if [ -z "$SECRET_KEY" ]; then
    echo "⚠️  Warning: SECRET_KEY not set"
    echo "   Generating a new secret key for this session..."
    export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    echo "   Note: Set SECRET_KEY environment variable for persistent sessions"
fi

# Set production environment
export FLASK_ENV=production

# Get port from environment or use default
PORT=${PORT:-5001}

# Check if gunicorn is installed
if ! command -v gunicorn &> /dev/null; then
    echo "❌ Error: gunicorn not found. Install it with: pip install gunicorn"
    exit 1
fi

# Start with gunicorn
echo "✅ Starting Gunicorn on port $PORT..."
echo "   Workers: $(python3 -c 'import multiprocessing; print(multiprocessing.cpu_count() * 2 + 1)')"
echo "   Access logs: stdout"
echo "   Error logs: stderr"
echo ""

if [ -f "gunicorn_config.py" ]; then
    gunicorn -c gunicorn_config.py app:app
else
    gunicorn -w 4 -b 0.0.0.0:$PORT --timeout 120 --access-logfile - --error-logfile - app:app
fi
