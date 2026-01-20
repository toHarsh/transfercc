#!/bin/bash
# Deploy Firebase Functions with environment variables

# Read the Firebase web config and convert to single-line JSON
FIREBASE_WEB_CONFIG=$(cat firebase-web-config.json | jq -c . | tr -d '\n')

echo "Deploying Firebase Functions with FIREBASE_WEB_CONFIG..."

# Deploy using Firebase CLI (it will use gcloud under the hood for Gen 2)
firebase deploy --only functions

# After deployment, update the Cloud Run service with environment variables
echo "Setting environment variables on Cloud Run service..."

# Get the function name and region from the deployment
FUNCTION_NAME="transfercc-api"
REGION="us-central1"  # Change if your function is in a different region
PROJECT_ID="transfercc-589f7"

# Update the Cloud Run service with environment variables
gcloud run services update ${FUNCTION_NAME} \
  --region=${REGION} \
  --project=${PROJECT_ID} \
  --update-env-vars FIREBASE_WEB_CONFIG="${FIREBASE_WEB_CONFIG}"

echo "✅ Environment variables set successfully!"
echo ""
echo "Your function URL: https://${FUNCTION_NAME}-ondpj2jkzq-${REGION}.a.run.app"
