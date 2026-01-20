# Firebase Deployment Guide

This guide will help you deploy the Transfercc app to Firebase Hosting and Cloud Functions.

## Prerequisites

**Important:** Your app is Python, but Firebase CLI (a Node.js tool) is needed for deployment. Think of it like `git` - it's a tool you install once to deploy your code.

### Quick Setup (Recommended):

1. **Install Node.js** (one-time, just for the CLI tool):
   ```bash
   # macOS with Homebrew:
   brew install node
   
   # Or download from: https://nodejs.org/
   ```

2. **Install Firebase CLI**:
   ```bash
   npm install -g firebase-tools
   ```

3. **Login to Firebase**:
   ```bash
   firebase login
   ```

That's it! You only need Node.js for the deployment tool - your app still runs Python on Firebase.

**Firebase Project** - Already configured (transfercc-589f7)

## Setup

1. **Initialize Firebase** (if not already done):
   ```bash
   firebase init
   ```
   - Select: Hosting and Functions
   - Use existing project: transfercc-589f7
   - Public directory: `static`
   - Configure as single-page app: No
   - Set up automatic builds: No

2. **Set Environment Variables** in Firebase Functions:
   ```bash
   firebase functions:config:set \
     flask.env="production" \
     firebase.config="$(cat firebase-service-account.json)" \
     firebase.web_config="$(cat firebase-web-config.json)" \
     secret.key="your-secret-key-here"
   ```

   Or set them in Firebase Console:
   - Go to Firebase Console → Functions → Configuration
   - Add environment variables:
     - `FLASK_ENV=production`
     - `FIREBASE_CONFIG` (JSON string from firebase-service-account.json)
     - `FIREBASE_WEB_CONFIG` (JSON string from firebase-web-config.json)
     - `SECRET_KEY` (your secret key)

## Deployment

### Using Firebase CLI (if installed):

1. **Deploy Functions**:
   ```bash
   firebase deploy --only functions
   ```

2. **Deploy Hosting**:
   ```bash
   firebase deploy --only hosting
   ```

3. **Deploy Everything**:
   ```bash
   firebase deploy
   ```

### Using Google Cloud SDK (Alternative):

```bash
# Deploy function
gcloud functions deploy app \
  --gen2 \
  --runtime=python311 \
  --region=us-central1 \
  --source=functions \
  --entry-point=app \
  --trigger-http \
  --allow-unauthenticated
```

### Using Firebase Console (Web UI - No CLI needed):

1. Go to [Firebase Console](https://console.firebase.google.com)
2. Select your project: transfercc-589f7
3. Go to **Functions** → **Get Started**
4. Upload your `functions/` directory
5. Set environment variables in the console
6. Deploy from the web interface

## Project Structure

```
transfercc/
├── functions/
│   ├── main.py              # Cloud Function entry point
│   └── requirements.txt     # Function dependencies
├── static/                  # Static files (hosted on Firebase Hosting)
├── app.py                  # Flask application
├── firebase.json           # Firebase configuration
└── .firebaserc            # Firebase project configuration
```

## How It Works

1. **Firebase Hosting** serves static files from the `static/` directory
2. **Cloud Functions** runs the Flask app as a serverless function
3. All requests are routed through the `app` function which handles Flask routing

## Troubleshooting

### Functions not deploying
- Check Python version (should be 3.11)
- Verify `functions/requirements.txt` is correct
- Check Firebase CLI is up to date: `firebase --version`

### Environment variables not working
- Set them in Firebase Console → Functions → Configuration
- Or use `firebase functions:config:set`

### Static files not loading
- Verify `static/` directory exists
- Check `firebase.json` hosting configuration
- Ensure files are committed to git

## URLs

After deployment:
- **Hosting URL**: `https://transfercc-589f7.web.app`
- **Functions URL**: `https://us-central1-transfercc-589f7.cloudfunctions.net/app`

The hosting URL will automatically route to the function for all requests.
