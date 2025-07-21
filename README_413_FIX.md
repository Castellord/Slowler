# Fix for "413 Request Entity Too Large" Error

This document explains the fixes applied to resolve the "413 Request Entity Too Large" error when uploading large audio files.

## What was the problem?

The error occurred because multiple layers in the application stack had request size limits:

1. **Flask development server (Werkzeug)** - Default limits for request size
2. **React development proxy** - Limited request forwarding capabilities
3. **Gunicorn configuration** - Default request size limits

## Solutions Applied

### 1. Backend Improvements

#### Flask Configuration
- Increased `MAX_CONTENT_LENGTH` from 100MB to **500MB**
- Added better error handling for large file uploads

#### Production Server (Gunicorn)
- Added Gunicorn as production WSGI server
- Configured proper request limits:
  - `timeout = 600` (10 minutes for large file processing)
  - `limit_request_field_size = 16384`
  - `workers = CPU_COUNT * 2 + 1`

#### Development Server
- Enhanced Werkzeug configuration for development
- Added threaded processing support

### 2. Frontend Improvements

#### Error Handling
- Added specific handling for 413 errors
- Better user feedback for large file uploads
- Graceful fallback error messages

### 3. Docker Configuration

#### Backend Dockerfile
- Uses Gunicorn in production mode
- Proper configuration file setup
- Optimized for large file handling

## How to Apply the Fix

### Option 1: Rebuild Docker Containers (Recommended)

```bash
# Stop existing containers
docker-compose down

# Rebuild with new configuration
docker-compose build --no-cache

# Start with new configuration
docker-compose up
```

### Option 2: Development Mode

```bash
# Backend (Terminal 1)
cd backend
pip install -r requirements.txt
python app.py

# Frontend (Terminal 2)
npm start
```

## Testing the Fix

1. **Small files (< 50MB)**: Should work immediately
2. **Medium files (50-200MB)**: Should work with new configuration
3. **Large files (200-500MB)**: Should work but may take longer to process

## File Size Recommendations

- **Optimal**: Under 100MB per file
- **Supported**: Up to 500MB per file
- **Multiple files**: Process in batches if total size > 200MB

## Troubleshooting

### If you still get 413 errors:

1. **Check file sizes**: Ensure individual files are under 500MB
2. **Process fewer files**: Try uploading 1-2 files at a time
3. **Check available disk space**: Ensure sufficient space for processing
4. **Restart containers**: `docker-compose restart`

### If processing is slow:

1. **Large files take time**: 10+ minutes for very large files is normal
2. **Check server resources**: Ensure adequate RAM and CPU
3. **Monitor logs**: `docker-compose logs backend`

## Configuration Details

### Current Limits:
- **Flask**: 500MB max request size
- **Gunicorn**: 10-minute timeout, optimized workers
- **Frontend**: Better error handling and user feedback

### File Processing:
- **Supported formats**: MP3, WAV
- **Processing**: Rubber Band algorithm (high quality)
- **Output**: ZIP archive with processed files

## Additional Notes

- The fix maintains backward compatibility
- Development and production modes are both supported
- Error messages are now more informative
- Processing progress is better tracked

If you continue to experience issues, check the Docker logs:
```bash
docker-compose logs backend
docker-compose logs frontend
