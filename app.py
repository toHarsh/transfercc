"""
Transfercc - ChatGPT to Claude Migration Tool
Web interface for browsing, searching, and exporting ChatGPT conversations
"""

import warnings
# Suppress warnings BEFORE importing other modules
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=DeprecationWarning, module='parser')
warnings.filterwarnings('ignore', message='.*urllib3.*OpenSSL.*')
warnings.filterwarnings('ignore', message='.*NotOpenSSLWarning.*')

import os
import sys
import json
import logging
import traceback
from flask import Flask, render_template_string, request, jsonify, send_file, redirect, url_for, session
import tempfile
import zipfile
import shutil
from io import BytesIO
from functools import wraps
import secrets
import hashlib
import time
import glob
from datetime import datetime, timedelta
import threading
from collections import defaultdict
from google.cloud import storage as gcs_storage, firestore
import uuid

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    # Load .env file from the same directory as this script
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        logging.info(f"Loaded environment variables from {env_path}")
    else:
        # Also try loading from current working directory
        load_dotenv()
except ImportError:
    # python-dotenv not installed, skip .env loading
    pass

# Import parser with error handling for Vercel
try:
    from parser import ChatGPTParser, Conversation
except ImportError as e:
    import logging
    logging.error(f"Failed to import parser: {e}")
    # Create dummy classes for Vercel if parser can't be imported
    class ChatGPTParser:
        pass
    class Conversation:
        pass

# Environment variables are loaded from system environment

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Firebase Admin - ONLY for authentication token verification
# Completely isolated from file processing/parsing
FIREBASE_AUTH_ENABLED = False
try:
    import firebase_admin
    from firebase_admin import credentials, auth
    
    firebase_config = os.environ.get('FIREBASE_CONFIG')
    
    # Also check for firebase-service-account.json in project directory
    if not firebase_config:
        project_dir = os.path.dirname(os.path.abspath(__file__))
        default_config_path = os.path.join(project_dir, 'firebase-service-account.json')
        if os.path.exists(default_config_path):
            firebase_config = default_config_path
            logger.info(f"Found Firebase config at default location: {default_config_path}")
    
    if firebase_config:
        # Initialize Firebase Admin ONLY if config exists
        if os.path.exists(firebase_config):
            cred = credentials.Certificate(firebase_config)
            firebase_admin.initialize_app(cred)
        else:
            # Try parsing as JSON string
            # Environment variables often store JSON with literal newline characters in the private key
            # JSON requires newlines to be escaped as \n, not literal newlines
            try:
                # First, try direct JSON parse (works if properly formatted)
                cred_dict = json.loads(firebase_config)
            except json.JSONDecodeError as initial_error:
                # Environment variables may store the private key with literal newlines that break JSON parsing
                # JSON requires newlines to be escaped as \n
                # The issue is that literal newlines appear inside string values
                try:
                    # Simple and reliable approach: escape all literal control characters
                    # that aren't already part of escape sequences
                    # Process character by character to handle edge cases
                    fixed_config = []
                    i = 0
                    while i < len(firebase_config):
                        char = firebase_config[i]
                        # Check if we're in an escape sequence (backslash followed by something)
                        if char == '\\' and i + 1 < len(firebase_config):
                            # This is an escape sequence, preserve it
                            fixed_config.append(char)
                            i += 1
                            if i < len(firebase_config):
                                fixed_config.append(firebase_config[i])
                                i += 1
                        elif char == '\n':
                            # Literal newline - escape it
                            fixed_config.append('\\n')
                            i += 1
                        elif char == '\r':
                            # Literal carriage return - escape it
                            fixed_config.append('\\r')
                            i += 1
                        elif char == '\t':
                            # Literal tab - escape it
                            fixed_config.append('\\t')
                            i += 1
                        elif ord(char) < 32:  # Other control characters
                            # Escape other control characters
                            fixed_config.append(f'\\u{ord(char):04x}')
                            i += 1
                        else:
                            # Regular character, keep as is
                            fixed_config.append(char)
                            i += 1
                    
                    fixed_config = ''.join(fixed_config)
                    
                    # Try parsing the fixed config
                    cred_dict = json.loads(fixed_config)
                    logger.info("Successfully parsed FIREBASE_CONFIG after escaping control characters")
                except (json.JSONDecodeError, Exception) as e2:
                    # Fallback: simpler approach - escape all unescaped control characters
                    try:
                        # Protect already-escaped sequences
                        fixed_config = firebase_config.replace('\\\\', '__TEMP_BS__')
                        fixed_config = fixed_config.replace('\\n', '__TEMP_NL__')
                        fixed_config = fixed_config.replace('\\r', '__TEMP_CR__')
                        fixed_config = fixed_config.replace('\\t', '__TEMP_TAB__')
                        
                        # Escape all remaining literal control characters
                        fixed_config = fixed_config.replace('\r\n', '\\n')
                        fixed_config = fixed_config.replace('\r', '\\r')
                        fixed_config = fixed_config.replace('\n', '\\n')
                        fixed_config = fixed_config.replace('\t', '\\t')
                        
                        # Restore protected sequences
                        fixed_config = fixed_config.replace('__TEMP_NL__', '\\n')
                        fixed_config = fixed_config.replace('__TEMP_CR__', '\\r')
                        fixed_config = fixed_config.replace('__TEMP_TAB__', '\\t')
                        fixed_config = fixed_config.replace('__TEMP_BS__', '\\\\')
                        
                        cred_dict = json.loads(fixed_config)
                        logger.info("Successfully parsed FIREBASE_CONFIG using fallback method")
                    except json.JSONDecodeError as e3:
                        # Log detailed error information
                        logger.error(f"Failed to parse FIREBASE_CONFIG as JSON.")
                        logger.error(f"Initial error: {initial_error}")
                        logger.error(f"Regex fix error: {e2}")
                        logger.error(f"Fallback fix error: {e3}")
                        logger.error(f"Config length: {len(firebase_config)} chars")
                        # Show error location
                        error_pos = getattr(e3, 'pos', None) or getattr(e2, 'pos', None) or getattr(initial_error, 'pos', None)
                        if error_pos:
                            start = max(0, error_pos - 150)
                            end = min(len(firebase_config), error_pos + 150)
                            logger.error(f"Error around position {error_pos}: {repr(firebase_config[start:end])}")
                        else:
                            logger.error(f"Config preview (first 300 chars): {firebase_config[:300]}")
                        raise ValueError(f"Invalid FIREBASE_CONFIG JSON. Could not parse after multiple attempts. Last error: {e3}")
            
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        FIREBASE_AUTH_ENABLED = True
        logger.info("Firebase Auth initialized (authentication only)")
    else:
        logger.info("Firebase Auth not configured - authentication disabled")
except ImportError:
    logger.warning("firebase-admin not installed. Authentication will be disabled.")
except Exception as e:
    logger.warning(f"Firebase Auth setup failed: {e}. Authentication disabled.")

# User tracking - completely separate from Firebase
USAGE_LOG_FILE = os.path.join(tempfile.gettempdir(), 'transfercc_usage.log')

def log_user_usage(user_email, user_id, action='login'):
    """Log user activity - NO Firebase dependency"""
    try:
        timestamp = datetime.now().isoformat()
        log_entry = f"{timestamp} | {user_email} | {user_id} | {action}\n"
        with open(USAGE_LOG_FILE, 'a') as f:
            f.write(log_entry)
        logger.info(f"User activity: {user_email} - {action}")
    except Exception as e:
        logger.error(f"Error logging usage: {e}")

# Google Cloud Storage and Firestore configuration
# These are used for the new GCS-based upload pipeline
# Bucket name is set here in code - can be overridden via environment variable
UPLOAD_BUCKET = os.environ.get('UPLOAD_BUCKET', 'transfercc-589f7-uploads')
MAX_UPLOAD_SIZE_MB = int(os.environ.get('MAX_UPLOAD_SIZE_MB', '500'))

# Log configuration on startup
logger.info(f"GCS Upload Configuration:")
logger.info(f"  UPLOAD_BUCKET: {UPLOAD_BUCKET}")
logger.info(f"  MAX_UPLOAD_SIZE_MB: {MAX_UPLOAD_SIZE_MB}")

# Initialize Firestore client (for job tracking)
firestore_db = None
firestore = None
try:
    from firebase_admin import firestore
    if firebase_admin._apps:
        firestore_db = firestore.client()
        logger.info("Firestore client initialized")
    else:
        logger.warning("Firebase Admin not initialized - Firestore unavailable")
except ImportError:
    logger.warning("firebase-admin not available - Firestore features disabled")
except Exception as e:
    logger.warning(f"Failed to initialize Firestore: {e}")

# Initialize Google Cloud Storage client
storage_client = None
try:
    from google.cloud import storage
    storage_client = storage.Client()
    logger.info(f"Google Cloud Storage client initialized (bucket: {UPLOAD_BUCKET})")
except ImportError:
    logger.warning("google-cloud-storage not installed - GCS upload features disabled")
except Exception as e:
    # In development, this is expected - use INFO level instead of WARNING
    log_level = logger.info if os.environ.get('FLASK_ENV') != 'production' else logger.warning
    log_level(f"GCS client not initialized (expected in local dev): {e}")

# Determine environment
FLASK_ENV = os.environ.get('FLASK_ENV', 'development')
IS_PRODUCTION = FLASK_ENV == 'production'

app = Flask(__name__, static_folder='static', static_url_path='/static')

# Core configuration
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max upload
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Initialize session ID if not present
@app.before_request
def ensure_session_id():
    if '_id' not in session:
        session['_id'] = secrets.token_hex(16)
        session.permanent = True
        session.modified = True  # Ensure session is saved
        logger.debug(f"Created new session ID: {session['_id']}")
    # If user is already logged in, ensure session is marked as permanent
    elif session.get('user_id') and not session.permanent:
        session.permanent = True
        session.modified = True

# Ephemeral storage configuration (FreeConvert-style)
EPHEMERAL_TTL = 2 * 3600  # 2 hours (files auto-delete after this)
EPHEMERAL_CLEANUP_INTERVAL = 300  # Cleanup every 5 minutes

# Session security settings
app.config['SESSION_COOKIE_SECURE'] = IS_PRODUCTION  # HTTPS only in production
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JS access
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection
app.config['PERMANENT_SESSION_LIFETIME'] = EPHEMERAL_TTL  # Match file TTL

logger.info("Starting Transfercc - ChatGPT to Claude Migration Tool")
logger.info(f"Environment: {FLASK_ENV}")
logger.info(f"MAX_CONTENT_LENGTH: {app.config['MAX_CONTENT_LENGTH']} bytes")
logger.info(f"SECRET_KEY configured: {bool(os.environ.get('SECRET_KEY'))}")

parser = None

# Ephemeral session-based file storage (local filesystem only - NO cloud storage)
# All files are stored locally in temp directory, scoped by session_id, and auto-delete after 2 hours
# This requires NO external services (no AWS S3, no cloud storage, no database)
# Files are stored in: {tempdir}/transfercc_sessions/
# Format: {session_id}_conv_{file_id}.json (session-scoped for security)

def get_writable_storage_dir():
    """Find and verify a writable storage directory"""
    # Allow override via environment variable
    custom_temp_dir = os.environ.get('TEMP_DIR') or os.environ.get('TMPDIR')
    
    candidates = []
    if custom_temp_dir:
        candidates.append(os.path.join(custom_temp_dir, 'transfercc_sessions'))
    
    # Try system temp directory first
    candidates.append(os.path.join(tempfile.gettempdir(), 'transfercc_sessions'))
    # Explicit /tmp fallback
    candidates.append('/tmp/transfercc_sessions')
    # Current working directory fallback (if temp not available)
    candidates.append(os.path.join(os.getcwd(), 'tmp', 'transfercc_sessions'))
    
    for storage_dir in candidates:
        try:
            # Create directory if it doesn't exist
            os.makedirs(storage_dir, exist_ok=True)
            
            # Test write permissions by creating a test file
            test_file = os.path.join(storage_dir, '.write_test')
            try:
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
                
                # Verify we can create subdirectories
                test_subdir = os.path.join(storage_dir, '.test_subdir')
                os.makedirs(test_subdir, exist_ok=True)
                os.rmdir(test_subdir)
                
                logger.info(f"✓ Using writable storage directory: {storage_dir}")
                return storage_dir
            except (IOError, OSError, PermissionError) as e:
                logger.warning(f"Directory {storage_dir} not writable: {e}")
                continue
        except (OSError, PermissionError) as e:
            logger.warning(f"Could not create directory {storage_dir}: {e}")
            continue
    
    # Last resort: use system temp without subdirectory
    fallback = tempfile.gettempdir()
    logger.warning(f"⚠ Using fallback storage (no subdirectory): {fallback}")
    return fallback

STORAGE_DIR = get_writable_storage_dir()

# Verify storage directory on startup
try:
    # Create a test file to verify write access
    test_path = os.path.join(STORAGE_DIR, '.startup_test')
    with open(test_path, 'w') as f:
        f.write('startup_test')
    os.remove(test_path)
    logger.info(f"✓ Storage directory verified writable: {STORAGE_DIR}")
except Exception as e:
    logger.error(f"✗ CRITICAL: Storage directory not writable: {STORAGE_DIR} - {e}")
    logger.error("Application may not function correctly. Check filesystem permissions.")

# Background job processing for large file uploads
# Store job status in memory only (job_id -> status dict)
# NO database, NO external storage - pure in-memory with session-scoped files
processing_jobs = {}
job_lock = threading.Lock()

# Enhanced cleanup for ephemeral storage (local filesystem only)
def cleanup_old_files():
    """Remove files older than EPHEMERAL_TTL - local filesystem cleanup (NO cloud storage)"""
    try:
        current_time = time.time()
        deleted_count = 0
        
        # Clean up conversation files (with or without session prefix)
        for pattern in ['conv_*.json', '*_conv_*.json']:
            for filepath in glob.glob(os.path.join(STORAGE_DIR, pattern)):
                if os.path.getmtime(filepath) < current_time - EPHEMERAL_TTL:
                    try:
                        os.remove(filepath)
                        deleted_count += 1
                        logger.debug(f"Cleaned up expired file: {filepath}")
                    except Exception as e:
                        logger.warning(f"Error deleting {filepath}: {e}")
        
        # Clean up upload files
        upload_dir = os.path.join(STORAGE_DIR, 'uploads')
        if os.path.exists(upload_dir):
            for filepath in glob.glob(os.path.join(upload_dir, '*')):
                if os.path.getmtime(filepath) < current_time - EPHEMERAL_TTL:
                    try:
                        os.remove(filepath)
                        deleted_count += 1
                    except Exception as e:
                        logger.warning(f"Error deleting upload {filepath}: {e}")
        
        # Clean up reassembled files
        for filepath in glob.glob(os.path.join(STORAGE_DIR, 'reassembled_*')):
            if os.path.getmtime(filepath) < current_time - EPHEMERAL_TTL:
                try:
                    os.remove(filepath)
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Error deleting reassembled {filepath}: {e}")
        
        # Clean up chunk directories
        chunks_dir = os.path.join(STORAGE_DIR, 'chunks')
        if os.path.exists(chunks_dir):
            for chunk_dir in glob.glob(os.path.join(chunks_dir, '*')):
                if os.path.isdir(chunk_dir):
                    # Check if directory is old
                    try:
                        dir_mtime = os.path.getmtime(chunk_dir)
                        if dir_mtime < current_time - EPHEMERAL_TTL:
                            shutil.rmtree(chunk_dir)
                            deleted_count += 1
                    except Exception as e:
                        logger.warning(f"Error deleting chunk dir {chunk_dir}: {e}")
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired files")
            
    except Exception as e:
        logger.warning(f"Error cleaning up old files: {e}")

def cleanup_expired_jobs():
    """Remove expired jobs and their associated files"""
    current_time = time.time()
    expired_jobs = []
    
    with job_lock:
        for job_id, job in list(processing_jobs.items()):
            expires_at = job.get('expires_at', 0)
            
            # Check if job expired
            if expires_at > 0 and current_time > expires_at:
                expired_jobs.append(job_id)
                
                # Clean up associated files
                storage_file = job.get('storage_file')
                if storage_file and os.path.exists(storage_file):
                    try:
                        os.remove(storage_file)
                        logger.info(f"Removed expired job file: {storage_file}")
                    except Exception as e:
                        logger.warning(f"Error removing expired file: {e}")
                
                # Clean up input file if exists
                input_file = job.get('input_file')
                if input_file and os.path.exists(input_file):
                    try:
                        os.remove(input_file)
                    except:
                        pass
        
        # Remove expired jobs
        for job_id in expired_jobs:
            del processing_jobs[job_id]
            logger.info(f"Removed expired job: {job_id}")

# Periodic cleanup thread for ephemeral storage
def periodic_ephemeral_cleanup():
    """Background thread for periodic cleanup"""
    while True:
        try:
            cleanup_old_files()
            cleanup_expired_jobs()
        except Exception as e:
            logger.error(f"Periodic cleanup error: {e}")
        time.sleep(EPHEMERAL_CLEANUP_INTERVAL)

# Start cleanup thread on app startup
cleanup_thread = threading.Thread(target=periodic_ephemeral_cleanup, daemon=True)
cleanup_thread.start()
logger.info("Ephemeral storage cleanup thread started")

