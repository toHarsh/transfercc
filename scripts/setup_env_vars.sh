#!/bin/bash
# Script to set Firebase Functions environment variables

echo "Setting Firebase Functions environment variables..."

# Set UPLOAD_BUCKET
firebase functions:config:set upload.bucket="transfercc-589f7-uploads" || {
    echo "Note: If using Firebase Functions Gen 2, use:"
    echo "  firebase functions:secrets:set UPLOAD_BUCKET"
    echo "Or set in Firebase Console → Functions → Configuration"
}

# Set MAX_UPLOAD_SIZE_MB
firebase functions:config:set upload.max_size_mb="500" || {
    echo "Note: If using Firebase Functions Gen 2, use:"
    echo "  firebase functions:secrets:set MAX_UPLOAD_SIZE_MB"
    echo "Or set in Firebase Console → Functions → Configuration"
}

echo ""
echo "For Firebase Functions Gen 2, set these in Firebase Console:"
echo "  - Go to Firebase Console → Functions → Configuration"
echo "  - Add environment variable: UPLOAD_BUCKET = transfercc-589f7-uploads"
echo "  - Add environment variable: MAX_UPLOAD_SIZE_MB = 500"
echo ""
echo "Or use gcloud CLI:"
echo "  gcloud functions deploy app --set-env-vars UPLOAD_BUCKET=transfercc-589f7-uploads,MAX_UPLOAD_SIZE_MB=500"
