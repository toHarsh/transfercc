#!/bin/bash

# Setup environment variables for Firebase
# Run this script to set up your environment

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "🔥 Firebase Environment Setup"
echo "============================"
echo ""

# Set FIREBASE_CONFIG if file exists
if [ -f "firebase-service-account.json" ]; then
    export FIREBASE_CONFIG="$SCRIPT_DIR/firebase-service-account.json"
    echo "✅ FIREBASE_CONFIG set to: $FIREBASE_CONFIG"
else
    echo "⚠️  firebase-service-account.json not found"
    echo "   Please download it from Firebase Console"
fi

echo ""
echo "📋 Next: Get Firebase Web Config"
echo "1. Go to https://console.firebase.google.com/project/transfercc-589f7/settings/general"
echo "2. Scroll to 'Your apps' section"
echo "3. Click the Web icon </> (or add a web app if you haven't)"
echo "4. Copy the Firebase configuration object"
echo ""
echo "Then set FIREBASE_WEB_CONFIG:"
echo "export FIREBASE_WEB_CONFIG='{\"apiKey\":\"...\",\"authDomain\":\"transfercc-589f7.firebaseapp.com\",\"projectId\":\"transfercc-589f7\",\"storageBucket\":\"transfercc-589f7.appspot.com\",\"messagingSenderId\":\"...\",\"appId\":\"...\"}'"
echo ""
echo "Or add both to your ~/.zshrc:"
echo "export FIREBASE_CONFIG=\"$SCRIPT_DIR/firebase-service-account.json\""
echo "export FIREBASE_WEB_CONFIG='{...}'"
echo ""
