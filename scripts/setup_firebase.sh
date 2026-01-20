#!/bin/bash

# Firebase Setup Script for Transfercc
# This script helps you configure Firebase authentication

echo "🔥 Firebase Setup for Transfercc"
echo "================================"
echo ""

# Check if firebase-admin is installed
if ! python3 -c "import firebase_admin" 2>/dev/null; then
    echo "❌ firebase-admin not installed"
    echo "   Installing..."
    pip3 install firebase-admin==6.2.0
fi

echo "✅ firebase-admin is installed"
echo ""

# Check for existing config
if [ -f "firebase-service-account.json" ]; then
    echo "✅ Found firebase-service-account.json"
else
    echo "⚠️  firebase-service-account.json not found"
    echo ""
    echo "📋 Next steps:"
    echo "1. Go to https://console.firebase.google.com/"
    echo "2. Create a project (or select existing)"
    echo "3. Enable Authentication → Google Sign-In"
    echo "4. Go to Project Settings → Service accounts"
    echo "5. Click 'Generate new private key'"
    echo "6. Save the downloaded JSON file as: firebase-service-account.json"
    echo "   in this directory: $(pwd)"
    echo ""
fi

echo ""
echo "📝 To set environment variables, run:"
echo ""
echo "export FIREBASE_CONFIG=\"$(pwd)/firebase-service-account.json\""
echo "export FIREBASE_WEB_CONFIG='{\"apiKey\":\"YOUR_API_KEY\",\"authDomain\":\"YOUR_PROJECT.firebaseapp.com\",\"projectId\":\"YOUR_PROJECT_ID\",\"storageBucket\":\"YOUR_PROJECT.appspot.com\",\"messagingSenderId\":\"YOUR_SENDER_ID\",\"appId\":\"YOUR_APP_ID\"}'"
echo ""
echo "Or add them to your shell profile (~/.zshrc or ~/.bashrc)"
echo ""