# Authentication - Google Sign-In with Firebase (isolated from file processing)
def login_required(f):
    """Decorator to require Google Sign-In - isolated from file processing"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # In production, Firebase MUST be configured
        if IS_PRODUCTION and not FIREBASE_AUTH_ENABLED:
            logger.error("Firebase Auth not configured in production! Authentication required.")
            return jsonify({"error": "Authentication required. Please configure Firebase."}), 503
        
        # In development, allow access if Firebase not configured (for local testing)
        if not FIREBASE_AUTH_ENABLED:
            return f(*args, **kwargs)
        
        # Check session - NO Firebase calls here, just session check
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401
        
        # User authenticated - proceed with original function
        # This function has NO access to Firebase - completely isolated
        return f(*args, **kwargs)
    
    return decorated_function


@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    if IS_PRODUCTION:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    # Content Security Policy - Allow Firebase and Google OAuth
    # Required domains for Firebase Auth with Google Sign-In:
    # - apis.google.com: Google OAuth API
    # - accounts.google.com: OAuth redirects
    # - www.gstatic.com: Firebase static resources
    # - *.googleapis.com: Firebase/Google APIs
    # - *.firebaseapp.com: Firebase hosting
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://www.gstatic.com https://apis.google.com https://accounts.google.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://*.googleapis.com https://*.firebaseapp.com https://*.firebaseio.com https://accounts.google.com; "
        "frame-src 'self' https://accounts.google.com https://*.firebaseapp.com; "
        "frame-ancestors 'self';"
    )
    response.headers['Content-Security-Policy'] = csp
    
    return response

# HTML Template with embedded CSS and JS
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transfercc • ChatGPT history to Claude</title>
    <link rel="icon" type="image/png" href="/static/images/Favicon.png">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #FAFAFA;
            --bg-secondary: #FFFFFF;
            --bg-tertiary: #F5F5F5;
            --bg-card: #FFFFFF;
            --text-primary: #1A1A1A;
            --text-secondary: #525252;
            --text-muted: #8C8C8C;
            --accent: #1A1A1A;
            --accent-hover: #333333;
            --border-color: #E5E5E5;
            --border-subtle: #EFEFEF;
            --radius: 3px;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        html, body {
            overflow-x: hidden;
            width: 100%;
            max-width: 100vw;
        }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            line-height: 1.5;
            font-size: 14px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
            padding-bottom: 64px;
            overflow-x: hidden;
        }
        
        /* Header */
        header {
            margin-bottom: 2rem;
            padding: 1.5rem 0;
            border-bottom: 1px solid var(--border-color);
        }
        
        .header-wrapper {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
        }
        
        .header-content {
            min-width: 0;
            flex: 1;
        }
        
        .header-actions {
            display: flex;
            align-items: center;
            gap: 8px;
            flex-shrink: 0;
        }
        
        .logo {
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--text-primary);
            letter-spacing: -0.02em;
        }
        
        .logo span {
            color: var(--text-muted);
            font-weight: 400;
        }
        
        .subtitle {
            color: var(--text-muted);
            font-size: 0.875rem;
            margin-top: 0.25rem;
        }
        
        .privacy-badge {
            font-size: 0.6875rem;
            color: var(--text-muted);
            margin-top: 0.5rem;
            display: flex;
            align-items: center;
            gap: 0.375rem;
        }
        
        /* Stats bar */
        .stats-bar {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 1rem;
            margin-bottom: 1.5rem;
            padding: 1rem 0;
            border-bottom: 1px solid var(--border-subtle);
        }
        
        .stat {
            text-align: left;
            min-width: 0;
        }
        
        .stat-value {
            font-size: 1.5rem;
            font-weight: 600;
            color: var(--text-primary);
            font-family: 'JetBrains Mono', monospace;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .stat-label {
            font-size: 0.75rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        
        /* Search */
        .search-container {
            margin-bottom: 1.5rem;
        }
        
        .search-box {
            display: flex;
            gap: 0.5rem;
            max-width: 500px;
            width: 100%;
        }
        
        .search-input {
            flex: 1;
            min-width: 0;
            padding: 0.625rem 0.875rem;
            font-size: 0.875rem;
            font-family: inherit;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            color: var(--text-primary);
            transition: border-color 0.15s ease;
        }
        
        .search-input:focus {
            outline: none;
            border-color: var(--accent);
        }
        
        .search-input::placeholder {
            color: var(--text-muted);
        }
        
        .search-btn {
            padding: 0.625rem 1rem;
            font-size: 0.875rem;
            font-weight: 500;
            font-family: inherit;
            background: var(--accent);
            border: none;
            border-radius: var(--radius);
            color: white;
            cursor: pointer;
            transition: background 0.15s ease;
        }
        
        .search-btn:hover {
            background: var(--accent-hover);
        }
        
        /* Autocomplete dropdown */
        .autocomplete-wrapper {
            position: relative;
            flex: 2;
            min-width: 0;
        }
        
        .autocomplete-dropdown {
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-top: none;
            border-radius: 0 0 var(--radius) var(--radius);
            max-height: 250px;
            overflow-y: auto;
            z-index: 100;
            display: none;
        }
        
        .autocomplete-dropdown.active {
            display: block;
        }
        
        .autocomplete-item {
            padding: 0.5rem 0.75rem;
            cursor: pointer;
            font-size: 0.8125rem;
            border-bottom: 1px solid var(--border-subtle);
            transition: background 0.1s ease;
        }
        
        .autocomplete-item:last-child {
            border-bottom: none;
        }
        
        .autocomplete-item:hover {
            background: var(--bg-tertiary);
        }
        
        .autocomplete-match {
            font-weight: 500;
            color: var(--text-primary);
        }
        
        .autocomplete-title {
            color: var(--text-muted);
            font-size: 0.75rem;
            margin-top: 0.125rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        /* Layout */
        .main-layout {
            display: grid;
            grid-template-columns: 240px 1fr;
            gap: 1.5rem;
            min-width: 0;
        }
        
        @media (max-width: 900px) {
            .main-layout {
                grid-template-columns: 1fr;
            }
        }
        
        /* Sidebar */
        .sidebar {
            background: var(--bg-secondary);
            border-radius: var(--radius);
            padding: 1rem;
            border: 1px solid var(--border-color);
            height: fit-content;
            position: sticky;
            top: 1rem;
            min-width: 0;
            overflow: hidden;
        }
        
        .sidebar-title {
            font-size: 0.6875rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--text-muted);
            margin-bottom: 0.75rem;
            font-weight: 500;
        }
        
        .project-list {
            list-style: none;
        }
        
        .project-item {
            padding: 0.5rem 0.75rem;
            margin-bottom: 0.125rem;
            border-radius: var(--radius);
            cursor: pointer;
            transition: background 0.1s ease;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .project-item:hover {
            background: var(--bg-tertiary);
        }
        
        .project-item.active {
            background: var(--bg-tertiary);
            font-weight: 500;
        }
        
        .project-name {
            font-size: 0.8125rem;
        }
        
        .project-count {
            font-size: 0.75rem;
            color: var(--text-muted);
            font-family: 'JetBrains Mono', monospace;
        }
        
        /* Conversations list */
        .conversations-container {
            background: var(--bg-secondary);
            border-radius: var(--radius);
            border: 1px solid var(--border-color);
            overflow: hidden;
            min-width: 0;
        }
        
        .conversations-header {
            padding: 0.875rem 1rem;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .conversations-title {
            font-size: 0.8125rem;
            font-weight: 500;
        }
        
        .export-all-btn {
            padding: 0.375rem 0.75rem;
            font-size: 0.75rem;
            font-family: inherit;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.1s ease;
        }
        
        .export-all-btn:hover {
            border-color: var(--accent);
            color: var(--accent);
        }
        
        .conversation-list {
            overflow-y: auto;
        }
        
        .conversation-item {
            padding: 0.875rem 1rem;
            border-bottom: 1px solid var(--border-subtle);
            cursor: pointer;
            transition: background 0.1s ease;
            overflow: hidden;
            min-width: 0;
        }
        
        .conversation-item:hover {
            background: var(--bg-tertiary);
        }
        
        .conversation-item.selected {
            background: var(--bg-tertiary);
        }
        
        .conv-title {
            font-size: 0.875rem;
            font-weight: 500;
            margin-bottom: 0.25rem;
            color: var(--text-primary);
            word-wrap: break-word;
        }
        
        .conv-preview {
            font-size: 0.8125rem;
            color: var(--text-muted);
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            margin-bottom: 0.375rem;
            word-break: break-word;
        }
        
        .conv-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            font-size: 0.6875rem;
            color: var(--text-muted);
        }
        
        .conv-meta span {
            display: flex;
            align-items: center;
            gap: 0.25rem;
            white-space: nowrap;
        }
        
        /* Modal */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            z-index: 1000;
            justify-content: center;
            align-items: center;
            padding: 2rem;
        }
        
        .modal-overlay.active {
            display: flex;
        }
        
        .modal {
            background: var(--bg-secondary);
            border-radius: var(--radius);
            width: 100%;
            max-width: 800px;
            max-height: 85vh;
            overflow: hidden;
            border: 1px solid var(--border-color);
            box-shadow: 0 16px 48px rgba(0, 0, 0, 0.12);
        }
        
        .modal-header {
            padding: 1rem 1.25rem;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
        }
        
        .modal-title {
            font-size: 1rem;
            font-weight: 600;
            margin-bottom: 0.25rem;
        }
        
        .modal-subtitle {
            font-size: 0.75rem;
            color: var(--text-muted);
        }
        
        .modal-actions {
            display: flex;
            gap: 0.5rem;
        }
        
        .modal-btn {
            padding: 0.375rem 0.75rem;
            font-size: 0.75rem;
            font-family: inherit;
            border-radius: var(--radius);
            cursor: pointer;
            transition: all 0.1s ease;
        }
        
        .modal-btn.copy {
            background: var(--accent);
            border: none;
            color: white;
        }
        
        .modal-btn.copy:hover {
            background: var(--accent-hover);
        }
        
        .modal-btn.close {
            background: transparent;
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
        }
        
        .modal-btn.close:hover {
            border-color: var(--text-secondary);
        }
        
        .modal-body {
            padding: 1.25rem;
            overflow-y: auto;
            max-height: calc(85vh - 80px);
        }
        
        /* Message styles */
        .message {
            margin-bottom: 1rem;
            padding: 0.875rem 1rem;
            border-radius: var(--radius);
            background: var(--bg-tertiary);
        }
        
        .message.user {
            border-left: 2px solid var(--text-muted);
        }
        
        .message.assistant {
            border-left: 2px solid var(--accent);
        }
        
        .message-header {
            display: flex;
            align-items: center;
            gap: 0.375rem;
            margin-bottom: 0.5rem;
            font-size: 0.6875rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }
        
        .message.user .message-header {
            color: var(--text-muted);
        }
        
        .message.assistant .message-header {
            color: var(--accent);
        }
        
        .message-content {
            font-size: 0.8125rem;
            line-height: 1.6;
            color: var(--text-secondary);
            white-space: pre-wrap;
            word-wrap: break-word;
            overflow-wrap: break-word;
            word-break: break-word;
        }
        
        .message-content code {
            background: var(--bg-primary);
            padding: 0.125rem 0.375rem;
            border-radius: 2px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8em;
            word-break: break-all;
        }
        
        /* Toast notification */
        .toast {
            position: fixed;
            bottom: 1.5rem;
            left: 50%;
            transform: translateX(-50%) translateY(100px);
            background: var(--accent);
            color: white;
            padding: 0.625rem 1.25rem;
            border-radius: var(--radius);
            font-size: 0.8125rem;
            font-weight: 500;
            opacity: 0;
            transition: all 0.2s ease;
            z-index: 2000;
        }
        
        .toast.show {
            transform: translateX(-50%) translateY(0);
            opacity: 1;
        }
        
        /* Upload area */
        .upload-area {
            border: 1px dashed var(--accent);
            border-radius: var(--radius);
            padding: 3.5rem 2rem;
            text-align: center;
            margin: 0;
            transition: all 0.15s ease;
            cursor: pointer;
            background: var(--bg-secondary);
            position: relative;
        }
        
        .upload-area:hover {
            border-color: var(--accent);
        }
        
        .upload-area.dragover {
            border-color: var(--accent);
            background: var(--bg-tertiary);
        }
        
        .upload-icon {
            position: absolute !important;
            top: 50% !important;
            font-size: 2.5rem;
            margin-bottom: 0.75rem;
        }
        
        .upload-text {
            font-size: 0.9375rem;
            color: var(--text-secondary);
            margin-bottom: 0.25rem;
        }
        
        .upload-hint {
            font-size: 0.8125rem;
            color: var(--text-muted);
        }
        
        .hidden {
            display: none;
        }
        
        /* Upload progress */
        .upload-progress {
            margin-top: 1.5rem;
            width: 100%;
            max-width: 300px;
            margin-left: auto;
            margin-right: auto;
        }
        
        .progress-bar {
            height: 4px;
            background: var(--border-color);
            border-radius: 2px;
            overflow: hidden;
        }
        
        .progress-fill {
            height: 100%;
            background: var(--accent);
            width: 0%;
            transition: width 0.3s ease;
        }
        
        .progress-text {
            margin-top: 0.5rem;
            font-size: 0.8125rem;
            color: var(--text-muted);
        }
        
        .upload-area.uploading {
            pointer-events: none;
            opacity: 0.7;
        }
        
        .upload-area.error {
            border-color: #e53935;
            background: rgba(229, 57, 53, 0.05);
        }
        
        .upload-area.success {
            border-color: #43a047;
            background: rgba(67, 160, 71, 0.08);
            border-style: solid;
        }
        
        .upload-area.success .upload-icon-ring {
            background: #43a047;
            width: 80px;
            height: 80px;
            animation: successPulse 0.6s ease-out;
        }
        
        .upload-area.success .upload-icon {
            color: white;
            font-size: 2.5rem;
        }
        
        @keyframes successPulse {
            0% {
                transform: translate(-50%, -50%) scale(0.8);
                opacity: 0.5;
            }
            50% {
                transform: translate(-50%, -50%) scale(1.1);
            }
            100% {
                transform: translate(-50%, -50%) scale(1);
                opacity: 1;
            }
        }
        
        .error-message {
            color: #e53935;
            font-size: 0.8125rem;
            margin-top: 1rem;
        }
        
        /* Scrollbar */
        ::-webkit-scrollbar {
            width: 6px;
        }
        
        ::-webkit-scrollbar-track {
            background: transparent;
        }
        
        ::-webkit-scrollbar-thumb {
            background: var(--border-color);
            border-radius: 3px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: var(--text-muted);
        }
        
        /* Projects Overview Section */
        .projects-section {
            margin-bottom: 1.5rem;
            min-width: 0;
        }
        
        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }
        
        .section-title {
            font-size: 24px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: var(--text-primary);
        }
        
        .section-title span {
            font-size: 24px;
        }
        
        .projects-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(min(220px, 100%), 1fr));
            gap: 0.75rem;
        }
        
        .project-card {
            background: var(--bg-secondary);
            border-radius: var(--radius);
            padding: 1rem;
            border: 1px solid var(--border-color);
            cursor: pointer;
            transition: border-color 0.1s ease;
            overflow: hidden;
            min-width: 0;
        }
        
        .project-card:hover {
            border-color: var(--accent);
        }
        
        .project-card-icon {
            font-size: 1.25rem;
            margin-bottom: 0.5rem;
        }
        
        .project-card-title {
            font-size: 0.875rem;
            font-weight: 500;
            margin-bottom: 0.25rem;
            color: var(--text-primary);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .project-card-stats {
            display: flex;
            gap: 1rem;
            margin-top: 0.75rem;
            padding-top: 0.75rem;
            border-top: 1px solid var(--border-subtle);
        }
        
        .project-card-stat {
            text-align: left;
        }
        
        .project-card-stat-value {
            font-size: 0.9375rem;
            font-weight: 600;
            color: var(--text-primary);
            font-family: 'JetBrains Mono', monospace;
        }
        
        .project-card-stat-label {
            font-size: 0.625rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        
        .project-card-recent {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 0.5rem;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .projects-collapsed {
            display: none;
        }
        
        /* Tab navigation */
        .tab-nav {
            display: flex;
            gap: 0;
            margin-bottom: 1.5rem;
            border-bottom: 1px solid var(--border-color);
            position: relative;
            z-index: 1;
        }
        
        .tab-btn {
            padding: 0.625rem 1rem;
            font-size: 0.8125rem;
            font-family: inherit;
            background: transparent;
            border: none;
            border-bottom: 2px solid transparent;
            margin-bottom: -1px;
            color: var(--text-muted);
            cursor: pointer;
            transition: all 0.1s ease;
            display: flex;
            align-items: center;
            gap: 0.375rem;
            -webkit-tap-highlight-color: rgba(0, 0, 0, 0.1);
            touch-action: manipulation;
        }
        
        .tab-btn:hover {
            color: var(--text-primary);
        }
        
        .tab-btn.active {
            color: var(--text-primary);
            border-bottom-color: var(--accent);
            font-weight: 500;
        }
        
        .tab-content {
            display: none;
            min-width: 0;
        }
        
        .tab-content.active {
            display: block;
        }
        
        /* Landing Page Styles */
        .landing-page {
            max-width: 720px;
            width: 100%;
            margin: 0 auto;
            padding-bottom: 5rem;
            min-height: calc(100vh - 8rem);
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        
        .landing-hero {
            text-align: center;
            margin-bottom: 2.5rem;
        }
        
        .hero-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.375rem;
            padding: 0.375rem 0.875rem;
            background: var(--bg-tertiary);
            border-radius: 100px;
            font-size: 0.75rem;
            color: var(--text-secondary);
            margin-bottom: 1.25rem;
            border: 1px solid var(--border-subtle);
        }
        
        .hero-title {
            font-size: 1.75rem;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 0.75rem;
            letter-spacing: -0.02em;
            line-height: 1.3;
        }
        
        .hero-description {
            font-size: 1rem;
            color: var(--text-muted);
            line-height: 1.6;
            max-width: 540px;
            width: 100%;
            margin: 0 auto;
            word-wrap: break-word;
        }
        
        .landing-card {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 0.25rem;
            margin-bottom: 2rem;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
            position: relative;
        }
        
        .landing-card .upload-area {
            border-radius: 6px;
            padding: 3rem 2rem;
            border-style: dashed;
            margin: 0;
        }
        
        .upload-icon-wrapper {
            position: relative;
            display: inline-block;
            margin-bottom: 1rem;
            width: 80px;
            height: 80px;
        }
        
        .upload-icon-ring {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 80px;
            height: 80px;
            border-radius: 50%;
            background: var(--bg-tertiary);
            z-index: 0;
        }
        
        .upload-icon-wrapper .upload-icon {
            font-size: 3rem;
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            z-index: 1;
            line-height: 1;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .landing-card .upload-text {
            font-size: 1.0625rem;
            font-weight: 500;
            color: var(--text-primary);
            margin-bottom: 0.375rem;
        }
        
        .landing-card .upload-hint {
            font-size: 0.875rem;
        }
        
        /* Features Grid */
        .features-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1rem;
            margin-bottom: 2rem;
        }
        
        @media (max-width: 600px) {
            .features-grid {
                grid-template-columns: 1fr;
            }
        }
        
        .feature-item {
            display: flex;
            align-items: flex-start;
            gap: 0.875rem;
            padding: 1rem;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
        }
        
        .feature-icon {
            font-size: 1.25rem;
            flex-shrink: 0;
            width: 36px;
            height: 36px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: var(--bg-tertiary);
            border-radius: 8px;
        }
        
        .feature-content h4 {
            font-size: 0.875rem;
            font-weight: 500;
            color: var(--text-primary);
            margin-bottom: 0.125rem;
        }
        
        .feature-content p {
            font-size: 0.8125rem;
            color: var(--text-muted);
            line-height: 1.4;
        }
        
        /* Features Grid Unboxed */
        .features-grid-unboxed {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1rem;
            margin-bottom: 2rem;
        }
        
        @media (max-width: 600px) {
            .features-grid-unboxed {
                grid-template-columns: 1fr;
            }
        }
        
        .feature-item-unboxed {
            display: flex;
            align-items: flex-start;
            gap: 0.875rem;
            padding: 0;
        }
        
        .feature-icon-unboxed {
            font-size: 1.25rem;
            flex-shrink: 0;
            width: 36px;
            height: 36px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        /* Smart Group Explainer */
        .smart-group-explainer {
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.08) 0%, rgba(168, 85, 247, 0.08) 100%);
            border-radius: var(--radius);
            padding: 1rem 1.25rem;
            margin-bottom: 1rem;
            border: 1px solid rgba(99, 102, 241, 0.15);
        }
        
        .smart-group-explainer p {
            color: var(--text-secondary);
            font-size: 0.8125rem;
            line-height: 1.5;
            margin: 0;
            word-wrap: break-word;
        }
        
        .smart-group-explainer strong {
            color: var(--text-primary);
        }
        
        /* Smart Group Form */
        .smart-group-form {
            background: var(--bg-secondary);
            border-radius: var(--radius);
            padding: 1rem;
            margin-bottom: 1rem;
            border: 1px solid var(--border-color);
        }
        
        .smart-group-form-title {
            font-size: 0.8125rem;
            margin-bottom: 0.5rem;
            color: var(--text-primary);
            font-weight: 500;
        }
        
        .smart-group-form-desc {
            color: var(--text-muted);
            font-size: 0.75rem;
            margin-bottom: 0.75rem;
        }
        
        .smart-group-inputs {
            display: flex;
            gap: 0.5rem;
            align-items: flex-start;
            width: 100%;
        }
        
        .smart-group-inputs .autocomplete-wrapper {
            flex: 1;
        }
        
        .smart-group-input {
            flex: 1;
            min-width: 0;
            width: 100%;
            padding: 0.5rem 0.75rem;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            color: var(--text-primary);
            font-family: inherit;
            font-size: 0.8125rem;
        }
        
        .smart-group-btn {
            padding: 0.5rem 1rem;
            background: var(--accent);
            border: none;
            border-radius: var(--radius);
            color: white;
            font-family: inherit;
            cursor: pointer;
            font-size: 0.8125rem;
            flex-shrink: 0;
            white-space: nowrap;
        }
        
        /* How-to Section */
        .howto-section {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }
        
        .howto-header {
            margin-bottom: 1.25rem;
        }
        
        .howto-content {
            display: flex;
            gap: 1.5rem;
            align-items: flex-start;
        }
        
        .howto-video {
            flex: 1;
            min-width: 0;
            border-radius: var(--radius);
            overflow: hidden;
            background: var(--bg-tertiary);
        }
        
        .howto-video video {
            width: 100%;
            height: auto;
            display: block;
            border-radius: var(--radius);
        }
        
        .howto-content .howto-steps {
            flex: 1;
            min-width: 0;
        }
        
        .howto-badge {
            display: inline-block;
            font-size: 0.6875rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
        }
        
        .howto-header h3 {
            font-size: 1rem;
            font-weight: 500;
            color: var(--text-primary);
        }
        
        .howto-steps {
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }
        
        .howto-step {
            display: flex;
            align-items: flex-start;
            gap: 1rem;
        }
        
        .step-number {
            width: 28px;
            height: 28px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: var(--accent);
            color: white;
            border-radius: 50%;
            font-size: 0.8125rem;
            font-weight: 600;
            flex-shrink: 0;
        }
        
        .step-content {
            flex: 1;
            padding-top: 0.125rem;
        }
        
        .step-content strong {
            display: block;
            font-size: 0.875rem;
            font-weight: 500;
            color: var(--text-primary);
            margin-bottom: 0.125rem;
        }
        
        .step-content p {
            font-size: 0.8125rem;
            color: var(--text-muted);
            margin: 0;
        }
        
        .step-content a {
            color: var(--accent);
            text-decoration: none;
        }
        
        .step-content a:hover {
            text-decoration: underline;
        }
        
        /* Privacy Footer */
        .privacy-footer {
            display: flex;
            align-items: flex-start;
            gap: 1rem;
            padding: 1.25rem;
            background: linear-gradient(135deg, rgba(26, 26, 26, 0.02) 0%, rgba(26, 26, 26, 0.05) 100%);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
        }
        
        .privacy-icon {
            font-size: 1.5rem;
            flex-shrink: 0;
        }
        
        .privacy-content {
            font-size: 0.8125rem;
            color: var(--text-muted);
            line-height: 1.6;
        }
        
        .privacy-content strong {
            color: var(--text-secondary);
            display: block;
            margin-bottom: 0.25rem;
        }
        
        /* Site Footer */
        .site-footer {
            text-align: center;
            padding: 1.5rem 1rem;
            border-top: 1px solid var(--border-color);
            font-size: 0.8125rem;
            color: var(--text-muted);
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: var(--bg-primary);
        }
        
        .site-footer a {
            color: var(--text-secondary);
            text-decoration: none;
            font-weight: 500;
            transition: color 0.15s ease;
        }
        
        .site-footer a:hover {
            color: var(--accent);
        }
        
        .twitter-preview-card {
            position: fixed;
            pointer-events: none;
            z-index: 9999;
            background: var(--bg-primary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1rem;
            width: 280px;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
            opacity: 0;
            transform: translateY(10px);
            transition: opacity 0.2s ease, transform 0.2s ease;
        }
        
        .twitter-preview-card.visible {
            opacity: 1;
            transform: translateY(0);
            pointer-events: auto;
        }
        
        .twitter-follow-btn {
            display: inline-flex;
            align-items: center;
            gap: 0.375rem;
            margin-top: 0.75rem;
            padding: 0.4rem 0.75rem;
            background: #000;
            color: #fff;
            border-radius: 100px;
            font-size: 0.75rem;
            font-weight: 500;
            text-decoration: none;
            transition: background 0.15s ease;
        }
        
        .twitter-follow-btn:hover {
            background: #333;
        }
        
        .twitter-follow-btn svg {
            width: 14px;
            height: 14px;
            fill: currentColor;
        }
        
        .twitter-preview-header {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 0.75rem;
        }
        
        .twitter-preview-avatar {
            width: 48px;
            height: 48px;
            border-radius: 50%;
            object-fit: cover;
        }
        
        .twitter-preview-names {
            flex: 1;
        }
        
        .twitter-preview-name {
            font-weight: 600;
            font-size: 0.9375rem;
            color: var(--text-primary);
        }
        
        .twitter-preview-handle {
            font-size: 0.8125rem;
            color: var(--text-muted);
        }
        
        .twitter-preview-bio {
            font-size: 0.8125rem;
            color: var(--text-secondary);
            line-height: 1.4;
            margin-bottom: 0.75rem;
        }
        
        .twitter-preview-stats {
            display: flex;
            gap: 1rem;
            font-size: 0.75rem;
            color: var(--text-muted);
        }
        
        .twitter-preview-stats strong {
            color: var(--text-primary);
            font-weight: 600;
        }
        
        /* Login Modal */
        #loginModalOverlay {
            z-index: 2000;
        }
        
        .user-info {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0 0.75rem;
            height: 34px;
            background: var(--bg-tertiary);
            border-radius: var(--radius);
            font-size: 0.75rem;
            color: var(--text-secondary);
            border: 1px solid var(--border-color);
        }
        
        .user-avatar {
            width: 22px;
            height: 22px;
            border-radius: 50%;
        }
        
        .logout-btn {
            padding: 0;
            font-size: 0.75rem;
            background: transparent;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            margin-left: 0.5rem;
            display: inline-flex;
            align-items: center;
        }
        
        /* Header action button (Load Different Data) */
        .header-action-btn {
            padding: 0 0.75rem;
            height: 34px;
            font-size: 0.75rem;
            font-family: inherit;
            background: transparent;
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.1s ease;
            display: inline-flex;
            align-items: center;
        }
        
        .header-action-btn:hover {
            border-color: var(--accent);
            color: var(--text-primary);
        }
        
        .logout-btn:hover {
            color: var(--accent);
            text-decoration: underline;
        }
        
        /* ===========================================
           MOBILE RESPONSIVE STYLES
           =========================================== */
        
        /* Tablet and smaller (768px and below) */
        @media (max-width: 768px) {
            .container {
                padding: 1rem;
                padding-bottom: 80px;
            }
            
            /* Header */
            header {
                margin-bottom: 1.5rem;
                padding: 1rem 0;
            }
            
            .header-wrapper {
                flex-direction: column;
                gap: 1rem;
                align-items: flex-start;
            }
            
            .header-actions {
                width: 100%;
                flex-wrap: wrap;
            }
            
            .logo {
                font-size: 1.125rem;
            }
            
            .privacy-badge {
                flex-wrap: wrap;
            }
            
            /* Stats bar */
            .stats-bar {
                grid-template-columns: repeat(2, 1fr);
                gap: 0.75rem;
                padding: 0.75rem 0;
            }
            
            .stat-value {
                font-size: 1.25rem;
            }
            
            .stat-label {
                font-size: 0.6875rem;
            }
            
            /* Search */
            .search-container {
                margin-bottom: 1rem;
            }
            
            .search-box {
                max-width: 100%;
            }
            
            .search-input {
                width: 100%;
                min-width: 0;
            }
            
            .search-btn {
                flex-shrink: 0;
            }
            
            /* Tab navigation */
            .tab-nav {
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
                scrollbar-width: none;
                -ms-overflow-style: none;
                margin-bottom: 1rem;
                gap: 0;
            }
            
            .tab-nav::-webkit-scrollbar {
                display: none;
            }
            
            .tab-btn {
                padding: 0.5rem 0.75rem;
                font-size: 0.75rem;
                white-space: nowrap;
                flex-shrink: 0;
            }
            
            .tab-btn span {
                display: none;
            }
            
            /* Projects grid */
            .projects-grid {
                grid-template-columns: 1fr;
                gap: 0.5rem;
            }
            
            .project-card {
                padding: 0.875rem;
            }
            
            .project-card-title {
                font-size: 0.8125rem;
            }
            
            .project-card-stats {
                margin-top: 0.5rem;
                padding-top: 0.5rem;
            }
            
            /* Section header */
            .section-header {
                flex-direction: column;
                align-items: flex-start;
                gap: 0.5rem;
            }
            
            .section-title {
                font-size: 1.25rem;
            }
            
            .section-title span {
                font-size: 1.25rem;
            }
            
            /* Smart groups */
            .smart-group-explainer {
                padding: 0.875rem 1rem;
            }
            
            .smart-group-explainer p {
                font-size: 0.75rem;
            }
            
            .smart-group-inputs {
                flex-direction: column;
            }
            
            .smart-group-input {
                width: 100%;
            }
            
            .smart-group-btn {
                width: 100%;
            }
            
            .smart-group-inputs .autocomplete-wrapper {
                width: 100%;
                flex: none;
            }
            
            /* Main layout - sidebar and conversations */
            .main-layout {
                grid-template-columns: 1fr;
                gap: 1rem;
            }
            
            .sidebar {
                position: relative;
                top: 0;
                order: -1;
            }
            
            .project-list {
                display: flex;
                flex-wrap: wrap;
                gap: 0.25rem;
            }
            
            .project-item {
                padding: 0.375rem 0.625rem;
                font-size: 0.75rem;
                border: 1px solid var(--border-color);
                border-radius: var(--radius);
                flex: 0 0 auto;
            }
            
            .project-item .project-name {
                font-size: 0.75rem;
            }
            
            .project-item .project-count {
                font-size: 0.6875rem;
                margin-left: 0.25rem;
            }
            
            /* Conversations */
            .conversations-container {
                border-radius: var(--radius);
            }
            
            .conversations-header {
                padding: 0.75rem;
                flex-direction: column;
                gap: 0.5rem;
                align-items: flex-start;
            }
            
            .export-all-btn {
                width: 100%;
                text-align: center;
            }
            
            .conversation-list {
                max-height: none;
            }
            
            .conversation-item {
                padding: 0.75rem;
            }
            
            .conv-title {
                font-size: 0.8125rem;
            }
            
            .conv-preview {
                font-size: 0.75rem;
                -webkit-line-clamp: 2;
            }
            
            .conv-meta {
                flex-wrap: wrap;
                gap: 0.5rem;
                font-size: 0.625rem;
            }
            
            /* Modal */
            .modal-overlay {
                padding: 0.5rem;
                align-items: flex-end;
            }
            
            .modal {
                max-height: 90vh;
                max-width: 100%;
                border-radius: var(--radius) var(--radius) 0 0;
            }
            
            .modal-header {
                padding: 0.875rem 1rem;
                flex-direction: column;
                gap: 0.75rem;
                align-items: flex-start;
            }
            
            .modal-title {
                font-size: 0.9375rem;
            }
            
            .modal-subtitle {
                font-size: 0.6875rem;
            }
            
            .modal-actions {
                width: 100%;
                justify-content: space-between;
            }
            
            .modal-btn {
                flex: 1;
                text-align: center;
                padding: 0.5rem 0.625rem;
            }
            
            .modal-body {
                padding: 1rem;
                max-height: calc(90vh - 120px);
            }
            
            /* Messages in modal */
            .message {
                padding: 0.75rem;
                margin-bottom: 0.75rem;
            }
            
            .message-header {
                font-size: 0.625rem;
            }
            
            .message-content {
                font-size: 0.75rem;
            }
            
            /* User info */
            .user-info {
                padding: 0.375rem 0.5rem;
                font-size: 0.75rem;
            }
            
            .user-avatar {
                width: 20px;
                height: 20px;
            }
            
            /* Site footer */
            .site-footer {
                padding: 1rem;
                font-size: 0.75rem;
            }
            
            /* Landing page */
            .landing-page {
                padding-bottom: 3rem;
            }
            
            .hero-title {
                font-size: 1.375rem;
            }
            
            .hero-description {
                font-size: 0.875rem;
            }
            
            .landing-card .upload-area {
                padding: 2rem 1rem;
            }
            
            .upload-icon-wrapper {
                width: 64px;
                height: 64px;
            }
            
            .upload-icon-ring {
                width: 64px;
                height: 64px;
            }
            
            .upload-icon-wrapper .upload-icon {
                font-size: 2.5rem;
            }
            
            .upload-area.success .upload-icon-ring {
                width: 64px;
                height: 64px;
            }
            
            .upload-area.success .upload-icon {
                font-size: 2rem;
            }
            
            .howto-section {
                padding: 1rem;
            }
            
            .howto-content {
                flex-direction: column;
            }
            
            .howto-video {
                width: 100%;
            }
            
            .howto-step {
                gap: 0.75rem;
            }
            
            .step-number {
                width: 24px;
                height: 24px;
                font-size: 0.75rem;
            }
            
            .step-content strong {
                font-size: 0.8125rem;
            }
            
            .step-content p {
                font-size: 0.75rem;
            }
            
            /* Features grid */
            .features-grid,
            .features-grid-unboxed {
                grid-template-columns: 1fr;
                gap: 0.75rem;
            }
            
            .feature-item,
            .feature-item-unboxed {
                padding: 0.75rem;
            }
            
            /* Privacy footer */
            .privacy-footer {
                padding: 1rem;
                flex-direction: column;
                gap: 0.75rem;
            }
        }
        
        /* Small phones (480px and below) */
        @media (max-width: 480px) {
            .container {
                padding: 0.75rem;
                padding-bottom: 70px;
            }
            
            /* Stats - 2 per row */
            .stats-bar {
                grid-template-columns: repeat(2, 1fr);
                gap: 0.5rem;
            }
            
            .stat-value {
                font-size: 1rem;
            }
            
            /* Tab buttons even smaller */
            .tab-btn {
                padding: 0.375rem 0.5rem;
                font-size: 0.6875rem;
            }
            
            /* Project cards */
            .project-card {
                padding: 0.75rem;
            }
            
            .project-card-icon {
                font-size: 1rem;
            }
            
            .project-card-title {
                font-size: 0.75rem;
            }
            
            .project-card-stat-value {
                font-size: 0.8125rem;
            }
            
            .project-card-stat-label {
                font-size: 0.5625rem;
            }
            
            .project-card-recent {
                font-size: 0.6875rem;
            }
            
            /* Sidebar filters - horizontal scroll */
            .sidebar {
                padding: 0.75rem;
            }
            
            .project-list {
                flex-wrap: nowrap;
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
                scrollbar-width: none;
                padding-bottom: 0.25rem;
            }
            
            .project-list::-webkit-scrollbar {
                display: none;
            }
            
            .project-item {
                flex-shrink: 0;
            }
            
            /* Conversations */
            .conversation-item {
                padding: 0.625rem;
            }
            
            .conv-title {
                font-size: 0.75rem;
            }
            
            .conv-preview {
                font-size: 0.6875rem;
                -webkit-line-clamp: 1;
            }
            
            /* Modal - full screen */
            .modal-overlay {
                padding: 0;
            }
            
            .modal {
                max-height: 100vh;
                height: 100vh;
                border-radius: 0;
            }
            
            .modal-header {
                padding: 0.75rem;
            }
            
            .modal-body {
                max-height: calc(100vh - 100px);
            }
            
            /* Landing page */
            .hero-badge {
                font-size: 0.6875rem;
                padding: 0.25rem 0.625rem;
            }
            
            .hero-title {
                font-size: 1.25rem;
            }
            
            .hero-description {
                font-size: 0.8125rem;
            }
            
            .landing-card {
                margin-bottom: 1.5rem;
            }
            
            .landing-card .upload-text {
                font-size: 0.9375rem;
            }
            
            .landing-card .upload-hint {
                font-size: 0.75rem;
            }
        }
        
        /* Fix for touch devices - better tap targets */
        @media (hover: none) and (pointer: coarse) {
            .tab-btn,
            .project-item,
            .conversation-item,
            .project-card,
            .modal-btn,
            .search-btn,
            .export-all-btn,
            .logout-btn {
                min-height: 44px;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            .project-card {
                justify-content: flex-start;
                flex-direction: column;
                align-items: flex-start;
            }
            
            .conversation-item {
                flex-direction: column;
                align-items: flex-start;
            }
            
            .project-item {
                justify-content: space-between;
            }
        }
    </style>
    <!-- Firebase SDK - ONLY for Google Sign-In on frontend -->
    <script src="https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js"></script>
    <script src="https://www.gstatic.com/firebasejs/10.7.1/firebase-auth-compat.js"></script>
</head>
<body>
    <div class="container">
        {% if parser %}
        <header>
            <div class="header-wrapper">
                <div class="header-content">
                    <h1 class="logo">ChatGPT <span>→</span> Claude</h1>
                    <p class="subtitle">Your ChatGPT conversations, ready for a new home</p>
                    <p class="privacy-badge">
                        <span>🔒</span>
                        <span>No data stored in DB or cookies • Processed in memory only</span>
                    </p>
                </div>
                <div id="headerActions" class="header-actions">
                    <button onclick="clearData()" class="header-action-btn">
                        ↻ Load Different Data
                    </button>
                </div>
            </div>
        </header>
        
        {% endif %}
        {% if parser %}
        <div class="stats-bar">
            <div class="stat">
                <div class="stat-value">{{ stats.total_conversations }}</div>
                <div class="stat-label">Conversations</div>
            </div>
            <div class="stat">
                <div class="stat-value">{{ stats.total_projects }}</div>
                <div class="stat-label">Clubbed Chats</div>
            </div>
            <div class="stat">
                <div class="stat-value">{{ "{:,}".format(stats.total_messages) }}</div>
                <div class="stat-label">Messages</div>
            </div>
            <div class="stat">
                <div class="stat-value">{{ "{:,}".format(stats.total_words) }}</div>
                <div class="stat-label">Words</div>
            </div>
        </div>
        
        <div class="search-container">
            <div class="search-box">
                <input type="text" class="search-input" id="searchInput" placeholder="Search your conversations..." />
                <button class="search-btn" onclick="searchConversations()">Search</button>
            </div>
        </div>
        
        <!-- Tab Navigation -->
        <div class="tab-nav">
            <button class="tab-btn active" data-tab="smart" onclick="switchTab('smart')">
                <span>🏷️</span> Smart Groups
            </button>
            <button class="tab-btn" data-tab="projects" onclick="switchTab('projects')">
                <span>🤖</span> Clubbed Chats ({{ stats.total_projects }})
            </button>
            <button class="tab-btn" data-tab="conversations" onclick="switchTab('conversations')">
                <span>💬</span> All Conversations ({{ stats.total_conversations }})
            </button>
        </div>
        
        <!-- Clubbed Chats Tab -->
        <div class="tab-content" id="projectsTab">
            <div class="projects-section">
                <div class="section-header">
                    <h2 class="section-title"><span>🤖</span> Clubbed Chats</h2>
                </div>
                <div class="projects-grid">
                    {% for project in projects %}
                    <div class="project-card" onclick="viewProject('{{ project.id }}', '{{ project.name | replace("'", "\\'") }}')">
                        <div class="project-card-icon">📁</div>
                        <h3 class="project-card-title">{{ project.name }}</h3>
                        <div class="project-card-stats">
                            <div class="project-card-stat">
                                <div class="project-card-stat-value">{{ project.conversations|length }}</div>
                                <div class="project-card-stat-label">Chats</div>
                            </div>
                            <div class="project-card-stat">
                                <div class="project-card-stat-value">{{ project.message_count }}</div>
                                <div class="project-card-stat-label">Messages</div>
                            </div>
                        </div>
                        {% if project.conversations %}
                        <div class="project-card-recent">
                            Latest: {{ project.conversations[0].title[:40] }}{% if project.conversations[0].title|length > 40 %}...{% endif %}
                        </div>
                        {% endif %}
                    </div>
                    {% endfor %}
                    
                    {% if unassigned_count > 0 %}
                    <div class="project-card" onclick="viewProject('unassigned', 'Regular ChatGPT')">
                        <div class="project-card-icon">💬</div>
                        <h3 class="project-card-title">Regular ChatGPT</h3>
                        <div class="project-card-stats">
                            <div class="project-card-stat">
                                <div class="project-card-stat-value">{{ unassigned_count }}</div>
                                <div class="project-card-stat-label">Chats</div>
                            </div>
                        </div>
                        <div class="project-card-recent" style="color: var(--text-muted);">
                            Conversations with standard ChatGPT
                        </div>
                    </div>
                    {% endif %}
                </div>
            </div>
        </div>
        
        <!-- Smart Groups Tab -->
        <div class="tab-content active" id="smartTab">
            <div class="projects-section">
                <div class="section-header">
                    <h1 class="section-title"><span>🏷️</span> Smart Groups</h1>
                </div>
                
                <!-- Explainer -->
                <div class="smart-group-explainer">
                    <p>
                        <strong>What are Smart Groups?</strong> – Automatically organize your conversations by keywords. Create a group like "Work Projects" with keywords "project, deadline, meeting" and all matching chats will be grouped together. Great for filtering by clients, topics, or any recurring theme in your conversations.
                    </p>
                </div>
                
                <div class="smart-group-form">
                    <h3 class="smart-group-form-title">Create a Smart Group</h3>
                    <p class="smart-group-form-desc">
                        Group conversations by keywords in their titles.
                    </p>
                    <div class="smart-group-inputs">
                        <input type="text" id="groupName" placeholder="Group name" class="smart-group-input">
                        <div class="autocomplete-wrapper">
                            <input type="text" id="groupKeywords" placeholder="Keywords (comma separated)" autocomplete="off" class="smart-group-input">
                            <div class="autocomplete-dropdown" id="keywordDropdown"></div>
                        </div>
                        <button onclick="createSmartGroup()" class="smart-group-btn">
                            Create
                        </button>
                    </div>
                </div>
                
                <div id="smartGroupsList" class="projects-grid">
                    <!-- Smart groups will be added here dynamically -->
                </div>
                
                <div style="margin-top: 1.5rem;">
                    <h3 style="font-size: 0.75rem; margin-bottom: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.04em;">
                        Suggested Groups
                    </h3>
                    <div id="suggestedGroups" class="projects-grid">
                        <!-- Will be populated by JS -->
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Conversations Tab -->
        <div class="tab-content" id="conversationsTab">
            <div class="main-layout">
                <aside class="sidebar">
                    <h3 class="sidebar-title">Filter by Project</h3>
                    <ul class="project-list">
                        <li class="project-item active" data-filter="all">
                            <span class="project-name">📚 All Conversations</span>
                            <span class="project-count">{{ stats.total_conversations }}</span>
                        </li>
                        {% for project in projects %}
                        <li class="project-item" data-filter="{{ project.id }}">
                            <span class="project-name">📁 {{ project.name[:25] }}{% if project.name|length > 25 %}...{% endif %}</span>
                            <span class="project-count">{{ project.conversations|length }}</span>
                        </li>
                        {% endfor %}
                        {% if unassigned_count > 0 %}
                        <li class="project-item" data-filter="unassigned">
                            <span class="project-name">📄 Unassigned</span>
                            <span class="project-count">{{ unassigned_count }}</span>
                        </li>
                        {% endif %}
                    </ul>
                </aside>
                
                <main class="conversations-container">
                    <div class="conversations-header">
                        <h2 class="conversations-title" id="conversationsTitle">All Conversations</h2>
                        <button class="export-all-btn" onclick="exportAll()">📥 Export All as Markdown</button>
                    </div>
                    <div class="conversation-list" id="conversationList">
                        {% for conv in conversations %}
                        <div class="conversation-item" data-id="{{ conv.id }}" data-project="{{ conv.project_id or 'unassigned' }}" onclick="showConversation('{{ conv.id }}')">
                            <h3 class="conv-title">{{ conv.title }}</h3>
                            <p class="conv-preview">{{ conv.get_preview(150) }}</p>
                            <div class="conv-meta">
                                {% if conv.update_time %}
                                <span>📅 {{ conv.update_time.strftime('%b %d, %Y') }}</span>
                                {% endif %}
                                <span>💬 {{ conv.messages|length }} messages</span>
                                {% if conv.model %}
                                <span>🤖 {{ conv.model }}</span>
                                {% endif %}
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                </main>
            </div>
        </div>
        {% else %}
        <!-- Landing Page -->
        <div class="landing-page">
            <!-- Hero Section -->
            <div class="landing-hero">
                <div class="hero-badge"><span>✨</span> Free</div>
                <h2 class="hero-title">Migrate your ChatGPT history to Claude</h2>
                <p class="hero-description">
                    Browse, search, and export your conversations in Claude-ready markdown format. 
                    Perfect for switching AI assistants or backing up your data.
                </p>
            </div>
            
            <!-- Main Upload Card -->
            <div class="landing-card">
                <div class="upload-area" id="uploadArea" style="cursor: pointer; position: relative;">
                    <input type="file" id="fileInput" accept=".zip,.json" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; z-index: 10;" />
                    <div class="upload-icon-wrapper" style="position: relative; z-index: 1; pointer-events: none;">
                        <div class="upload-icon-ring"></div>
                        <div class="upload-icon" id="uploadIcon">📦</div>
                    </div>
                    <p class="upload-text" id="uploadText" style="position: relative; z-index: 1; pointer-events: none;">Drop your ChatGPT export here</p>
                    <p class="upload-hint" id="uploadHint" style="position: relative; z-index: 1; pointer-events: none;">ZIP file or conversations.json • Up to 500MB</p>
                    <div class="upload-progress hidden" id="uploadProgress">
                        <div class="progress-bar">
                            <div class="progress-fill" id="progressFill"></div>
                        </div>
                        <p class="progress-text" id="progressText">Uploading...</p>
                    </div>
                </div>
            </div>
            
            <!-- How-to Section -->
            <div class="howto-section">
                <div class="howto-header">
                    <span class="howto-badge">📖 Quick Guide</span>
                    <h3>How to export your ChatGPT data</h3>
                </div>
                <div class="howto-content">
                    <div class="howto-video">
                        <video autoplay loop muted playsinline>
                            <source src="/static/Howto.mov" type="video/quicktime">
                            <source src="/static/Howto.mov" type="video/mp4">
                        </video>
                    </div>
                    <div class="howto-steps">
                        <div class="howto-step">
                            <div class="step-number">1</div>
                            <div class="step-content">
                                <strong>Open ChatGPT Settings</strong>
                                <p>Go to <a href="https://chat.openai.com" target="_blank">chat.openai.com</a> → Profile → Settings</p>
                            </div>
                        </div>
                        <div class="howto-step">
                            <div class="step-number">2</div>
                            <div class="step-content">
                                <strong>Request Export</strong>
                                <p>Data controls → Export data → Confirm export</p>
                            </div>
                        </div>
                        <div class="howto-step">
                            <div class="step-number">3</div>
                            <div class="step-content">
                                <strong>Download & Upload</strong>
                                <p>Get the ZIP from your email and drop it here</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Features Section (Unboxed 2x2 Grid) -->
            <div class="features-grid-unboxed">
                <div class="feature-item-unboxed">
                    <div class="feature-icon-unboxed">🔍</div>
                    <div class="feature-content">
                        <h4>Search Everything</h4>
                        <p>Full-text search across all your conversations</p>
                    </div>
                </div>
                <div class="feature-item-unboxed">
                    <div class="feature-icon-unboxed">📁</div>
                    <div class="feature-content">
                        <h4>Smart Organization</h4>
                        <p>Auto-grouped by Clubbed Chats and projects</p>
                    </div>
                </div>
                <div class="feature-item-unboxed">
                    <div class="feature-icon-unboxed">📤</div>
                    <div class="feature-content">
                        <h4>Export to Markdown</h4>
                        <p>Copy individual chats or export everything</p>
                    </div>
                </div>
                <div class="feature-item-unboxed">
                    <div class="feature-icon-unboxed">🔒</div>
                    <div class="feature-content">
                        <h4>100% Private</h4>
                        <p>All processing happens locally in memory</p>
                    </div>
                </div>
            </div>
            
            
        </div>
        {% endif %}
    </div>
    
    <!-- Modal for conversation view -->
    <div class="modal-overlay" id="modalOverlay" onclick="closeModal(event)">
        <div class="modal" onclick="event.stopPropagation()">
            <div class="modal-header">
                <div>
                    <h2 class="modal-title" id="modalTitle">Conversation</h2>
                    <p class="modal-subtitle" id="modalSubtitle"></p>
                </div>
                <div class="modal-actions">
                    <button class="modal-btn copy" onclick="copyToClipboard()">📋 Copy as Markdown</button>
                    <button class="modal-btn close" onclick="closeModal()">✕ Close</button>
                </div>
            </div>
            <div class="modal-body" id="modalBody">
                <!-- Messages will be inserted here -->
            </div>
        </div>
    </div>
    
    <!-- Toast notification -->
    <div class="toast" id="toast">Copied to clipboard!</div>
    
    <script>
        let currentConversation = null;
        let currentMarkdown = '';
        
        // File Upload Handling
        function initUpload() {
            console.log('[UPLOAD] Initializing upload handlers...');
            const uploadArea = document.getElementById('uploadArea');
            const fileInput = document.getElementById('fileInput');
            
            if (!uploadArea || !fileInput) {
                console.error('[UPLOAD] Upload area or file input not found!', {
                    uploadArea: !!uploadArea,
                    fileInput: !!fileInput
                });
                return;
            }
            console.log('[UPLOAD] Upload elements found, attaching event listeners');
            console.log('[UPLOAD] fileInput element:', fileInput);
            console.log('[UPLOAD] fileInput type:', fileInput.type);
            console.log('[UPLOAD] fileInput accept:', fileInput.accept);
            
            // File input now covers the entire upload area, so clicks go directly to it
            // Just need to handle the change event
            console.log('[UPLOAD] File input configured to cover upload area - clicks will work directly');
            
            // Ensure file input covers the entire area and is clickable
            fileInput.style.position = 'absolute';
            fileInput.style.top = '0';
            fileInput.style.left = '0';
            fileInput.style.width = '100%';
            fileInput.style.height = '100%';
            fileInput.style.opacity = '0';
            fileInput.style.cursor = 'pointer';
            fileInput.style.zIndex = '10';
            
            // Make sure all child elements don't block the file input
            const childElements = uploadArea.querySelectorAll('*:not(#fileInput)');
            childElements.forEach(function(child) {
                child.style.pointerEvents = 'none';
                child.style.position = 'relative';
                child.style.zIndex = '1';
                console.log('[UPLOAD] Configured child element:', child.tagName, child.className || child.id);
            });
            
            // Mark as initialized
            uploadArea.setAttribute('data-listener-attached', 'true');
            devLog('[UPLOAD] Upload handlers fully initialized and child elements configured');
            
            // Test click programmatically after a short delay
            setTimeout(function() {
                console.log('[UPLOAD] Testing fileInput.click() programmatically...');
                try {
                    // This is just a test - don't actually open the picker
                    console.log('[UPLOAD] fileInput element is accessible:', {
                        exists: !!fileInput,
                        type: fileInput.type,
                        accept: fileInput.accept,
                        hasClick: typeof fileInput.click === 'function'
                    });
                } catch (err) {
                    console.error('[UPLOAD] Error testing fileInput:', err);
                }
            }, 1000);
            
            // Click handler on upload area to trigger file input
            uploadArea.addEventListener('click', function(e) {
                // Only trigger if not clicking directly on the file input
                if (e.target !== fileInput) {
                    e.preventDefault();
                    e.stopPropagation();
                    console.log('[UPLOAD] Upload area clicked, triggering file input');
                    fileInput.click();
                }
            });
            
            // File input change - no authentication required
            fileInput.addEventListener('change', function() {
                console.log('[UPLOAD] File input changed');
                if (this.files && this.files[0]) {
                    console.log('[UPLOAD] File selected:', this.files[0].name);
                    uploadFile(this.files[0]);
                }
            });
            
            // Drag and drop - no authentication required
            uploadArea.addEventListener('dragover', function(e) {
                e.preventDefault();
                e.stopPropagation();
                uploadArea.classList.add('dragover');
            });
            
            uploadArea.addEventListener('dragleave', function(e) {
                e.preventDefault();
                e.stopPropagation();
                uploadArea.classList.remove('dragover');
            });
            
            uploadArea.addEventListener('drop', function(e) {
                console.log('[UPLOAD] File dropped');
                e.preventDefault();
                e.stopPropagation();
                uploadArea.classList.remove('dragover');
                
                // No authentication required
                if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                    console.log('[UPLOAD] Dropped file:', e.dataTransfer.files[0].name);
                    uploadFile(e.dataTransfer.files[0]);
                }
            });
            console.log('[UPLOAD] Upload handlers initialized');
        }
        
        // Initialize upload handlers when DOM is ready
        function initializeUpload() {
            console.log('[UPLOAD] initializeUpload called, readyState:', document.readyState);
            if (document.readyState === 'loading') {
                console.log('[UPLOAD] DOM still loading, waiting for DOMContentLoaded');
                document.addEventListener('DOMContentLoaded', function() {
                    console.log('[UPLOAD] DOMContentLoaded fired, calling initUpload');
                    initUpload();
                });
            } else {
                // DOM is already loaded, initialize immediately
                console.log('[UPLOAD] DOM already loaded, calling initUpload immediately');
                initUpload();
            }
        }
        
        // Try multiple times to ensure it works
        initializeUpload();
        
        // Also try after delays as fallbacks
        setTimeout(function() {
            const uploadArea = document.getElementById('uploadArea');
            const fileInput = document.getElementById('fileInput');
            console.log('[UPLOAD] Fallback check (500ms): uploadArea=', !!uploadArea, 'fileInput=', !!fileInput);
            if (uploadArea && fileInput) {
                if (!uploadArea.hasAttribute('data-listener-attached')) {
                    console.log('[UPLOAD] Fallback: Re-initializing upload handlers');
                    uploadArea.setAttribute('data-listener-attached', 'true');
                    initUpload();
                } else {
                    console.log('[UPLOAD] Listeners already attached');
                }
            }
        }, 500);
        
        setTimeout(function() {
            const uploadArea = document.getElementById('uploadArea');
            const fileInput = document.getElementById('fileInput');
            console.log('[UPLOAD] Final check (2000ms): uploadArea=', !!uploadArea, 'fileInput=', !!fileInput);
            if (uploadArea && fileInput) {
                // Test if click works
                console.log('[UPLOAD] Testing click handler...');
                uploadArea.style.cursor = 'pointer';
                uploadArea.style.userSelect = 'none';
            }
        }, 2000);
        
        async function uploadFile(file) {
            devLog('[UPLOAD] uploadFile called');
            devLog('[UPLOAD] File:', file.name, 'Size:', file.size, 'Type:', file.type);
            
            // Check authentication first
            const isAuthenticated = await requireAuthForUpload();
            if (!isAuthenticated) {
                console.log('[UPLOAD] User not authenticated - showing login modal');
                // Store file for upload after login
                pendingFile = file;
                showLoginModal();
                return;
            }
            
            const uploadArea = document.getElementById('uploadArea');
            const uploadIcon = document.getElementById('uploadIcon');
            const uploadText = document.getElementById('uploadText');
            const uploadHint = document.getElementById('uploadHint');
            const uploadProgress = document.getElementById('uploadProgress');
            const progressFill = document.getElementById('progressFill');
            const progressText = document.getElementById('progressText');
            
            // Validate file type
            const fileName = file.name.toLowerCase();
            console.log('[UPLOAD] Validating file type:', fileName);
            if (!fileName.endsWith('.zip') && !fileName.endsWith('.json')) {
                console.log('[UPLOAD] Invalid file type');
                showUploadError('Please upload a ZIP file or conversations.json');
                return;
            }
            console.log('[UPLOAD] File type valid');
            
            // Helper to truncate filename from middle if > 40 chars
            function truncateFilename(name, maxLength = 40) {
                if (name.length <= maxLength) return name;
                const ext = name.lastIndexOf('.') > -1 ? name.slice(name.lastIndexOf('.')) : '';
                const nameWithoutExt = name.slice(0, name.length - ext.length);
                const charsToShow = maxLength - ext.length - 3; // 3 for '...'
                const frontChars = Math.ceil(charsToShow / 2);
                const backChars = Math.floor(charsToShow / 2);
                return nameWithoutExt.slice(0, frontChars) + '...' + nameWithoutExt.slice(-backChars) + ext;
            }
            
            // Show upload state
            uploadArea.classList.add('uploading');
            uploadArea.classList.remove('error', 'success');
            uploadIcon.textContent = '⏳';
            uploadText.textContent = 'Uploading ' + truncateFilename(file.name);
            uploadHint.textContent = 'Please wait...';
            uploadProgress.classList.remove('hidden');
            progressFill.style.width = '0%';
            progressText.textContent = 'Preparing upload...';
            
            // Use background job processing for all files
            const fileSize = file.size;
            devLog('[UPLOAD] File size: ' + (fileSize / 1024 / 1024).toFixed(2) + 'MB - using background processing');
            uploadFileWithBackgroundProcessing(file);
        }
        
        // Chunked upload for large files
        async function uploadFileChunked(file, chunkSize) {
            const fileId = Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            const totalChunks = Math.ceil(file.size / chunkSize);
            const uploadArea = document.getElementById('uploadArea');
            const progressFill = document.getElementById('progressFill');
            const progressText = document.getElementById('progressText');
            
            devLog('[UPLOAD] Starting chunked upload: ' + totalChunks + ' chunks');
            
            try {
                for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
                    const start = chunkIndex * chunkSize;
                    const end = Math.min(start + chunkSize, file.size);
                    const chunk = file.slice(start, end);
                    
                    const formData = new FormData();
                    formData.append('chunk', chunk);
                    formData.append('chunkIndex', chunkIndex);
                    formData.append('totalChunks', totalChunks);
                    formData.append('fileId', fileId);
                    formData.append('filename', file.name);
                    
                    // Update progress
                    const chunkProgress = Math.round(((chunkIndex + 1) / totalChunks) * 100);
                    progressFill.style.width = chunkProgress + '%';
                    progressText.textContent = `Uploading chunk ${chunkIndex + 1}/${totalChunks}...`;
                    
                    // Upload chunk
                    const response = await fetch('/upload-chunk', {
                        method: 'POST',
                        body: formData,
                        credentials: 'include' // Send cookies
                    });
                    
                    if (!response.ok) {
                        if (response.status === 401 || response.status === 403) {
                            pendingFile = file;
                            showLoginModal();
                            return;
                        }
                        const error = await response.json().catch(() => ({error: 'Upload failed'}));
                        throw new Error(error.error || 'Chunk upload failed');
                    }
                    
                    const result = await response.json();
                    devLog('[UPLOAD] Chunk response:', result);
                    
                    // If this was the last chunk, server will process the file
                    if (result.success && result.stats) {
                        // Upload complete and processed
                        uploadArea.classList.remove('uploading', 'error');
                        uploadArea.classList.add('success');
                        document.getElementById('uploadIcon').textContent = '✓';
                        document.getElementById('uploadText').textContent = 'Upload Successful!';
                        document.getElementById('uploadHint').textContent = result.message || 'Processing your conversations...';
                        progressText.textContent = 'Loading your conversations...';
                        progressFill.style.width = '100%';
                        
                        setTimeout(() => {
                            window.location.reload();
                        }, 1500);
                        return;
                    }
                    
                    // If last chunk uploaded, processing might take time
                    if (chunkIndex === totalChunks - 1) {
                        devLog('[UPLOAD] Last chunk uploaded, processing may take time for large files...');
                        progressText.textContent = 'Processing file... This may take a moment.';
                        
                        // Wait a bit for processing, then reload
                        // For very large files, processing might timeout on Vercel
                        // So we'll reload after a delay and hope processing completed
                        setTimeout(() => {
                            devLog('[UPLOAD] Reloading page after processing delay...');
                            window.location.reload();
                        }, 15000); // Wait 15 seconds for processing
                        return;
                    }
                }
            } catch (error) {
                devError('[UPLOAD] Chunked upload error:', error);
                showUploadError('Upload failed: ' + error.message);
            }
        }
        
        // Background job processing - upload file, then poll for status
        function uploadFileWithBackgroundProcessing(file) {
            const formData = new FormData();
            formData.append('file', file);
            
            const fileToUpload = file;
            const xhr = new XMLHttpRequest();
            const progressFill = document.getElementById('progressFill');
            const progressText = document.getElementById('progressText');
            
            // CRITICAL: Set withCredentials to send cookies/session with request
            xhr.withCredentials = true;
            
            // Track upload progress (0-50%, processing will be 50-100%)
            xhr.upload.addEventListener('progress', function(e) {
                if (e.lengthComputable) {
                    const uploadPercent = Math.round((e.loaded / e.total) * 50);
                    progressFill.style.width = uploadPercent + '%';
                    progressText.textContent = Math.round((e.loaded / e.total) * 100) + '% uploaded';
                }
            });
            
            xhr.addEventListener('load', function() {
                if (xhr.status === 200) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.success && response.job_id) {
                            devLog('[UPLOAD] File uploaded, job ID: ' + response.job_id);
                            progressText.textContent = 'Processing file...';
                            // Start polling for job status
                            pollJobStatus(response.job_id);
                        } else {
                            showUploadError(response.error || 'Upload failed');
                        }
                    } catch (e) {
                        devError('[UPLOAD] Failed to parse response:', e);
                        showUploadError('Invalid response from server: ' + e.message);
                    }
                } else if (xhr.status === 401 || xhr.status === 403) {
                    devLog('[UPLOAD] Authentication required (status: ' + xhr.status + ')');
                    document.getElementById('uploadArea').classList.remove('uploading');
                    pendingFile = fileToUpload;
                    showLoginModal();
                } else {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        showUploadError(response.error || 'Upload failed (status: ' + xhr.status + ')');
                    } catch (e) {
                        showUploadError('Upload failed: ' + xhr.statusText + ' (status: ' + xhr.status + ')');
                    }
                }
            });
            
            xhr.addEventListener('error', function() {
                devError('[UPLOAD] Network error during upload');
                showUploadError('Network error. Please check your connection and try again.');
            });
            
            xhr.open('POST', '/upload');
            progressText.textContent = 'Uploading file...';
            xhr.send(formData);
        }
        
        // Poll job status
        async function pollJobStatus(jobId) {
            const progressFill = document.getElementById('progressFill');
            const progressText = document.getElementById('progressText');
            const uploadArea = document.getElementById('uploadArea');
            let pollCount = 0;
            const maxPolls = 300; // 5 minutes max (300 * 1 second)
            
            const poll = async () => {
                try {
                    const response = await fetch(`/upload-status/${jobId}`, {
                        credentials: 'include'
                    });
                    
                    if (!response.ok) {
                        if (response.status === 401 || response.status === 403) {
                            showLoginModal();
                            return;
                        }
                        throw new Error('Status check failed: ' + response.status);
                    }
                    
                    const status = await response.json();
                    devLog('[UPLOAD] Job status:', status);
                    
                    // Update progress
                    const progress = status.progress || 0;
                    // Upload was 0-50%, so processing is 50-100%
                    const totalProgress = 50 + (progress / 2);
                    progressFill.style.width = totalProgress + '%';
                    progressText.textContent = status.message || `Processing... ${progress}%`;
                    
                    if (status.status === 'completed') {
                        // Success!
                        uploadArea.classList.remove('uploading', 'error');
                        uploadArea.classList.add('success');
                        document.getElementById('uploadIcon').textContent = '✓';
                        document.getElementById('uploadText').textContent = 'Upload Successful!';
                        document.getElementById('uploadHint').textContent = status.message || 'Processing your conversations...';
                        progressText.textContent = 'Loading your conversations...';
                        progressFill.style.width = '100%';
                        
                        setTimeout(() => {
                            window.location.reload();
                        }, 1500);
                        return;
                    } else if (status.status === 'error') {
                        showUploadError(status.error || 'Processing failed');
                        return;
                    } else if (status.status === 'processing' || status.status === 'queued') {
                        // Continue polling
                        pollCount++;
                        if (pollCount >= maxPolls) {
                            showUploadError('Processing is taking too long. Please try again or contact support.');
                            return;
                        }
                        setTimeout(poll, 1000); // Poll every second
                    }
                } catch (error) {
                    devError('[UPLOAD] Error polling job status:', error);
                    // Continue polling on error (might be temporary)
                    pollCount++;
                    if (pollCount < maxPolls) {
                        setTimeout(poll, 2000); // Wait 2 seconds on error
                    } else {
                        showUploadError('Failed to check processing status. Please refresh the page.');
                    }
                }
            };
            
            // Start polling
            poll();
        }
        
        function showUploadError(message) {
            console.error('[UPLOAD] showUploadError:', message);
            const uploadArea = document.getElementById('uploadArea');
            const uploadIcon = document.getElementById('uploadIcon');
            const uploadText = document.getElementById('uploadText');
            const uploadHint = document.getElementById('uploadHint');
            const uploadProgress = document.getElementById('uploadProgress');
            
            uploadArea.classList.remove('uploading');
            uploadArea.classList.add('error');
            uploadIcon.textContent = '⚠️';
            uploadText.textContent = 'Upload failed';
            uploadHint.innerHTML = message + '<br><br>Click to try again';
            uploadProgress.classList.add('hidden');
            
            // Reset after 5 seconds
            setTimeout(() => {
                console.log('[UPLOAD] Resetting upload area after error');
                uploadArea.classList.remove('error');
                uploadIcon.textContent = '📦';
                uploadText.textContent = 'Drop your ChatGPT export ZIP file here';
                uploadHint.textContent = 'Or click to browse • Accepts .zip or conversations.json';
            }, 5000);
        }
        
        function clearData() {
            devLog('[DATA] clearData called');
            if (confirm('Clear current data and upload a different file?')) {
                console.log('[DATA] User confirmed, clearing data...');
                fetch('/clear', { method: 'POST' })
                    .then(r => {
                        console.log('[DATA] /clear response status:', r.status);
                        if (!r.ok) {
                            throw new Error('Server returned ' + r.status);
                        }
                        return r.json();
                    })
                    .then(data => {
                        console.log('[DATA] /clear response:', data);
                        if (data.success) {
                            console.log('[DATA] Data cleared, reloading...');
                            window.location.reload();
                        } else {
                            alert('Failed to clear data: ' + (data.error || 'Unknown error'));
                        }
                    })
                    .catch(err => {
                        console.error('[DATA] Error clearing data:', err);
                        alert('Error clearing data: ' + err.message);
                    });
            }
        }
        
        // Tab switching
        function switchTab(tabName) {
            console.log('[UI] switchTab:', tabName);
            // Update tab buttons
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.tab === tabName);
            });
            
            // Update tab content
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(tabName + 'Tab').classList.add('active');
        }
        
        // View a specific project
        function viewProject(projectId, projectName) {
            console.log('[UI] viewProject:', projectId, projectName);
            // Switch to conversations tab
            switchTab('conversations');
            
            // Filter to this project
            document.querySelectorAll('.project-item').forEach(item => {
                item.classList.remove('active');
                if (item.dataset.filter === projectId) {
                    item.classList.add('active');
                }
            });
            
            document.getElementById('conversationsTitle').textContent = projectName;
            filterConversations(projectId);
        }
        
        // Project filter
        document.querySelectorAll('.project-item').forEach(item => {
            item.addEventListener('click', function() {
                document.querySelectorAll('.project-item').forEach(i => i.classList.remove('active'));
                this.classList.add('active');
                
                const filter = this.dataset.filter;
                const title = this.querySelector('.project-name').textContent.trim();
                document.getElementById('conversationsTitle').textContent = title.replace(/^[📚📁📄] /, '');
                
                filterConversations(filter);
            });
        });
        
        function filterConversations(filter) {
            console.log('[UI] filterConversations:', filter);
            const items = document.querySelectorAll('.conversation-item');
            let visibleCount = 0;
            items.forEach(item => {
                if (filter === 'all') {
                    item.style.display = '';
                    visibleCount++;
                } else if (filter === 'unassigned') {
                    const show = item.dataset.project === 'unassigned';
                    item.style.display = show ? '' : 'none';
                    if (show) visibleCount++;
                } else {
                    const show = item.dataset.project === filter;
                    item.style.display = show ? '' : 'none';
                    if (show) visibleCount++;
                }
            });
            console.log('[UI] Filter result:', visibleCount, 'visible conversations');
        }
        
        function searchConversations() {
            const query = document.getElementById('searchInput').value.toLowerCase();
            console.log('[SEARCH] searchConversations:', query);
            const items = document.querySelectorAll('.conversation-item');
            let matchCount = 0;
            
            items.forEach(item => {
                const title = item.querySelector('.conv-title').textContent.toLowerCase();
                const preview = item.querySelector('.conv-preview').textContent.toLowerCase();
                const matches = title.includes(query) || preview.includes(query);
                item.style.display = matches ? '' : 'none';
                if (matches) matchCount++;
            });
            console.log('[SEARCH] Found', matchCount, 'matches');
        }
        
        document.getElementById('searchInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') searchConversations();
        });
        
        function showConversation(id) {
            console.log('[CONV] showConversation:', id);
            fetch(`/conversation/${id}`)
                .then(r => {
                    console.log('[CONV] Response status:', r.status);
                    return r.json();
                })
                .then(data => {
                    console.log('[CONV] Loaded conversation:', data.title);
                    console.log('[CONV] Messages count:', data.messages ? data.messages.length : 0);
                    currentConversation = data;
                    currentMarkdown = data.markdown;
                    
                    document.getElementById('modalTitle').textContent = data.title;
                    
                    let subtitle = [];
                    if (data.project_name) subtitle.push(`Project: ${data.project_name}`);
                    if (data.create_time) subtitle.push(`Created: ${data.create_time}`);
                    if (data.model) subtitle.push(`Model: ${data.model}`);
                    document.getElementById('modalSubtitle').textContent = subtitle.join(' • ');
                    
                    let messagesHtml = '';
                    data.messages.forEach(msg => {
                        const roleClass = msg.role === 'user' ? 'user' : 'assistant';
                        const roleIcon = msg.role === 'user' ? '👤' : '🤖';
                        messagesHtml += `
                            <div class="message ${roleClass}">
                                <div class="message-header">${roleIcon} ${msg.role.charAt(0).toUpperCase() + msg.role.slice(1)}</div>
                                <div class="message-content">${escapeHtml(msg.content)}</div>
                            </div>
                        `;
                    });
                    
                    document.getElementById('modalBody').innerHTML = messagesHtml;
                    document.getElementById('modalOverlay').classList.add('active');
                })
                .catch(err => {
                    console.error('[CONV] Error loading conversation:', err);
                    showToast('Failed to load conversation');
                });
        }
        
        function closeModal(event) {
            console.log('[UI] closeModal called');
            if (!event || event.target === document.getElementById('modalOverlay')) {
                document.getElementById('modalOverlay').classList.remove('active');
            }
        }
        
        function copyToClipboard() {
            console.log('[UI] copyToClipboard, markdown length:', currentMarkdown ? currentMarkdown.length : 0);
            navigator.clipboard.writeText(currentMarkdown).then(() => {
                console.log('[UI] Copied to clipboard successfully');
                showToast('Copied to clipboard!');
            }).catch(err => {
                console.error('[UI] Copy to clipboard failed:', err);
                showToast('Failed to copy');
            });
        }
        
        function showToast(message) {
            console.log('[UI] showToast:', message);
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 2500);
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function exportAll() {
            console.log('[EXPORT] exportAll called');
            window.location.href = '/export-all';
        }
        
        // Keyboard shortcuts
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') closeModal();
        });
        
        // Smart Groups functionality
        let smartGroups = JSON.parse(localStorage.getItem('otc_smart_groups') || '[]');
        console.log('[SMART] Loaded', smartGroups.length, 'smart groups from localStorage');
        let allConversations = [];
        
        // Load conversation data
        document.addEventListener('DOMContentLoaded', function() {
            console.log('[INIT] DOMContentLoaded - loading conversation data');
            // Get all conversation items
            document.querySelectorAll('.conversation-item').forEach(item => {
                allConversations.push({
                    id: item.dataset.id,
                    title: item.querySelector('.conv-title').textContent,
                    project: item.dataset.project
                });
            });
            console.log('[INIT] Loaded', allConversations.length, 'conversations');
            
            renderSmartGroups();
            generateSuggestedGroups();
            initKeywordAutocomplete();
        });
        
        // Keyword autocomplete for Smart Groups
        function initKeywordAutocomplete() {
            const keywordInput = document.getElementById('groupKeywords');
            const dropdown = document.getElementById('keywordDropdown');
            if (!keywordInput || !dropdown) return;
            
            let timeout;
            
            keywordInput.addEventListener('input', function() {
                clearTimeout(timeout);
                const value = this.value;
                const lastKeyword = value.split(',').pop().trim().toLowerCase();
                
                if (lastKeyword.length < 2) {
                    dropdown.classList.remove('active');
                    return;
                }
                
                timeout = setTimeout(() => {
                    showKeywordSuggestions(lastKeyword, dropdown);
                }, 100);
            });
            
            keywordInput.addEventListener('focus', function() {
                const value = this.value;
                const lastKeyword = value.split(',').pop().trim().toLowerCase();
                if (lastKeyword.length >= 2) {
                    showKeywordSuggestions(lastKeyword, dropdown);
                }
            });
            
            document.addEventListener('click', function(e) {
                if (!e.target.closest('.autocomplete-wrapper')) {
                    dropdown.classList.remove('active');
                }
            });
            
            keywordInput.addEventListener('keydown', function(e) {
                if (e.key === 'Escape') {
                    dropdown.classList.remove('active');
                }
            });
        }
        
        function showKeywordSuggestions(query, dropdown) {
            // Find matching conversation titles
            const matches = allConversations.filter(conv => 
                conv.title.toLowerCase().includes(query)
            ).slice(0, 8);
            
            // Extract unique words from matching titles
            const wordMatches = new Map();
            matches.forEach(conv => {
                const words = conv.title.toLowerCase().split(/\s+/);
                words.forEach(word => {
                    word = word.replace(/[^a-z0-9]/g, '');
                    if (word.includes(query) && word.length > 2) {
                        if (!wordMatches.has(word)) {
                            wordMatches.set(word, conv.title);
                        }
                    }
                });
            });
            
            if (wordMatches.size === 0 && matches.length === 0) {
                dropdown.innerHTML = '<div style="padding: 0.75rem; color: var(--text-muted); font-size: 0.8125rem;">No matches found</div>';
            } else {
                let html = '';
                
                // Show word matches first
                wordMatches.forEach((title, word) => {
                    html += `
                        <div class="autocomplete-item" onclick="addKeyword('${word}')">
                            <div class="autocomplete-match">${word}</div>
                            <div class="autocomplete-title">from: ${title}</div>
                        </div>
                    `;
                });
                
                dropdown.innerHTML = html || '<div style="padding: 0.75rem; color: var(--text-muted); font-size: 0.8125rem;">No matches</div>';
            }
            
            dropdown.classList.add('active');
        }
        
        function addKeyword(word) {
            const input = document.getElementById('groupKeywords');
            const currentValue = input.value;
            const parts = currentValue.split(',').map(p => p.trim()).filter(p => p);
            
            // Remove the partial keyword being typed
            if (parts.length > 0) {
                parts.pop();
            }
            parts.push(word);
            
            input.value = parts.join(', ') + ', ';
            input.focus();
            document.getElementById('keywordDropdown').classList.remove('active');
        }
        
        function createSmartGroup() {
            console.log('[SMART] createSmartGroup called');
            const name = document.getElementById('groupName').value.trim();
            const keywords = document.getElementById('groupKeywords').value.trim();
            console.log('[SMART] Name:', name, 'Keywords:', keywords);
            
            if (!name || !keywords) {
                console.log('[SMART] Missing name or keywords');
                showToast('Please enter both name and keywords');
                return;
            }
            
            const keywordList = keywords.split(',').map(k => k.trim().toLowerCase()).filter(k => k);
            console.log('[SMART] Keyword list:', keywordList);
            
            const group = {
                id: 'smart_' + Date.now(),
                name: name,
                keywords: keywordList,
                icon: '📂'
            };
            
            smartGroups.push(group);
            localStorage.setItem('otc_smart_groups', JSON.stringify(smartGroups));
            console.log('[SMART] Group saved, total groups:', smartGroups.length);
            
            document.getElementById('groupName').value = '';
            document.getElementById('groupKeywords').value = '';
            
            renderSmartGroups();
            showToast(`Created group "${name}"`);
        }
        
        function renderSmartGroups() {
            console.log('[SMART] renderSmartGroups, groups count:', smartGroups.length);
            const container = document.getElementById('smartGroupsList');
            if (!container) {
                console.log('[SMART] Smart groups container not found (might be on landing page)');
                return;
            }
            container.innerHTML = '';
            
            smartGroups.forEach(group => {
                const matches = allConversations.filter(conv => 
                    group.keywords.some(kw => conv.title.toLowerCase().includes(kw))
                );
                console.log('[SMART] Group', group.name, 'has', matches.length, 'matches');
                
                const card = document.createElement('div');
                card.className = 'project-card';
                card.onclick = () => viewSmartGroup(group);
                card.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <div class="project-card-icon">${group.icon}</div>
                        <button onclick="event.stopPropagation(); deleteSmartGroup('${group.id}')" 
                            style="background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1.2rem;">✕</button>
                    </div>
                    <h3 class="project-card-title">${group.name}</h3>
                    <div class="project-card-stats">
                        <div class="project-card-stat">
                            <div class="project-card-stat-value">${matches.length}</div>
                            <div class="project-card-stat-label">Matches</div>
                        </div>
                    </div>
                    <div class="project-card-recent" style="color: var(--text-muted);">
                        Keywords: ${group.keywords.join(', ')}
                    </div>
                `;
                container.appendChild(card);
            });
            
            if (smartGroups.length === 0) {
                container.innerHTML = `
                    <div style="grid-column: 1 / -1; text-align: center; padding: 2rem; color: var(--text-muted);">
                        <p>No smart groups yet. Create one above!</p>
                        <p style="margin-top: 0.5rem; font-size: 0.9rem;">
                            Try creating groups like "Emails" with keywords "[company name], [project name], [client name], etc"
                        </p>
                    </div>
                `;
            }
        }
        
        function deleteSmartGroup(groupId) {
            console.log('[SMART] deleteSmartGroup:', groupId);
            smartGroups = smartGroups.filter(g => g.id !== groupId);
            localStorage.setItem('otc_smart_groups', JSON.stringify(smartGroups));
            renderSmartGroups();
            showToast('Group deleted');
        }
        
        function viewSmartGroup(group) {
            console.log('[SMART] viewSmartGroup:', group.name);
            switchTab('conversations');
            
            document.querySelectorAll('.project-item').forEach(item => item.classList.remove('active'));
            document.getElementById('conversationsTitle').textContent = group.name;
            
            // Filter conversations by keywords
            const items = document.querySelectorAll('.conversation-item');
            let matchCount = 0;
            items.forEach(item => {
                const title = item.querySelector('.conv-title').textContent.toLowerCase();
                const matches = group.keywords.some(kw => title.includes(kw));
                item.style.display = matches ? '' : 'none';
                if (matches) matchCount++;
            });
            console.log('[SMART] Showing', matchCount, 'conversations for group', group.name);
        }
        
        function generateSuggestedGroups() {
            const container = document.getElementById('suggestedGroups');
            
            // Analyze conversation titles to find common words
            const wordCounts = {};
            const stopWords = ['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'new', 'chat', 'help', 'how', 'what', 'why', 'when', 'where', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'make', 'made', 'get', 'got', 'this', 'that', 'these', 'those', 'my', 'your', 'his', 'her', 'its', 'our', 'their', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'us', 'them', 'using', 'code', 'app'];
            
            allConversations.forEach(conv => {
                const words = conv.title.toLowerCase().split(/\\s+/);
                words.forEach(word => {
                    word = word.replace(/[^a-z0-9]/g, '');
                    if (word.length > 3 && !stopWords.includes(word)) {
                        wordCounts[word] = (wordCounts[word] || 0) + 1;
                    }
                });
            });
            
            // Get top keywords that appear in multiple conversations
            const suggestions = Object.entries(wordCounts)
                .filter(([word, count]) => count >= 3)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 8);
            
            if (suggestions.length === 0) {
                container.innerHTML = '<p style="color: var(--text-muted); grid-column: 1 / -1;">No suggestions available yet.</p>';
                return;
            }
            
            container.innerHTML = suggestions.map(([word, count]) => `
                <div class="project-card" onclick="suggestGroup('${word}')" style="cursor: pointer;">
                    <div class="project-card-icon">💡</div>
                    <h3 class="project-card-title" style="text-transform: capitalize;">${word}</h3>
                    <div class="project-card-stats">
                        <div class="project-card-stat">
                            <div class="project-card-stat-value">${count}</div>
                            <div class="project-card-stat-label">Matches</div>
                        </div>
                    </div>
                    <div class="project-card-recent">Click to create group</div>
                </div>
            `).join('');
        }
        
        function suggestGroup(keyword) {
            document.getElementById('groupName').value = keyword.charAt(0).toUpperCase() + keyword.slice(1);
            document.getElementById('groupKeywords').value = keyword;
            document.getElementById('groupName').focus();
            showToast('Edit the group name and keywords, then click Create');
        }
        
    </script>
    
    <!-- Site Footer -->
    <footer class="site-footer">
        Created by <a href="https://x.com/thatproduktguy" target="_blank" rel="noopener noreferrer" id="twitterLink">@Harsh</a>
    </footer>
    
    <!-- Twitter Preview Card -->
    <div class="twitter-preview-card" id="twitterPreviewCard">
        <div class="twitter-preview-header">
            <img src="/static/images/Profile.jpg" alt="Harsh" class="twitter-preview-avatar">
            <div class="twitter-preview-names">
                <div class="twitter-preview-name">Harsh Kothari</div>
                <div class="twitter-preview-handle">@thatproduktguy</div>
            </div>
        </div>
        <div class="twitter-preview-bio">
            building things.<br>
            thinking about decisions, not features.<br><br>
            Sr Product Designer <a href="https://x.com/browserstack" style="color: var(--accent); text-decoration: none;">@BrowserStack</a><br>
            building <a href="https://x.com/getfrim" style="color: var(--accent); text-decoration: none;">@getfrim</a>
        </div>
        <a href="https://x.com/thatproduktguy" target="_blank" rel="noopener noreferrer" class="twitter-follow-btn">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"></path></svg>
            Follow on X
        </a>
    </div>
    
    <script>
        // Twitter preview card hover effect
        (function() {
            const twitterLink = document.getElementById('twitterLink');
            const previewCard = document.getElementById('twitterPreviewCard');
            
            if (twitterLink && previewCard) {
                let isHovering = false;
                
                twitterLink.addEventListener('mouseenter', () => {
                    isHovering = true;
                    setTimeout(() => {
                        if (isHovering) {
                            previewCard.classList.add('visible');
                        }
                    }, 200);
                });
                
                twitterLink.addEventListener('mouseleave', () => {
                    isHovering = false;
                    previewCard.classList.remove('visible');
                });
                
                twitterLink.addEventListener('mousemove', (e) => {
                    const offsetX = 15;
                    const offsetY = 15;
                    const cardWidth = 280;
                    const cardHeight = 180;
                    
                    let x = e.clientX + offsetX;
                    let y = e.clientY + offsetY;
                    
                    // Keep card within viewport
                    if (x + cardWidth > window.innerWidth) {
                        x = e.clientX - cardWidth - offsetX;
                    }
                    if (y + cardHeight > window.innerHeight) {
                        y = e.clientY - cardHeight - offsetX;
                    }
                    
                    previewCard.style.left = x + 'px';
                    previewCard.style.top = y + 'px';
                });
            }
        })();
    </script>
    
    <!-- Login Modal - isolated from file processing -->
    <div id="loginModalOverlay" class="modal-overlay">
        <div class="modal" style="max-width: 400px;">
            <div class="modal-header">
                <div>
                    <h3 class="modal-title">Sign In Required</h3>
                    <p class="modal-subtitle">Sign in with Google to continue</p>
                </div>
            </div>
            <div class="modal-body" style="text-align: center; padding: 2rem;">
                <button onclick="signInWithGoogle()" class="modal-btn copy" style="width: 100%; padding: 0.75rem; font-size: 0.875rem; display: flex; align-items: center; justify-content: center; gap: 0.5rem;">
                    <svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
                        <g fill="none" fill-rule="evenodd">
                            <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z" fill="#4285F4"/>
                            <path d="M9 18c2.43 0 4.467-.806 5.96-2.184l-2.908-2.258c-.806.54-1.837.86-3.052.86-2.347 0-4.33-1.585-5.04-3.714H.957v2.332C2.438 15.983 5.482 18 9 18z" fill="#34A853"/>
                            <path d="M3.96 10.704c-.18-.54-.282-1.117-.282-1.704s.102-1.164.282-1.704V4.964H.957C.347 6.174 0 7.548 0 9s.348 2.826.957 4.036l3.003-2.332z" fill="#FBBC05"/>
                            <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.964L3.96 7.296C4.67 5.167 6.653 3.58 9 3.58z" fill="#EA4335"/>
                        </g>
                    </svg>
                    Sign in with Google
                </button>
                <p style="margin-top: 1rem; font-size: 0.75rem; color: var(--text-muted);">
                    Your data stays private. We only track usage for analytics.
                </p>
            </div>
        </div>
    </div>
    
    <!-- Firebase Authentication Script - ISOLATED from file processing -->
    <script>
        // Production mode check
        const IS_PRODUCTION = {{ 'true' if IS_PRODUCTION else 'false' }};
        
        // Console logging wrapper - only log in development
        const devLog = IS_PRODUCTION ? () => {} : console.log.bind(console);
        const devError = console.error.bind(console); // Always log errors
        
        // Firebase Authentication - ISOLATED from file processing
        let firebaseApp = null;
        let currentUser = null;
        // Store pending file for upload after login
        let pendingFile = null;

        // Initialize Firebase - ONLY for auth
        async function initFirebase() {
            try {
                devLog('[FIREBASE] Initializing Firebase...');
                devLog('[FIREBASE] Firebase SDK available:', typeof firebase !== 'undefined');
                
                const response = await fetch('/api/firebase-config');
                const data = await response.json();
                
                devLog('[FIREBASE] Config response:', data);
                
                // Check if Firebase is configured
                if (data.configured === false || !data.apiKey) {
                    devLog('[FIREBASE] Firebase not configured - allowing access without authentication');
                    // Still check auth status in case there's a session
                    await checkAuthStatus();
                    return;
                }
                
                // Firebase is configured - initialize it
                if (data.apiKey && typeof firebase !== 'undefined') {
                    try {
                        // Check if Firebase is already initialized
                        if (firebase.apps.length > 0) {
                            devLog('[FIREBASE] Firebase already initialized, using existing app');
                            firebaseApp = firebase.app();
                        } else {
                            devLog('[FIREBASE] Initializing Firebase with config...');
                            firebaseApp = firebase.initializeApp(data);
                            devLog('[FIREBASE] Firebase initialized successfully');
                        }
                        await checkAuthStatus();
                    } catch (initError) {
                        devError('[FIREBASE] Error initializing Firebase:', initError);
                        if (initError.code === 'app/duplicate-app') {
                            devLog('[FIREBASE] Firebase app already exists, using it');
                            firebaseApp = firebase.app();
                            await checkAuthStatus();
                        } else {
                            throw initError;
                        }
                    }
                } else {
                    devError('[FIREBASE] Firebase SDK not loaded or no API key');
                    if (typeof firebase === 'undefined') {
                        devError('[FIREBASE] Firebase SDK scripts not loaded! Check if scripts are in HTML.');
                    } else if (!data.apiKey) {
                        devError('[FIREBASE] No API key in config:', data);
                    }
                    await checkAuthStatus();
                }
            } catch (e) {
                devError('[FIREBASE] Firebase init error:', e);
                devError('[FIREBASE] Error details:', e.message, e.stack);
                // Even on error, check auth status
                await checkAuthStatus();
            }
        }

        // Check authentication - NO Firebase dependency after initial check
        async function checkAuthStatus() {
            try {
                const response = await fetch('/auth/status');
                const data = await response.json();
                
                // If Firebase is not configured, don't show login modal
                if (data.firebase_configured === false) {
                    console.log('Firebase not configured - allowing access without authentication');
                    return; // Don't show login modal, allow access
                }
                
                // Firebase is configured - check if authenticated
                if (data.authenticated) {
                    currentUser = data.user;
                    updateUserUI(data.user);
                    
                    // If there's a pending file, upload it now
                    if (pendingFile) {
                        const file = pendingFile;
                        pendingFile = null;
                        uploadFile(file);
                    }
                }
                // Don't show login modal automatically - only when user tries to upload
            } catch (e) {
                console.error('Error checking auth status:', e);
                // On error, if we can't determine status, don't block access
            }
        }
        
        // Check if user is authenticated (for upload)
        async function requireAuthForUpload() {
            try {
                const response = await fetch('/auth/status');
                const data = await response.json();
                
                console.log('[AUTH] Auth status check:', data);
                
                // If Firebase not configured, allow upload (development mode)
                if (data.firebase_configured === false) {
                    console.log('[AUTH] Firebase not configured - allowing upload without authentication');
                    return true;
                }
                
                // If authenticated, allow upload
                if (data.authenticated) {
                    console.log('[AUTH] User authenticated - allowing upload');
                    return true;
                }
                
                // Not authenticated - return false
                console.log('[AUTH] User not authenticated - blocking upload');
                return false;
            } catch (e) {
                console.error('[AUTH] Error checking auth status:', e);
                // On error, if Firebase is configured, block access
                // If not configured, allow access
                return true; // Default to allowing for development
            }
        }

        // Show login modal
        function showLoginModal() {
            devLog('[AUTH] showLoginModal called');
            const modal = document.getElementById('loginModalOverlay');
            devLog('[AUTH] Modal element:', modal);
            if (modal) {
                modal.classList.add('active');
                devLog('[AUTH] Login modal shown');
            } else {
                devError('[AUTH] Login modal element not found!');
            }
        }

        // Close login modal
        function closeLoginModal(event) {
            console.log('[AUTH] closeLoginModal called');
            if (!event || event.target === document.getElementById('loginModalOverlay')) {
                document.getElementById('loginModalOverlay').classList.remove('active');
            }
        }

        // Convert technical Firebase errors to user-friendly messages
        function getUserFriendlyError(error) {
            if (!error) return 'Something went wrong. Please try again.';
            
            const errorCode = error.code || '';
            const errorMessage = error.message || String(error);
            
            // Map Firebase error codes to friendly messages
            const errorMap = {
                'auth/internal-error': 'There was a problem with the sign-in service. Please try again in a moment.',
                'auth/network-request-failed': 'Network error. Please check your internet connection and try again.',
                'auth/popup-closed-by-user': 'Sign-in was cancelled. Please try again if you want to continue.',
                'auth/popup-blocked': 'The sign-in popup was blocked. Please allow popups for this site and try again.',
                'auth/cancelled-popup-request': 'Another sign-in attempt is already in progress. Please wait.',
                'auth/unauthorized-domain': 'This domain is not authorized. Please contact support.',
                'auth/invalid-api-key': 'Configuration error. Please contact support.',
                'auth/operation-not-allowed': 'Sign-in method is not enabled. Please contact support.',
                'auth/too-many-requests': 'Too many sign-in attempts. Please wait a few minutes and try again.',
                'auth/user-disabled': 'This account has been disabled. Please contact support.',
                'auth/user-not-found': 'Account not found. Please try a different account.',
                'auth/wrong-password': 'Incorrect password. Please try again.',
                'auth/email-already-in-use': 'This email is already in use. Please try a different account.',
                'auth/weak-password': 'Password is too weak. Please use a stronger password.',
                'auth/invalid-email': 'Invalid email address. Please check and try again.',
                'auth/account-exists-with-different-credential': 'An account with this email already exists. Please use a different sign-in method.'
            };
            
            // Check if we have a mapped message
            if (errorCode && errorMap[errorCode]) {
                return errorMap[errorCode];
            }
            
            // For production, show generic message; for development, show actual error
            if (IS_PRODUCTION) {
                // In production, hide technical details
                if (errorCode && errorCode.startsWith('auth/')) {
                    return 'Sign-in failed. Please try again or contact support if the problem persists.';
                }
                return 'Something went wrong. Please try again.';
            } else {
                // In development, show the actual error for debugging
                return errorMessage;
            }
        }

        // Google Sign-In - ONLY uses Firebase for popup, then sends token to backend
        async function signInWithGoogle() {
            devLog('[AUTH] signInWithGoogle called, firebaseApp:', firebaseApp);
            devLog('[AUTH] Firebase SDK available:', typeof firebase !== 'undefined');
            
            // Check if Firebase SDK is loaded
            if (typeof firebase === 'undefined') {
                alert('Unable to load sign-in service. Please refresh the page and try again.');
                console.error('[AUTH] Firebase SDK not available');
                return;
            }
            
            // Try to initialize Firebase if not already initialized
            if (!firebaseApp) {
                console.log('[AUTH] Firebase not initialized, attempting to initialize...');
                try {
                    await initFirebase();
                } catch (initError) {
                    console.error('[AUTH] Error during Firebase initialization:', initError);
                }
                
                // Check again after initialization attempt
                if (!firebaseApp) {
                    // Try to get existing Firebase app
                    try {
                        if (firebase.apps && firebase.apps.length > 0) {
                            console.log('[AUTH] Found existing Firebase app');
                            firebaseApp = firebase.app();
                        }
                    } catch (e) {
                        console.error('[AUTH] Error getting Firebase app:', e);
                    }
                    
                    // If still not initialized, check backend status
                    if (!firebaseApp) {
                        try {
                            const statusResponse = await fetch('/auth/status');
                            const statusData = await statusResponse.json();
                            
                            if (statusData.firebase_configured === false) {
                                alert('Authentication is not configured. The app is running in development mode without authentication.');
                                document.getElementById('loginModalOverlay').classList.remove('active');
                                return;
                            }
                        } catch (e) {
                            console.error('Error checking Firebase status:', e);
                        }
                        
                        // Get config and try manual initialization
                        try {
                            const configResponse = await fetch('/api/firebase-config');
                            const configData = await configResponse.json();
                            console.log('[AUTH] Config for manual init:', configData);
                            
                            // Check if config has apiKey (not null/undefined)
                            if (configData.apiKey && configData.apiKey !== null && configData.apiKey !== 'null') {
                                console.log('[AUTH] Attempting manual Firebase initialization...');
                                // Remove any error/status fields before initializing
                                const cleanConfig = {
                                    apiKey: configData.apiKey,
                                    authDomain: configData.authDomain,
                                    projectId: configData.projectId,
                                    storageBucket: configData.storageBucket,
                                    messagingSenderId: configData.messagingSenderId,
                                    appId: configData.appId
                                };
                                firebaseApp = firebase.initializeApp(cleanConfig);
                                devLog('[AUTH] Manual initialization successful');
                            } else {
                                devError('[AUTH] No valid API key in config:', configData);
                                throw new Error('No API key in config. Please set FIREBASE_WEB_CONFIG environment variable and restart the app.');
                            }
                        } catch (manualInitError) {
                            console.error('[AUTH] Manual initialization failed:', manualInitError);
                            alert('Firebase initialization failed. Please restart the Flask app with FIREBASE_WEB_CONFIG set. Error: ' + manualInitError.message);
                            return;
                        }
                    }
                }
            }
            
            // Final check - verify Firebase is ready
            if (!firebaseApp || typeof firebase === 'undefined' || !firebase.auth) {
                console.error('[AUTH] Firebase not ready:', {
                    firebaseApp: !!firebaseApp,
                    firebaseSDK: typeof firebase !== 'undefined',
                    firebaseAuth: typeof firebase !== 'undefined' && !!firebase.auth
                });
                alert('Firebase authentication is not ready. Please refresh the page and try again.');
                return;
            }
            
            console.log('[AUTH] Starting Google Sign-In...');
            const provider = new firebase.auth.GoogleAuthProvider();
            try {
                const result = await firebase.auth().signInWithPopup(provider);
                console.log('[AUTH] Sign-in successful, getting ID token...');
                const idToken = await result.user.getIdToken();
                console.log('[AUTH] ID token obtained, sending to backend...');
                
                // Send token to backend - backend verifies and creates session
                const response = await fetch('/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ idToken: idToken })
                });
                
                const data = await response.json();
                if (data.success) {
                    currentUser = data.user;
                    updateUserUI(data.user);
                    document.getElementById('loginModalOverlay').classList.remove('active');
                    
                    // Check if there's a pending file to upload
                    if (pendingFile) {
                        const file = pendingFile;
                        pendingFile = null;
                        // Small delay to ensure UI is updated
                        setTimeout(() => {
                            uploadFile(file);
                        }, 300);
                    } else {
                        // No pending file, just reload
                        window.location.reload();
                    }
                } else {
                    const friendlyError = getUserFriendlyError({ message: data.error || 'Unknown error' });
                    alert('Sign-in failed: ' + friendlyError);
                }
            } catch (error) {
                console.error('Sign-in error:', error);
                const friendlyError = getUserFriendlyError(error);
                alert('Sign-in failed: ' + friendlyError);
            }
        }

        // Update UI - NO Firebase dependency
        function updateUserUI(user) {
            const headerActions = document.getElementById('headerActions');
            if (headerActions && user) {
                const avatarHtml = user.photoURL ? 
                    `<img src="${user.photoURL}" alt="${user.name}" class="user-avatar" onerror="this.style.display='none'">` : '';
                headerActions.innerHTML = `
                    <div class="user-info">
                        ${avatarHtml}
                        <span>${user.name || user.email}</span>
                        <button onclick="signOut()" class="logout-btn">Logout</button>
                    </div>
                    <button onclick="clearData()" class="header-action-btn">
                        ↻ Load Different Data
                    </button>
                `;
            }
        }

        // Sign out - NO Firebase dependency after initial signout
        async function signOut() {
            if (firebaseApp) {
                await firebase.auth().signOut();
            }
            
            await fetch('/logout', { method: 'POST' });
            currentUser = null;
            window.location.reload();
        }

        // Wait for Firebase SDK to load, then initialize
        let firebaseWaitTimeout = null;
        let firebaseWaitStart = Date.now();
        const FIREBASE_MAX_WAIT = 5000; // 5 seconds max wait
        
        function waitForFirebase() {
            if (typeof firebase !== 'undefined') {
                devLog('[FIREBASE] Firebase SDK loaded, initializing...');
                if (firebaseWaitTimeout) clearTimeout(firebaseWaitTimeout);
                initFirebase().catch(err => {
                    console.error('[FIREBASE] Initialization error:', err);
                    // Show page even if Firebase fails
                    document.body.style.display = 'block';
                });
            } else {
                const elapsed = Date.now() - firebaseWaitStart;
                if (elapsed > FIREBASE_MAX_WAIT) {
                    console.warn('[FIREBASE] Firebase SDK did not load within timeout, showing page anyway');
                    document.body.style.display = 'block';
                    // Try to check auth status without Firebase
                    checkAuthStatus().catch(err => {
                        console.error('[AUTH] Error checking auth status:', err);
                    });
                    return;
                }
                devLog('[FIREBASE] Waiting for Firebase SDK to load...');
                firebaseWaitTimeout = setTimeout(waitForFirebase, 100);
            }
        }
        
        // Global error handler to prevent white screen
        window.addEventListener('error', function(e) {
            console.error('[GLOBAL ERROR]', e.error, e.message, e.filename, e.lineno);
            // Ensure page is visible even if there's an error
            document.body.style.display = 'block';
            document.body.style.visibility = 'visible';
        });
        
        // Initialize on page load with error handling
        try {
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', function() {
                    try {
                        waitForFirebase();
                    } catch (e) {
                        console.error('[INIT ERROR]', e);
                        // Show page even if initialization fails
                        document.body.style.display = 'block';
                    }
                });
            } else {
                try {
                    waitForFirebase();
                } catch (e) {
                    console.error('[INIT ERROR]', e);
                    document.body.style.display = 'block';
                }
            }
        } catch (e) {
            console.error('[CRITICAL INIT ERROR]', e);
            // Ensure page is visible
            document.body.style.display = 'block';
            document.body.style.visibility = 'visible';
        }
    </script>
</body>
</html>
"""




