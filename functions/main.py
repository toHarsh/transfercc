"""
Firebase Cloud Functions entry point for Flask app (Transfercc)
"""

import os
import sys
import logging
from typing import Any

from firebase_functions import https_fn, options, storage_fn
from google.cloud import storage as gcs_storage
from google.cloud import firestore

# Make sure the functions directory (where main.py & app.py live) is on sys.path
FUNCTIONS_DIR = os.path.dirname(os.path.abspath(__file__))
if FUNCTIONS_DIR not in sys.path:
    sys.path.insert(0, FUNCTIONS_DIR)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import the Flask app from app.py (must define `app = Flask(__name__)`)
from app import app as flask_app  # type: ignore
from app import STORAGE_DIR, EPHEMERAL_TTL

# GCS bucket configuration
UPLOAD_BUCKET_NAME = os.environ.get("UPLOAD_BUCKET", "transfercc-589f7-uploads")
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "500"))

logger.info("GCS Upload Configuration:")
logger.info("  UPLOAD_BUCKET: %s", UPLOAD_BUCKET_NAME)
logger.info("  MAX_UPLOAD_SIZE_MB: %s", MAX_UPLOAD_SIZE_MB)


# --- HTTP ENTRYPOINT: WRAP FLASK APP --------------------------------------


@https_fn.on_request(
    cors=options.CorsOptions(
        cors_origins=["*"],
        cors_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    )
)
def transfercc_api(req: https_fn.Request) -> https_fn.Response:
    """
    HTTP Cloud Function entry point.

    This wraps the existing Flask app and lets it handle all routes.
    """
    try:
        logger.info(
            "Incoming request: %s %s",
            getattr(req, "method", "GET"),
            getattr(req, "path", "/"),
        )

        # Prefer the WSGI environ (best integration with Flask)
        environ: Any = getattr(req, "environ", None)

        if environ is not None:
            # Normal path: use environ directly
            with flask_app.request_context(environ):
                flask_resp = flask_app.full_dispatch_request()
        else:
            # Fallback: build a test_request_context
            path = getattr(req, "path", "/") or "/"
            method = getattr(req, "method", "GET")

            query_string = getattr(req, "query_string", b"")
            if isinstance(query_string, str):
                query_string = query_string.encode("utf-8")

            data = getattr(req, "data", b"")
            if isinstance(data, str):
                data = data.encode("utf-8")

            with flask_app.test_request_context(
                path=path,
                method=method,
                query_string=query_string,
                data=data,
                headers=dict(getattr(req, "headers", {})),
            ):
                flask_resp = flask_app.full_dispatch_request()

        body = flask_resp.get_data()
        headers = dict(flask_resp.headers)
        status = flask_resp.status_code

        logger.info("Responding with %s (%d bytes)", status, len(body))

        return https_fn.Response(
            body,
            status=status,
            headers=headers,
        )

    except Exception as e:
        logger.exception("Error handling request in transfercc_api: %s", e)
        return https_fn.Response(
            f"Internal server error: {e}",
            status=500,
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )


# --- STORAGE TRIGGER: PROCESS UPLOADED FILES ------------------------------


@storage_fn.on_object_finalized(bucket=UPLOAD_BUCKET_NAME)
def process_uploaded_file(event: storage_fn.CloudEvent) -> None:
    """
    Background worker that processes files uploaded to GCS.

    Expects object path: uploads/{job_id}/{filename}
    """
    import time
    import tempfile
    import hashlib
    import json

    from app import STORAGE_DIR, EPHEMERAL_TTL
    from services.process_export import process_export

    logger.info("Storage trigger fired: %s", event.data)

    try:
        bucket_name = event.data.bucket
        object_name = event.data.name
        logger.info(f"EVENT DATA: bucket={bucket_name}, name={object_name}")


        if not object_name.startswith("uploads/"):
            logger.warning("Ignoring file outside uploads/ prefix: %s", object_name)
            return

        path_parts = object_name.split("/", 2)
        if len(path_parts) < 3:
            logger.warning("Invalid object path format: %s", object_name)
            return

        job_id = path_parts[1]
        filename = path_parts[2]

        logger.info("Extracted job_id=%s, filename=%s", job_id, filename)

        db = firestore.Client()
        storage_client = gcs_storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(object_name)

        job_ref = db.collection("jobs").document(job_id)
        job_doc = job_ref.get()

        if not job_doc.exists:
            logger.warning("Job %s not found in Firestore, ignoring file", job_id)
            return

        job_data = job_doc.to_dict() or {}

        # Update job -> processing
        job_ref.update(
            {
                "status": "processing",
                "progress": 10,
                "message": "Downloading file from storage...",
                "updated_at": firestore.SERVER_TIMESTAMP,
            }
        )

        temp_file = None
        try:
            # Download to temp file
            fd, temp_file = tempfile.mkstemp(suffix=os.path.splitext(filename)[1])
            os.close(fd)

            logger.info(
                "Downloading gs://%s/%s to %s", bucket_name, object_name, temp_file
            )
            blob.download_to_filename(temp_file)

            file_size = os.path.getsize(temp_file)
            logger.info("Downloaded %d bytes", file_size)

            job_ref.update(
                {
                    "progress": 30,
                    "message": "Processing file...",
                    "updated_at": firestore.SERVER_TIMESTAMP,
                }
            )

            metadata = {
                "filename": filename,
                "content_type": job_data.get(
                    "content_type", "application/octet-stream"
                ),
                "file_size": file_size,
            }

            result = process_export(job_id, temp_file, metadata=metadata)

            if not result.get("success"):
                error_msg = result.get("error", "Unknown error")
                logger.error("Job %s processing failed: %s", job_id, error_msg)
                job_ref.update(
                    {
                        "status": "failed",
                        "error_message": error_msg,
                        "updated_at": firestore.SERVER_TIMESTAMP,
                    }
                )
                return

            stats = result.get("stats", {})
            conversations_data = result.get("conversations_data", [])

            session_id = job_data.get("session_id", "unknown")
            file_id = hashlib.md5(
                f"{session_id}_{time.time()}".encode()
            ).hexdigest()

            os.makedirs(STORAGE_DIR, exist_ok=True)
            storage_file = os.path.join(
                STORAGE_DIR, f"{session_id}_conv_{file_id}.json"
            )

            with open(storage_file, "w", encoding="utf-8") as f:
                json.dump(conversations_data, f)

            expires_at = time.time() + EPHEMERAL_TTL

            job_ref.update(
                {
                    "status": "completed",
                    "progress": 100,
                    "message": f"Successfully loaded {stats.get('total_conversations', 0)} conversations",
                    "storage_file": storage_file,
                    "stats": stats,
                    "expires_at": expires_at,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                }
            )

            logger.info(
                "Job %s completed: %d conversations",
                job_id,
                stats.get("total_conversations", 0),
            )

        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logger.debug("Cleaned up temp file: %s", temp_file)
                except Exception as cleanup_err:
                    logger.warning(
                        "Failed to clean up temp file %s: %s", temp_file, cleanup_err
                    )

    except Exception as e:
        logger.exception("Error in storage trigger: %s", e)
        try:
            if "job_id" in locals():
                db = firestore.Client()
                job_ref = db.collection("jobs").document(job_id)
                job_ref.update(
                    {
                        "status": "failed",
                        "error_message": str(e),
                        "updated_at": firestore.SERVER_TIMESTAMP,
                    }
                )
        except Exception as update_error:
            logger.error("Failed to update job status after error: %s", update_error)
