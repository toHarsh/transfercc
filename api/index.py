"""
Vercel serverless entry point for Flask app
"""
import sys
import os
import logging

# Configure logging for Vercel
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

try:
    # Add parent directory to path to import app
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, parent_dir)
    
    # Don't change directory - Vercel needs to stay in the function directory
    # os.chdir(parent_dir)  # Commented out for Vercel compatibility
    
    logger.info(f"Importing Flask app from: {parent_dir}")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"Python path: {sys.path}")
    logger.info(f"Files in parent_dir: {os.listdir(parent_dir) if os.path.exists(parent_dir) else 'NOT FOUND'}")
    
    # Try importing app
    from app import app
    
    logger.info("Flask app imported successfully")
    logger.info(f"App instance: {app}")
    logger.info(f"App routes: {[str(rule) for rule in app.url_map.iter_rules()]}")
    
except Exception as e:
    import traceback
    logger.error(f"Failed to import Flask app: {e}")
    logger.error(f"Traceback: {traceback.format_exc()}")
    # Create a minimal error app so Vercel doesn't fail completely
    from flask import Flask
    app = Flask(__name__)
    
    @app.route('/')
    @app.route('/<path:path>')
    def error(path=''):
        error_msg = f"Error loading application: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
        return error_msg, 500

# Vercel Python runtime expects the Flask app to be exported
# Export the app directly - Vercel will use it as the handler
