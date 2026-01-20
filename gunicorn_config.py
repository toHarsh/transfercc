# Gunicorn configuration for production
import multiprocessing
import os
import sys

# Add current directory to Python path to ensure app can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Server socket
bind = f"0.0.0.0:{os.environ.get('PORT', '5001')}"
backlog = 2048

# Worker processes - limit to 2 workers to avoid memory issues
cpu_count = multiprocessing.cpu_count()
workers = min(2, cpu_count)  # Max 2 workers to avoid memory issues
worker_class = 'sync'
worker_connections = 1000
timeout = 300  # 5 minutes for large file processing
keepalive = 5

# Increase limits for large file uploads
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# WSGI application - explicitly specify the app
# This tells Gunicorn which module and app instance to use
wsgi_app = 'app:app'

# Logging
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'transfercc'

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (if needed)
# keyfile = '/path/to/keyfile'
# certfile = '/path/to/certfile'
