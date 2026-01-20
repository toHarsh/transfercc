# GCS Upload Pipeline Migration

This document describes the refactored upload pipeline that uses Google Cloud Storage (GCS) signed URLs to bypass HTTP request size limits.

## Architecture Overview

### Old Flow (Deprecated for large files)
1. Client POSTs file directly to `/upload` endpoint
2. Flask receives file in HTTP request body
3. File saved to local filesystem
4. Background thread processes file
5. **Problem**: HTTP 413 (Payload Too Large) for files > 32MB

### New Flow (GCS-based)
1. Client calls `POST /upload-url` with file metadata
2. Backend creates Firestore job and generates GCS signed URL
3. Client uploads file directly to GCS using signed URL (bypasses HTTP limits)
4. GCS Storage trigger function processes file when upload completes
5. Client polls `/upload-status/<job_id>` to check progress
6. **Benefit**: No HTTP size limits, files up to 500MB+ supported

## New Components

### 1. `/upload-url` Endpoint
- **Route**: `POST /upload-url`
- **Auth**: Required (login_required)
- **Request Body**:
  ```json
  {
    "file_name": "export.zip",
    "content_type": "application/zip",
    "file_size": 12345678
  }
  ```
- **Response**:
  ```json
  {
    "uploadUrl": "https://storage.googleapis.com/...",
    "jobId": "abc123...",
    "objectPath": "uploads/abc123/export.zip"
  }
  ```
- **Functionality**:
  - Validates file metadata
  - Creates job document in Firestore
  - Generates GCS signed URL (V4, PUT, 1 hour expiry)
  - Returns URL and job ID to client

### 2. Storage Trigger Function
- **Location**: `functions/main.py` → `process_uploaded_file()`
- **Trigger**: GCS `object.finalize` event on uploads bucket
- **Functionality**:
  - Extracts `job_id` from object path: `uploads/{job_id}/{filename}`
  - Updates job status to "processing"
  - Downloads file from GCS
  - Calls `services.process_export.process_export()` to process file
  - Updates job status to "completed" or "failed"
  - Stores processed data in session-scoped file

### 3. Updated `/upload-status` Endpoint
- **Route**: `GET /upload-status/<job_id>`
- **Auth**: Required
- **Functionality**:
  - Reads job from Firestore (new jobs) or in-memory dict (old jobs for backwards compatibility)
  - Verifies session ownership
  - Returns job status, progress, and results
  - Updates session when job completes

### 4. Processing Service Module
- **Location**: `functions/services/process_export.py`
- **Function**: `process_export(job_id, file_handle_or_bytes, metadata={})`
- **Functionality**:
  - Extracts data from ZIP or JSON files
  - Normalizes data structure
  - Parses conversations using ChatGPTParser
  - Returns statistics and processed data
  - Reusable by both direct upload and GCS trigger

### 5. Frontend JavaScript Updates
- **Function**: `uploadFileWithBackgroundProcessing()`
- **New Flow**:
  1. Call `/upload-url` to get signed URL and job ID
  2. Upload file directly to GCS using `fetch(uploadUrl, { method: 'PUT', body: file })`
  3. Start polling `/upload-status/<jobId>`
  4. Show progress and handle completion/errors

## Configuration

### Environment Variables

Add these to your Firebase Functions environment:

```bash
# GCS bucket name (default: transfercc-589f7-uploads)
UPLOAD_BUCKET=transfercc-589f7-uploads

# Maximum upload size in MB (default: 500)
MAX_UPLOAD_SIZE_MB=500
```

### GCS Bucket Setup

1. Create a GCS bucket (or use existing):
   ```bash
   gsutil mb gs://transfercc-589f7-uploads
   ```

2. Configure CORS (if needed for direct browser uploads):
   ```json
   [
     {
       "origin": ["*"],
       "method": ["PUT", "GET", "HEAD"],
       "responseHeader": ["Content-Type"],
       "maxAgeSeconds": 3600
     }
   ]
   ```
   ```bash
   gsutil cors set cors.json gs://transfercc-589f7-uploads
   ```

3. Set bucket permissions (Firebase Functions service account needs write access):
   - The default Firebase Functions service account should already have access
   - If not, grant `roles/storage.objectAdmin` to the service account

### Firestore Setup

The code automatically creates a `jobs` collection. No manual setup needed, but ensure:
- Firestore is enabled in your Firebase project
- The Firebase Functions service account has Firestore read/write permissions

## Deployment

1. **Install dependencies**:
   ```bash
   cd functions
   pip install -r requirements.txt
   ```

2. **Set environment variables** in Firebase Console:
   - Go to Functions → Configuration → Environment variables
   - Add `UPLOAD_BUCKET` and `MAX_UPLOAD_SIZE_MB`

3. **Deploy functions**:
   ```bash
   firebase deploy --only functions
   ```

   This will deploy:
   - `app` (HTTP function - Flask app)
   - `process_uploaded_file` (Storage trigger)

## Backwards Compatibility

- The old `/upload` endpoint is still available but restricted to files < 10MB
- Files > 10MB will receive an error message directing users to use the new flow
- The `/upload-status` endpoint works with both old (in-memory) and new (Firestore) jobs
- Old direct uploads continue to work for small files

## Testing

### Test the new flow:

1. **Request upload URL**:
   ```bash
   curl -X POST https://your-function-url/upload-url \
     -H "Content-Type: application/json" \
     -H "Cookie: session=..." \
     -d '{
       "file_name": "test.zip",
       "content_type": "application/zip",
       "file_size": 1000000
     }'
   ```

2. **Upload to GCS** (using returned `uploadUrl`):
   ```bash
   curl -X PUT "<uploadUrl>" \
     -H "Content-Type: application/zip" \
     --data-binary @test.zip
   ```

3. **Check status**:
   ```bash
   curl https://your-function-url/upload-status/<jobId> \
     -H "Cookie: session=..."
   ```

## Error Handling

- **Upload URL generation fails**: Returns 500 with error message
- **GCS upload fails**: Client shows error, job remains in "pending" state
- **Processing fails**: Job status set to "failed" with error message
- **Job expires**: Status returns 410 Gone after 2 hours

## Monitoring

- Check Firebase Functions logs for:
  - Job creation (`/upload-url` calls)
  - Storage trigger executions
  - Processing errors
- Check Firestore `jobs` collection for job status
- Check GCS bucket for uploaded files

## File Cleanup

- Processed files are stored in session-scoped locations (same as before)
- GCS uploaded files are NOT automatically deleted (can be enabled in trigger function)
- Expired jobs are cleaned up by existing cleanup functions

## Migration Notes

- All new uploads automatically use the GCS flow
- No changes needed to existing UI (JavaScript handles both flows)
- Old direct uploads still work for files < 10MB
- Large files (> 10MB) must use the new GCS flow