def get_parser_from_session():
    """Helper function to load parser from file-based storage with expiration check"""
    global parser
    storage_file = session.get('conversations_file', None)
    expires_at = session.get('conversations_expires_at', 0)
    
    # Check expiration from session
    if expires_at > 0 and time.time() > expires_at:
        logger.info("Session data expired, clearing")
        if storage_file and os.path.exists(storage_file):
            try:
                os.remove(storage_file)
            except:
                pass
        session.pop('conversations_file', None)
        session.pop('conversations_expires_at', None)
        return None
    
    logger.info(f"get_parser_from_session - storage_file: {storage_file}")
    
    # Load from file storage
    if storage_file:
        if os.path.exists(storage_file):
            # Check file age (double-check expiration)
            file_age = time.time() - os.path.getmtime(storage_file)
            if file_age > EPHEMERAL_TTL:
                logger.info(f"File expired (age: {file_age}s), removing")
                try:
                    os.remove(storage_file)
                except:
                    pass
                session.pop('conversations_file', None)
                session.pop('conversations_expires_at', None)
                return None
            
            try:
                logger.info(f"Loading conversations from file: {storage_file}")
                with open(storage_file, 'r', encoding='utf-8') as f:
                    conversations_data = json.load(f)
                
                logger.info(f"Loaded {len(conversations_data) if isinstance(conversations_data, list) else 'unknown'} conversations from file")
                parser = ChatGPTParser()
                parser.parse_from_json(conversations_data)
                logger.info(f"Parser initialized with {len(parser.conversations)} conversations")
                return parser
            except Exception as e:
                logger.exception(f"Error loading parser from file {storage_file}: {e}")
                parser = None
                # Clean up invalid file
                try:
                    if os.path.exists(storage_file):
                        os.remove(storage_file)
                except:
                    pass
                session.pop('conversations_file', None)
                session.pop('conversations_expires_at', None)
        else:
            logger.warning(f"Storage file not found: {storage_file}")
            # File doesn't exist - clear from session
            session.pop('conversations_file', None)
            session.pop('conversations_expires_at', None)
    
    # Fallback: try old session-based storage (for backwards compatibility)
    conversations_data = session.get('conversations_data', None)
    if conversations_data:
        try:
            parser = ChatGPTParser()
            parser.parse_from_json(conversations_data)
            # Migrate to file storage
            session_id = session.get('_id', secrets.token_hex(16))
            file_id = hashlib.md5(f"{session_id}_{time.time()}".encode()).hexdigest()
            storage_file = os.path.join(STORAGE_DIR, f'{session_id}_conv_{file_id}.json')  # Add session prefix
            expires_at = time.time() + EPHEMERAL_TTL
            with open(storage_file, 'w', encoding='utf-8') as f:
                json.dump(conversations_data, f)
            session['conversations_file'] = storage_file
            session['conversations_expires_at'] = expires_at  # Add expiration
            session.pop('conversations_data', None)  # Remove from session
            logger.info("Migrated session data to file storage")
            return parser
        except Exception as e:
            logger.error(f"Error loading parser from session: {e}")
            parser = None
            session.pop('conversations_data', None)
    
    return None


