# Gunicorn configuration for handling large file uploads
import multiprocessing

# Server socket
bind = "0.0.0.0:5230"
backlog = 2048

# Worker processes - reduced for memory efficiency
workers = 2  # Fixed number for better memory control
worker_class = "sync"
worker_connections = 1000
timeout = 1200  # 20 minutes for large file processing
keepalive = 2

# Restart workers more frequently to prevent memory leaks
max_requests = 10  # Restart after fewer requests
max_requests_jitter = 5
worker_tmp_dir = "/dev/shm"  # Use shared memory for temp files

# Request limits - IMPORTANT for large file uploads
limit_request_line = 8192
limit_request_fields = 200
limit_request_field_size = 16384

# Logging
loglevel = "info"
accesslog = "-"
errorlog = "-"

# Process naming
proc_name = "slowler-audio-processor"

# Server mechanics
preload_app = False
daemon = False
pidfile = None
user = None
group = None
tmp_upload_dir = None

# SSL (if needed)
keyfile = None
certfile = None
