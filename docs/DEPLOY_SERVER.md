# Server Deployment Guide

Deploy to a traditional server (DigitalOcean, Linode, AWS EC2, Render, etc.) to avoid Vercel's 4.5MB limit and timeout issues.

## Quick Deploy Options

### Option 1: Render
1. Go to [render.com](https://render.com)
2. Sign up
3. Click "New" → "Web Service"
4. Connect your GitHub repo
5. Settings:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn -c gunicorn_config.py app:app`
   - **Environment:** Python 3
6. Add environment variables
7. Deploy!

### Option 3: DigitalOcean App Platform
1. Go to [cloud.digitalocean.com](https://cloud.digitalocean.com)
2. Create App → GitHub
3. Select repo
4. Configure:
   - **Type:** Web Service
   - **Run Command:** `gunicorn -c gunicorn_config.py app:app`
   - **Build Command:** `pip install -r requirements.txt`
5. Add environment variables
6. Deploy!

### Option 4: VPS (DigitalOcean Droplet, Linode, AWS EC2)
For full control:

```bash
# 1. SSH into your server
ssh root@your-server-ip

# 2. Install Python and dependencies
apt-get update
apt-get install -y python3 python3-pip nginx

# 3. Clone your repo
git clone https://github.com/yourusername/transfercc.git
cd transfercc/transfercc

# 4. Install Python dependencies
pip3 install -r requirements.txt

# 5. Set environment variables
export FLASK_ENV=production
export FIREBASE_CONFIG='{"type":"service_account",...}'
export FIREBASE_WEB_CONFIG='{"apiKey":"...",...}'
export SECRET_KEY="your-secret-key"

# 6. Run with Gunicorn
gunicorn -c gunicorn_config.py app:app

# 7. Set up Nginx reverse proxy (optional but recommended)
# See nginx config below
```

## Nginx Configuration (for VPS)

Create `/etc/nginx/sites-available/transfercc`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Increase timeouts for large uploads
        proxy_read_timeout 300s;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        
        # Increase body size limit
        client_max_body_size 500M;
    }
}
```

Enable it:
```bash
ln -s /etc/nginx/sites-available/transfercc /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

## Systemd Service (for VPS - Auto-start)

Create `/etc/systemd/system/transfercc.service`:

```ini
[Unit]
Description=Transfercc Flask App
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/transfercc/transfercc
Environment="FLASK_ENV=production"
Environment="FIREBASE_CONFIG=/path/to/firebase-service-account.json"
Environment="FIREBASE_WEB_CONFIG={\"apiKey\":\"...\"}"
Environment="SECRET_KEY=your-secret-key"
ExecStart=/usr/local/bin/gunicorn -c gunicorn_config.py app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
systemctl daemon-reload
systemctl enable transfercc
systemctl start transfercc
systemctl status transfercc
```

## Environment Variables Checklist

Make sure these are set in your deployment platform:

```bash
FLASK_ENV=production
FIREBASE_CONFIG={"type":"service_account",...}  # OR path to file
FIREBASE_WEB_CONFIG={"apiKey":"...","authDomain":"...","projectId":"...","storageBucket":"...","messagingSenderId":"...","appId":"..."}
SECRET_KEY=your-64-character-hex-string
PORT=5001  # Optional, defaults to 5001
```

## Testing After Deployment

1. Visit your app URL
2. Check `/health` endpoint
3. Try uploading a small file first
4. Then try a large file (should work now!)

## Troubleshooting

**Upload still fails?**
- Check server logs: `journalctl -u transfercc -f` (for systemd)
- Check file size limits in Nginx config
- Check Gunicorn timeout in `gunicorn_config.py`

**Authentication not working?**
- Verify `FIREBASE_CONFIG` and `FIREBASE_WEB_CONFIG` are set correctly
- Check Firebase authorized domains include your domain
- Check browser console for errors

**App not starting?**
- Check logs for import errors
- Verify all dependencies in `requirements.txt` are installed
- Check Python version (needs 3.8+)

## Recommended: Render or Firebase Hosting

For easiest deployment, I recommend **Render** or **Firebase Hosting**:
- ✅ No file size limits
- ✅ No timeout issues  
- ✅ Free tier available
- ✅ Auto HTTPS
- ✅ Easy environment variable management
- ✅ GitHub integration
- ✅ Auto-deploy on push

Just connect your GitHub repo and add environment variables - done!