@app.route('/')
def index():
    try:
        global parser
        
        # Log session info for debugging
        storage_file = session.get('conversations_file', None)
        logger.info(f"Index route - Session ID: {session.get('_id', 'no-id')}")
        logger.info(f"Index route - conversations_file in session: {storage_file}")
        if storage_file:
            logger.info(f"Index route - File exists: {os.path.exists(storage_file)}")
        
        # Load parser from session if available
        parser = get_parser_from_session()
        
        if parser:
            stats = parser.get_stats()
            logger.info(f"Index route - Loaded {stats['total_conversations']} conversations")
            return render_template_string(
                HTML_TEMPLATE,
                parser=parser,
                stats=stats,
                projects=list(parser.projects.values()),
                conversations=parser.conversations,
                unassigned_count=len(parser.unassigned_conversations),
                IS_PRODUCTION=IS_PRODUCTION
            )
        
        logger.info("Index route - No parser loaded, showing empty state")
        return render_template_string(
            HTML_TEMPLATE, 
            parser=None,
            IS_PRODUCTION=IS_PRODUCTION
        )
    except Exception as e:
        logger.exception(f"Error in index route: {e}")
        return f"<html><body><h1>Error</h1><p>{str(e)}</p><pre>{traceback.format_exc()}</pre></body></html>", 500


