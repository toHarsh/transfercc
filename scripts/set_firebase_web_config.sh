#!/bin/bash
# Set FIREBASE_WEB_CONFIG environment variable on Cloud Run service

FUNCTION_NAME="transfercc-api"
REGION="us-central1"  # Based on your URL: transfercc-api-ondpj2jkzq-uc.a.run.app (uc = us-central1)
PROJECT_ID="transfercc-589f7"

# Read the Firebase web config and convert to single-line JSON
FIREBASE_WEB_CONFIG='{"apiKey":"AIzaSyDp103Sc_bdR9LRpcJRRDOGMtPWUStmOL0","authDomain":"transfercc-589f7.firebaseapp.com","projectId":"transfercc-589f7","storageBucket":"transfercc-589f7.firebasestorage.app","messagingSenderId":"853998449283","appId":"1:853998449283:web:7ec967db0d68ab421221b6","measurementId":"G-0D5D6S730X"}'

echo "Setting FIREBASE_WEB_CONFIG on Cloud Run service: ${FUNCTION_NAME}..."

gcloud run services update ${FUNCTION_NAME} \
  --region=${REGION} \
  --project=${PROJECT_ID} \
  --update-env-vars FIREBASE_WEB_CONFIG="${FIREBASE_WEB_CONFIG}"

echo ""
echo "✅ Environment variable set successfully!"
echo "The function will automatically restart with the new environment variable."
