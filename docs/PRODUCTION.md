# Production Deployment Guide

## Prerequisites

1. **Firebase Project** - Configured with Google Sign-In enabled
2. **Environment Variables** - All required variables set
3. **Python 3.8+** - Installed on server
4. **Production Server** - Gunicorn or similar WSGI server

## Required Environment Variables

### Required for Production

```bash
# Flask Environment
FLASK_ENV=production

# Firebase Backend (Service Account)
FIREBASE_CONFIG=/path/to/firebase-service-account.json
# OR as JSON string:
# FIREBASE_CONFIG='{"type":"service_account",...}'

# Firebase Frontend (Web Config)
FIREBASE_WEB_CONFIG='{"apiKey":"...","authDomain":"...","projectId":"...","storageBucket":"...","messagingSenderId":"...","appId":"..."}'

# Security
SECRET_KEY=your-secret-key-here  # Generate with: python -c "import secrets; print(secrets.token_hex(32))"

# Server
PORT=5001  # Optional, defaults to 5001
```

### Optional

```bash
# CORS (if needed)
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

## Deployment Steps

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Environment Variables

**Option A: Export in shell**
```bash
export FLASK_ENV=production
export FIREBASE_CONFIG="/path/to/firebase-service-account.json"
export FIREBASE_WEB_CONFIG='{"apiKey":"...",...}'
export SECRET_KEY="your-secret-key"
```

**Option B: Use .env file** (not recommended for production, use secret management)
```bash
# Create .env file
FLASK_ENV=production
FIREBASE_CONFIG=/path/to/firebase-service-account.json
FIREBASE_WEB_CONFIG={"apiKey":"...",...}
SECRET_KEY=your-secret-key
```

**Option C: Platform-specific** (Vercel, Heroku, etc.)
- Set environment variables in platform dashboard
- Never commit `.env` files to git

### 3. Run with Gunicorn (Recommended)

```bash
gunicorn -w 4 -b 0.0.0.0:5001 --timeout 120 app:app
```

### 4. Verify Deployment

- Check health endpoint: `https://yourdomain.com/health`
- Test authentication flow
- Verify file upload works

## Security Checklist

- [ ] `FLASK_ENV=production` is set
- [ ] `SECRET_KEY` is set and secure (32+ character random string)
- [ ] Firebase credentials are not in git
- [ ] HTTPS is enabled
- [ ] Firebase authorized domains include your production domain
- [ ] Session cookies are secure (automatic in production)
- [ ] File upload size limits are appropriate
- [ ] Error messages don't expose sensitive information

## Monitoring

### Health Check Endpoint

```bash
curl https://yourdomain.com/health
```

Returns:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-17T...",
  "environment": "production",
  "firebase_configured": true
}
```

### Usage Logs

User activity is logged to: `/tmp/transfercc_usage.log`

Format:
```
2024-01-17T10:30:00 | user@example.com | user_id_123 | login
2024-01-17T10:31:00 | user@example.com | user_id_123 | api_access
```

## Platform-Specific Deployment

### Vercel

1. Set environment variables in Vercel dashboard
2. Deploy: `vercel --prod`
3. The `vercel.json` is already configured

### Heroku

1. Set environment variables:
   ```bash
   heroku config:set FLASK_ENV=production
   heroku config:set FIREBASE_CONFIG="..."
   heroku config:set FIREBASE_WEB_CONFIG='{...}'
   heroku config:set SECRET_KEY="..."
   ```

2. Deploy:
   ```bash
   git push heroku main
   ```

### Docker

Create `Dockerfile`:
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5001

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5001", "--timeout", "120", "app:app"]
```

## Troubleshooting

### Firebase not initializing
- Check `FIREBASE_WEB_CONFIG` is set correctly
- Verify Firebase project has Google Sign-In enabled
- Check browser console for errors

### Authentication not working
- Verify `FIREBASE_CONFIG` points to valid service account
- Check Firebase authorized domains include your domain
- Verify session cookies are working (check browser dev tools)

### Health check fails
- Check all required environment variables are set
- Review application logs for errors
- Verify Firebase credentials are valid