@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files from the app directory"""
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    static_path = os.path.join(base_dir, 'static', filename)
    
    # Security: prevent directory traversal
    if not os.path.abspath(static_path).startswith(os.path.abspath(os.path.join(base_dir, 'static'))):
        return "Forbidden", 403
    
    if not os.path.exists(static_path):
        return "Not Found", 404
    
    return send_file(static_path)


@app.route('/login', methods=['POST'])
def login():
    """Google Sign-In endpoint - ONLY uses Firebase for token verification"""
    if not FIREBASE_AUTH_ENABLED:
        return jsonify({"error": "Authentication not configured"}), 503
    
    data = request.get_json()
    id_token = data.get('idToken')
    
    if not id_token:
        return jsonify({"error": "ID token required"}), 400
    
    try:
        # ONLY Firebase call - verify token, then done with Firebase
        decoded_token = auth.verify_id_token(id_token)
        user_id = decoded_token['uid']
        user_email = decoded_token.get('email', 'unknown')
        user_name = decoded_token.get('name', '')
        user_photo = decoded_token.get('picture', '')
        
        # Log usage - NO Firebase dependency
        log_user_usage(user_email, user_id, action='login')
        
        # Store in session - NO Firebase dependency
        session['user_id'] = user_id
        session['user_email'] = user_email
        session['user_name'] = user_name
        session['user_photo'] = user_photo
        session.permanent = True
        session.modified = True  # Explicitly mark as modified to ensure Flask saves it
        
        logger.info(f"User logged in: {user_email}")
        
        return jsonify({
            "success": True,
            "user": {
                "email": user_email,
                "name": user_name,
                "uid": user_id,
                "photoURL": user_photo
            }
        })
    except Exception as e:
        logger.error(f"Login error: {e}")
        # Return user-friendly error message
        error_msg = str(e)
        if IS_PRODUCTION:
            # In production, don't expose technical details
            if "invalid" in error_msg.lower() or "token" in error_msg.lower():
                error_msg = "Sign-in failed. Please try again."
            elif "network" in error_msg.lower() or "timeout" in error_msg.lower():
                error_msg = "Network error. Please check your connection and try again."
            else:
                error_msg = "Sign-in failed. Please try again or contact support."
        return jsonify({"error": error_msg}), 401


@app.route('/logout', methods=['POST'])
def logout():
    """Logout - NO Firebase dependency"""
    user_email = session.get('user_email', 'unknown')
    user_id = session.get('user_id', 'unknown')
    
    if user_id != 'unknown':
        log_user_usage(user_email, user_id, action='logout')
    
    session.clear()
    logger.info(f"User logged out: {user_email}")
    return jsonify({"success": True})


@app.route('/auth/status')
def auth_status():
    """Check auth status - NO Firebase dependency, just session check"""
    # Return firebase_configured based on backend config, not frontend web config
    # The backend can require auth even if frontend web config isn't set yet
    firebase_configured = FIREBASE_AUTH_ENABLED
    
    if not firebase_configured:
        return jsonify({
            "authenticated": False,
            "user": None,
            "firebase_configured": False
        })
    
    user_id = session.get('user_id')
    if user_id:
        return jsonify({
            "authenticated": True,
            "user": {
                "email": session.get('user_email'),
                "name": session.get('user_name'),
                "uid": user_id,
                "photoURL": session.get('user_photo', '')
            }
        })
    else:
        return jsonify({
            "authenticated": False,
            "user": None
        })


@app.route('/api/firebase-config')
def get_firebase_config():
    """Return Firebase web config - ONLY for frontend auth, not used elsewhere"""
    web_config = os.environ.get('FIREBASE_WEB_CONFIG')
    
    # Fallback: try to read from firebase-web-config.json file
    if not web_config:
        project_dir = os.path.dirname(os.path.abspath(__file__))
        # Support both legacy location (project root) and new organised location (config/)
        candidate_paths = [
            os.path.join(project_dir, 'firebase-web-config.json'),
            os.path.join(project_dir, 'config', 'firebase-web-config.json'),
        ]
        for web_config_file in candidate_paths:
        if os.path.exists(web_config_file):
            try:
                with open(web_config_file, 'r') as f:
                    web_config_data = json.load(f)
                    # Convert dict to JSON string for consistency
                    web_config = json.dumps(web_config_data)
                    logger.info(f"Loaded Firebase web config from file: {web_config_file}")
                    break
            except Exception as e:
                    logger.error(f"Error reading firebase-web-config.json from {web_config_file}: {e}")
    
    logger.info(f"FIREBASE_WEB_CONFIG in environment: {'SET' if web_config else 'NOT SET'}")
    
    if web_config:
        try:
            config = json.loads(web_config)
            logger.info(f"Firebase web config loaded successfully, has apiKey: {'apiKey' in config and bool(config.get('apiKey'))}")
            return jsonify(config)
        except Exception as e:
            logger.error(f"Error parsing FIREBASE_WEB_CONFIG: {e}")
            return jsonify({"error": "Invalid config", "details": str(e)}), 500
    
    # If backend has Firebase configured but web config not set, return error
    if FIREBASE_AUTH_ENABLED:
        logger.warning("FIREBASE_WEB_CONFIG not set but backend is configured")
        return jsonify({
            "configured": False,
            "apiKey": None,
            "error": "FIREBASE_WEB_CONFIG not set. Please set it to enable Google Sign-In.",
            "backend_configured": True
        }), 200
    
    # Return 200 with configured: false instead of 404 to avoid console errors
    return jsonify({"configured": False, "error": "Firebase not configured"}), 200

@app.route("/upload-url", methods=["POST"])
def get_upload_url():
    """Generate signed URL for direct upload to Google Cloud Storage"""
    db = firestore.Client()
    storage_client = gcs_storage.Client()

    file_name = request.json.get("fileName")
    content_type = request.json.get("contentType", "application/zip")

    job_id = str(uuid.uuid4())

    # Create Firestore job doc
    job_ref = db.collection("jobs").document(job_id)
    job_ref.set({
        "status": "pending",
        "progress": 0,
        "message": "Upload not started",
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    })

    # GCS path: uploads/{job_id}/{file_name}
    bucket = storage_client.bucket(os.environ.get("UPLOAD_BUCKET", "transfercc-589f7-uploads"))
    blob = bucket.blob(f"uploads/{job_id}/{file_name}")

    upload_url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(hours=1),
        method="PUT",
        content_type=content_type,
    )

    return jsonify({
        "jobId": job_id,
        "uploadUrl": upload_url,
        "bucketPath": blob.name,
    })


@app.route('/process-upload', methods=['POST'])
@login_required
def process_upload():
    """Process upload endpoint - Firebase Storage not available, use direct upload"""
    return jsonify({"error": "Firebase not configured", "useDirectUpload": True}), 400


@app.route('/upload-chunk', methods=['POST'])
@login_required
def upload_chunk():
    """Handle chunked file upload - for files > 4.5MB (Vercel limit)"""
    try:
        chunk = request.files.get('chunk')
        chunk_index = int(request.form.get('chunkIndex', 0))
        total_chunks = int(request.form.get('totalChunks', 1))
        file_id = request.form.get('fileId')
        filename = request.form.get('filename', 'upload')
        
        if not chunk or not file_id:
            return jsonify({"error": "Missing chunk or fileId"}), 400
        
        # Store chunk in temp directory
        session_id = session.get('_id', secrets.token_hex(16))
        chunks_dir = os.path.join(STORAGE_DIR, 'chunks', file_id)
        os.makedirs(chunks_dir, exist_ok=True)
        
        chunk_path = os.path.join(chunks_dir, f'chunk_{chunk_index}')
        chunk.save(chunk_path)
        
        logger.info(f"Received chunk {chunk_index + 1}/{total_chunks} for file {file_id}")
        
        # Check if all chunks received
        received_chunks = len([f for f in os.listdir(chunks_dir) if f.startswith('chunk_')])
        
        if received_chunks == total_chunks:
            # All chunks received - reassemble file
            logger.info(f"All chunks received for {file_id}, reassembling and processing...")
            try:
                # Process synchronously - this might take time for large files
                # Vercel timeout is 60s for Pro, 10s for Hobby
                result = reassemble_and_process_file(chunks_dir, file_id, filename)
                logger.info(f"File processing complete for {file_id}")
                return result
            except Exception as e:
                logger.exception(f"Error processing file {file_id}: {e}")
                # Clean up chunks on error
                try:
                    import shutil
                    shutil.rmtree(chunks_dir)
                except:
                    pass
                return jsonify({"error": f"Error processing file: {str(e)}"}), 500
        else:
            return jsonify({
                "success": True,
                "chunkIndex": chunk_index,
                "receivedChunks": received_chunks,
                "totalChunks": total_chunks,
                "message": f"Chunk {chunk_index + 1}/{total_chunks} uploaded"
            })
    
    except Exception as e:
        logger.exception("Chunk upload error")
        return jsonify({"error": f"Error uploading chunk: {str(e)}"}), 500


def reassemble_and_process_file(chunks_dir, file_id, filename):
    """Reassemble chunks into file and process it"""
    global parser
    
    try:
        # Get all chunk files and sort by index
        chunk_files = sorted(
            [f for f in os.listdir(chunks_dir) if f.startswith('chunk_')],
            key=lambda x: int(x.split('_')[1])
        )
        
        # Reassemble file
        reassembled_path = os.path.join(STORAGE_DIR, f'reassembled_{file_id}_{filename}')
        with open(reassembled_path, 'wb') as outfile:
            for chunk_file in chunk_files:
                chunk_path = os.path.join(chunks_dir, chunk_file)
                with open(chunk_path, 'rb') as infile:
                    outfile.write(infile.read())
                # Clean up chunk
                os.remove(chunk_path)
        
        # Clean up chunks directory
        try:
            os.rmdir(chunks_dir)
        except:
            pass
        
        # Process the reassembled file
        return process_uploaded_file(reassembled_path, filename)
    
    except Exception as e:
        logger.exception("Error reassembling file")
        return jsonify({"error": f"Error reassembling file: {str(e)}"}), 500


def process_uploaded_file(file_path, filename):
    """Process uploaded file (ZIP or JSON)"""
    global parser
    
    try:
        filename_lower = filename.lower()
        
        if filename_lower.endswith('.zip'):
            # Handle ZIP file
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                conversations_json = None
                for name in zip_ref.namelist():
                    if name.endswith('conversations.json'):
                        conversations_json = name
                        break
                
                if not conversations_json:
                    os.remove(file_path)
                    return jsonify({"error": "No conversations.json found in ZIP file"}), 400
                
                with zip_ref.open(conversations_json) as f:
                    data = json.load(f)
        
        elif filename_lower.endswith('.json'):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            os.remove(file_path)
            return jsonify({"error": "Unsupported file type"}), 400
        
        # Clean up reassembled file
        os.remove(file_path)
        
        # Process data (same as regular upload)
        return process_conversation_data(data)
    
    except Exception as e:
        logger.exception("Error processing uploaded file")
        if os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({"error": f"Error processing file: {str(e)}"}), 500


def process_conversation_data(data):
    """Process conversation data and store it"""
    global parser
    
    # Validate and normalize data structure
    if isinstance(data, dict):
        if "conversations" in data:
            data = data["conversations"]
        elif "data" in data:
            data = data["data"]
        else:
            for key, value in data.items():
                if isinstance(value, list) and len(value) > 0:
                    if isinstance(value[0], dict) and ("id" in value[0] or "conversation_id" in value[0] or "mapping" in value[0]):
                        data = value
                        break
    
    if not isinstance(data, list):
        return jsonify({"error": f"Invalid data format. Expected a list of conversations."}), 400
    
    if len(data) == 0:
        return jsonify({"error": "No conversations found in the file."}), 400
    
    logger.info(f"Parsing {len(data)} conversations from upload")
    logger.info(f"Data type: {type(data)}, First item type: {type(data[0]) if data else 'empty'}")
    
    # Parse the data
    parser = ChatGPTParser()
    try:
        parser.parse_from_json(data)
        logger.info(f"Parsed {len(parser.conversations)} conversations successfully")
        
        # Check if parsing actually found conversations
        if len(parser.conversations) == 0:
            logger.warning("Parser completed but found 0 conversations with messages")
            return jsonify({
                "error": "No conversations with messages found in the file.",
                "details": f"Parsed {len(data)} entries but none contained messages"
            }), 400
    except Exception as parse_error:
        logger.exception(f"Error parsing conversations in process_conversation_data: {parse_error}")
        return jsonify({
            "error": f"Error parsing conversations: {str(parse_error)}",
            "details": f"Exception type: {type(parse_error).__name__}"
        }), 500
    
    # Store data in file with session prefix and expiration
    session_id = session.get('_id', secrets.token_hex(16))
    file_id = hashlib.md5(f"{session_id}_{time.time()}".encode()).hexdigest()
    storage_file = os.path.join(STORAGE_DIR, f'{session_id}_conv_{file_id}.json')  # Add session prefix
    expires_at = time.time() + EPHEMERAL_TTL
    
    data_json = json.dumps(data)
    with open(storage_file, 'w', encoding='utf-8') as f:
        f.write(data_json)
    
    session['conversations_file'] = storage_file
    session['conversations_expires_at'] = expires_at  # Add expiration to session
    session.permanent = True
    
    cleanup_old_files()  # Trigger cleanup
    
    stats = parser.get_stats()
    logger.info(f"Upload complete: {stats['total_conversations']} conversations loaded")
    return jsonify({
        "success": True,
        "stats": stats,
        "expires_at": expires_at,  # Add expiration to response
        "expires_in": int(EPHEMERAL_TTL),
        "message": f"Successfully loaded {stats['total_conversations']} conversations"
    })


def process_file_background(job_id, file_path, filename, session_id):
    """Process file in background thread with expiration checks"""
    global parser, processing_jobs
    
    try:
        # Check if job expired before processing
        with job_lock:
            job = processing_jobs.get(job_id)
            if not job:
                logger.warning(f"Job {job_id} not found, aborting")
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
                return
            
            # Check expiration
            expires_at = job.get('expires_at', 0)
            if expires_at > 0 and time.time() > expires_at:
                logger.warning(f"Job {job_id} expired before processing")
                del processing_jobs[job_id]
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
                return
            
            processing_jobs[job_id].update({
                "status": "processing",
                "progress": 0,
                "message": "Extracting file..."
            })
        
        logger.info(f"[Job {job_id}] Starting background processing of {filename}")
        
        # Extract data from file
        with job_lock:
            processing_jobs[job_id]["progress"] = 10
            processing_jobs[job_id]["message"] = "Reading file..."
        
        filename_lower = filename.lower()
        if filename_lower.endswith('.zip'):
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                conversations_json = None
                for name in zip_ref.namelist():
                    if name.endswith('conversations.json'):
                        conversations_json = name
                        break
                
                if not conversations_json:
                    with job_lock:
                        processing_jobs[job_id] = {
                            "status": "error",
                            "error": "No conversations.json found in ZIP file"
                        }
                    os.remove(file_path)
                    return
                
                with zip_ref.open(conversations_json) as f:
                    data = json.load(f)
        elif filename_lower.endswith('.json'):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            with job_lock:
                processing_jobs[job_id] = {
                    "status": "error",
                    "error": "Unsupported file type"
                }
            os.remove(file_path)
            return
        
        # Clean up uploaded file
        os.remove(file_path)
        
        # Normalize data structure
        with job_lock:
            processing_jobs[job_id]["progress"] = 30
            processing_jobs[job_id]["message"] = "Processing data structure..."
        
        if isinstance(data, dict):
            if "conversations" in data:
                data = data["conversations"]
            elif "data" in data:
                data = data["data"]
            else:
                for key, value in data.items():
                    if isinstance(value, list) and len(value) > 0:
                        if isinstance(value[0], dict) and ("id" in value[0] or "conversation_id" in value[0] or "mapping" in value[0]):
                            data = value
                            break
        
        if not isinstance(data, list) or len(data) == 0:
            with job_lock:
                processing_jobs[job_id] = {
                    "status": "error",
                    "error": "No conversations found in file"
                }
            return
        
        # Parse conversations
        with job_lock:
            processing_jobs[job_id]["progress"] = 50
            processing_jobs[job_id]["message"] = f"Parsing {len(data)} conversations..."
        
        parser = ChatGPTParser()
        parser.parse_from_json(data)
        
        if len(parser.conversations) == 0:
            with job_lock:
                processing_jobs[job_id] = {
                    "status": "error",
                    "error": "No conversations with messages found"
                }
            return
        
        # Store data with session prefix and expiration
        with job_lock:
            if job_id not in processing_jobs:
                # Job was deleted/expired during processing
                logger.warning(f"Job {job_id} was removed during processing")
                return
            processing_jobs[job_id]["progress"] = 80
            processing_jobs[job_id]["message"] = "Processing data..."
        
        file_id = hashlib.md5(f"{session_id}_{time.time()}".encode()).hexdigest()
        storage_file = os.path.join(STORAGE_DIR, f'{session_id}_conv_{file_id}.json')  # Add session prefix
        
        with open(storage_file, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        
        stats = parser.get_stats()
        expires_at = time.time() + EPHEMERAL_TTL
        
        with job_lock:
            if job_id in processing_jobs:  # Double-check job still exists
                processing_jobs[job_id].update({
                    "status": "completed",
                    "progress": 100,
                    "message": f"Successfully loaded {stats['total_conversations']} conversations",
                    "storage_file": storage_file,
                    "stats": stats,
                    "expires_at": expires_at  # Update expiration
                })
        
        logger.info(f"[Job {job_id}] Processing complete: {stats['total_conversations']} conversations")
        
    except Exception as e:
        logger.exception(f"[Job {job_id}] Error in background processing: {e}")
        with job_lock:
            processing_jobs[job_id] = {
                "status": "error",
                "error": str(e)
            }
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass


@app.route('/upload', methods=['POST'])
@login_required
def upload():
    """Handle ChatGPT export file upload - saves file and processes in background"""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    # Check file size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > app.config['MAX_CONTENT_LENGTH']:
        return jsonify({
            "error": f"File too large. Maximum size: {app.config['MAX_CONTENT_LENGTH'] / 1024 / 1024:.0f}MB"
        }), 413
    
    # Validate file type
    filename = file.filename.lower()
    if not (filename.endswith('.zip') or filename.endswith('.json')):
        return jsonify({"error": "Please upload a ZIP file (ChatGPT export) or a conversations.json file"}), 400
    
    try:
        # Generate job ID and expiration
        job_id = secrets.token_hex(16)
        session_id = session.get('_id', secrets.token_hex(16))
        user_id = session.get('user_id')  # Get user_id for session verification
        expires_at = time.time() + EPHEMERAL_TTL
        
        # Save uploaded file to temp location with session prefix
        upload_dir = os.path.join(STORAGE_DIR, 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, f'{session_id}_{job_id}_{file.filename}')
        file.save(file_path)
        
        logger.info(f"File saved, starting background job {job_id} for {file.filename}")
        
        # Initialize job status with expiration and user tracking
        with job_lock:
            processing_jobs[job_id] = {
                "status": "queued",
                "progress": 0,
                "message": "File uploaded, starting processing...",
                "session_id": session_id,
                "user_id": user_id,  # Store user_id for verification
                "input_file": file_path,
                "created_at": time.time(),
                "expires_at": expires_at  # Add expiration
            }
        
        # Start background processing thread
        thread = threading.Thread(
            target=process_file_background,
            args=(job_id, file_path, file.filename, session_id),
            daemon=True
        )
        thread.start()
        
        # Return immediately with job ID and expiration
        return jsonify({
            "success": True,
            "job_id": job_id,
            "expires_at": expires_at,
            "expires_in": int(EPHEMERAL_TTL),
            "message": "File uploaded successfully. Processing in background..."
        })
    
    except Exception as e:
        logger.exception("Upload error")
        return jsonify({"error": f"Error uploading file: {str(e)}"}), 500


@app.route('/upload-status/<job_id>')
@login_required
def upload_status(job_id):
    """Check status of background processing job with expiration and session verification"""
    session_id = session.get('_id')
    user_id = session.get('user_id')
    
    with job_lock:
        job = processing_jobs.get(job_id)
    
    if not job:
        return jsonify({"error": "Job not found or expired"}), 404
    
    # Verify session ownership (security - ensure user can only access their own jobs)
    if job.get('session_id') != session_id or job.get('user_id') != user_id:
        logger.warning(f"Unauthorized access attempt to job {job_id} by user {user_id}")
        return jsonify({"error": "Unauthorized"}), 403
    
    # Check expiration
    expires_at = job.get('expires_at', 0)
    if expires_at > 0 and time.time() > expires_at:
        # Auto-cleanup expired job
        cleanup_expired_jobs()
        return jsonify({
            "error": "Job expired",
            "status": "expired"
        }), 410  # 410 Gone
    
    # If completed, update session and clean up job
    if job.get("status") == "completed":
        storage_file = job.get("storage_file")
        if storage_file and os.path.exists(storage_file):
            session['conversations_file'] = storage_file
            session['conversations_expires_at'] = expires_at  # Store expiration in session
            session.permanent = True
            session.modified = True
            logger.info(f"Job {job_id} completed, session updated with file: {storage_file}")
        
        # Clean up job after returning (keep for a bit in case of retries)
        def cleanup_job():
            time.sleep(60)  # Keep for 1 minute
            with job_lock:
                if job_id in processing_jobs:
                    del processing_jobs[job_id]
        threading.Thread(target=cleanup_job, daemon=True).start()
    
    # Return job status with expiration info
    response = dict(job)
    response['expires_in'] = max(0, int(expires_at - time.time())) if expires_at > 0 else 0
    return jsonify(response)


@app.route('/clear', methods=['POST'])
@login_required
def clear_data():
    """Clear the current loaded data"""
    global parser
    parser = None
    
    # Clear from file storage
    storage_file = session.get('conversations_file', None)
    if storage_file and os.path.exists(storage_file):
        try:
            os.remove(storage_file)
            logger.info(f"Removed storage file: {storage_file}")
        except Exception as e:
            logger.warning(f"Error removing storage file: {e}")
    
    # Clear from session (both old and new methods)
    session.pop('conversations_file', None)
    session.pop('conversations_data', None)
    
    logger.info("Data cleared")
    return jsonify({"success": True, "message": "Data cleared"})


@app.route('/conversation/<conv_id>')
@login_required
def get_conversation(conv_id):
    global parser
    parser = get_parser_from_session()
    if not parser:
        return jsonify({"error": "No data loaded"}), 400
    
    for conv in parser.conversations:
        if conv.id == conv_id:
            return jsonify({
                "id": conv.id,
                "title": conv.title,
                "project_name": conv.project_name,
                "create_time": conv.create_time.strftime('%B %d, %Y') if conv.create_time else None,
                "model": conv.model,
                "markdown": conv.to_markdown(),
                "messages": [
                    {"role": m.role, "content": m.content}
                    for m in conv.messages
                ]
            })
    
    return jsonify({"error": "Conversation not found"}), 404


@app.route('/search')
@login_required
def search():
    global parser
    parser = get_parser_from_session()
    query = request.args.get('q', '')
    if not parser:
        return jsonify({"error": "No data loaded"}), 400
    
    results = parser.search(query)
    return jsonify({
        "results": [
            {
                "id": c.id,
                "title": c.title,
                "preview": c.get_preview(),
                "date": c.update_time.strftime('%b %d, %Y') if c.update_time else None
            }
            for c in results
        ]
    })


@app.route('/debug')
@login_required
def debug_info():
    """Debug endpoint to see data structure"""
    global parser
    parser = get_parser_from_session()
    if not parser:
        return jsonify({"error": "No data loaded"}), 400
    
    # Get raw data from file storage
    storage_file = session.get('conversations_file', None)
    raw_data = []
    if storage_file and os.path.exists(storage_file):
        try:
            with open(storage_file, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
        except Exception as e:
            logger.error(f"Error loading raw data from file: {e}")
    
    # Fallback to old session storage
    if not raw_data:
        raw_data = session.get('conversations_data', [])
    
    # Get keys from first conversation
    sample_keys = list(raw_data[0].keys()) if raw_data else []
    
    # Sample non-mapping data from first few conversations
    samples = []
    for conv in raw_data[:5]:
        sample = {k: v for k, v in conv.items() if k != 'mapping'}
        samples.append(sample)
    
    return jsonify({
        "total_raw_conversations": len(raw_data),
        "parsed_conversations": len(parser.conversations),
        "parsed_projects": len(parser.projects),
        "unassigned": len(parser.unassigned_conversations),
        "sample_keys": sample_keys,
        "sample_conversations": samples,
        "project_names": [p.name for p in parser.projects.values()]
    })


@app.route('/export-all')
@login_required
def export_all():
    global parser
    parser = get_parser_from_session()
    if not parser:
        return "No data loaded", 400
    
    logger.info(f"Exporting {len(parser.conversations)} conversations")
    
    # Create a ZIP file in memory
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Export by project
        for project_id, project in parser.projects.items():
            for conv in project.conversations:
                filename = f"{_sanitize_filename(project.name)}/{_sanitize_filename(conv.title)}.md"
                zf.writestr(filename, conv.to_markdown())
        
        # Export unassigned
        for conv in parser.unassigned_conversations:
            filename = f"_Unassigned/{_sanitize_filename(conv.title)}.md"
            zf.writestr(filename, conv.to_markdown())
    
    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name='chatgpt_export_markdown.zip'
    )


def _sanitize_filename(name: str) -> str:
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    if len(name) > 80:
        name = name[:80]
    return name.strip() or "untitled"


def load_export(export_path: str):
    """Load a ChatGPT export from the given path"""
    global parser
    parser = ChatGPTParser(export_path)
    parser.parse()
    return parser.get_stats()


# Environment validation for production
def validate_production_config():
    """Validate that all required config is set for production"""
    if not IS_PRODUCTION:
        return True
    
    errors = []
    
    if not FIREBASE_AUTH_ENABLED:
        errors.append("FIREBASE_CONFIG must be set in production")
    
    web_config = os.environ.get('FIREBASE_WEB_CONFIG')
    if not web_config:
        # Check if file exists (support both old and new locations)
        project_dir = os.path.dirname(os.path.abspath(__file__))
        candidate_paths = [
            os.path.join(project_dir, 'firebase-web-config.json'),
            os.path.join(project_dir, 'config', 'firebase-web-config.json'),
        ]
        if not any(os.path.exists(path) for path in candidate_paths):
            errors.append("FIREBASE_WEB_CONFIG must be set in production")
    
    if not os.environ.get('SECRET_KEY'):
        errors.append("SECRET_KEY must be set in production")
    
    if errors:
        logger.error("Production configuration errors:")
        for error in errors:
            logger.error(f"  - {error}")
        return False
    
    logger.info("✅ Production configuration validated")
    return True


# Health check endpoint
@app.route('/health')
def health_check():
    """Health check endpoint for monitoring - verify storage is writable"""
    status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "environment": FLASK_ENV,
        "firebase_configured": FIREBASE_AUTH_ENABLED,
        "storage_dir": STORAGE_DIR,
        "storage_writable": False,
        "cleanup_thread_running": False,
        "ephemeral_ttl_seconds": EPHEMERAL_TTL
    }
    
    # Test storage write access
    try:
        test_file = os.path.join(STORAGE_DIR, '.health_check')
        with open(test_file, 'w') as f:
            f.write(str(time.time()))
        os.remove(test_file)
        status["storage_writable"] = True
    except Exception as e:
        status["status"] = "unhealthy"
        status["storage_error"] = str(e)
        logger.error(f"Health check: Storage not writable - {e}")
    
    # Check cleanup thread is running
    try:
        status["cleanup_thread_running"] = cleanup_thread.is_alive()
        if not cleanup_thread.is_alive():
            status["status"] = "degraded"
            status["warning"] = "Cleanup thread not running"
    except:
        status["cleanup_thread_running"] = False
    
    # Check critical services
    if IS_PRODUCTION and not FIREBASE_AUTH_ENABLED:
        if status["status"] == "healthy":
            status["status"] = "degraded"
        status["warning"] = (status.get("warning", "") + "; Firebase not configured").lstrip("; ")
    
    http_status = 200 if status["status"] == "healthy" else (503 if status["status"] == "unhealthy" else 200)
    return jsonify(status), http_status


@app.route('/test')
def test():
    """Simple test endpoint to verify app is running"""
    return jsonify({
        "message": "App is running",
        "timestamp": datetime.now().isoformat(),
        "working_directory": os.getcwd(),
        "python_path": sys.path[:3]  # First 3 entries
    }), 200


if __name__ == "__main__":
    # ONLY for local development
    # In production, this is handled by Firebase Functions via main.py
    app.run(host="0.0.0.0", port=8080, debug=True)
