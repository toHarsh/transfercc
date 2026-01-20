#!/bin/bash

# Transfercc - ChatGPT to Claude Migration Tool
# Quick start script for local development

set -e

echo "🚀 Transfercc - ChatGPT to Claude Migration"
echo "============================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not found."
    echo "   Install it from https://python.org"
    exit 1
fi

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check/install dependencies
if ! python3 -c "import flask" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip3 install -r requirements.txt
fi

# Load .env if exists
if [ -f .env ]; then
    echo "📄 Loading environment from .env"
    export $(cat .env | grep -v '^#' | xargs)
fi

# Set Firebase config if service account exists
if [ -f "firebase-service-account.json" ]; then
    export FIREBASE_CONFIG="$SCRIPT_DIR/firebase-service-account.json"
fi

# Set Firebase Web Config (if not already set)
if [ -z "$FIREBASE_WEB_CONFIG" ]; then
    export FIREBASE_WEB_CONFIG='{"apiKey":"AIzaSyDp103Sc_bdR9LRpcJRRDOGMtPWUStmOL0","authDomain":"transfercc-589f7.firebaseapp.com","projectId":"transfercc-589f7","storageBucket":"transfercc-589f7.firebasestorage.app","messagingSenderId":"853998449283","appId":"1:853998449283:web:7ec967db0d68ab421221b6","measurementId":"G-0D5D6S730X"}'
fi

# Check for export path argument (optional - can upload via web)
if [ -n "$1" ]; then
    EXPORT_PATH="$1"
    
    # Verify conversations.json exists
    if [ ! -f "$EXPORT_PATH/conversations.json" ]; then
        echo "❌ conversations.json not found in: $EXPORT_PATH"
        echo "   Make sure you've extracted the ChatGPT export ZIP file"
        exit 1
    fi
    
    echo "📂 Loading export from: $EXPORT_PATH"
    echo ""
    python3 app.py "$EXPORT_PATH"
else
    echo "🌐 Starting web server..."
    echo "   Open http://localhost:${PORT:-5001} in your browser"
    echo "   Upload your ChatGPT export ZIP file to get started!"
    echo ""
    echo "Press Ctrl+C to stop"
    echo ""
    python3 app.py
fi
