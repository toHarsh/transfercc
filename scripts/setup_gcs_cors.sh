#!/bin/bash
# Configure CORS on GCS bucket to allow browser uploads

BUCKET_NAME="transfercc-589f7-uploads"
PROJECT_ID="transfercc-589f7"

echo "Configuring CORS on GCS bucket: ${BUCKET_NAME}..."

# Use the CORS config file in the project (from config/ directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CORS_FILE="$PROJECT_DIR/config/gcs_cors.json"

if [ ! -f "$CORS_FILE" ]; then
    echo "Error: $CORS_FILE not found"
    exit 1
fi

echo "Using CORS config from: $CORS_FILE"

# Apply CORS configuration
gsutil cors set "$CORS_FILE" gs://${BUCKET_NAME}

echo ""
echo "✅ CORS configured on bucket ${BUCKET_NAME}"
echo ""
echo "This allows browsers to upload files directly to GCS."
