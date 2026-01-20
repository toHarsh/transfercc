#!/bin/bash
# Grant Storage permissions to the Cloud Run service account

PROJECT_ID="transfercc-589f7"
REGION="us-central1"
SERVICE_NAME="transfercc-api"

echo "Finding service account for Cloud Run service..."

# Try to get the service account from the Cloud Run service
SERVICE_ACCOUNT=$(gcloud run services describe ${SERVICE_NAME} \
  --region=${REGION} \
  --project=${PROJECT_ID} \
  --format="value(spec.template.spec.serviceAccountName)" 2>/dev/null)

# If no custom service account, use default compute service account
if [ -z "$SERVICE_ACCOUNT" ]; then
    echo "No custom service account found, using default compute service account..."
    PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format="value(projectNumber)")
    SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
    echo "Using default: ${SERVICE_ACCOUNT}"
else
    echo "Found custom service account: ${SERVICE_ACCOUNT}"
fi

echo ""
echo "Granting Storage Object Admin role to: ${SERVICE_ACCOUNT}"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/storage.objectAdmin"

echo ""
echo "✅ Permissions granted successfully!"
echo ""
echo "The service account ${SERVICE_ACCOUNT} now has Storage Object Admin permissions."
