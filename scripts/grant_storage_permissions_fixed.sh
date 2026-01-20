#!/bin/bash
# Grant Storage permissions to the Cloud Run service account

PROJECT_ID="transfercc-589f7"
PROJECT_NUMBER="853998449283"  # From your firebase-web-config.json messagingSenderId

echo "Granting Storage Object Admin role to default compute service account..."

# Grant to default compute service account
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

echo ""
echo "Also granting to App Engine service account (if used)..."

# Grant to App Engine service account
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${PROJECT_ID}@appspot.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

echo ""
echo "✅ Permissions granted successfully!"
