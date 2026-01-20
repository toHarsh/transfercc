#!/usr/bin/env python3
"""
Script to set Firebase Functions environment variables programmatically.

This script sets the UPLOAD_BUCKET and MAX_UPLOAD_SIZE_MB environment variables
for Firebase Functions using the Firebase Admin SDK or gcloud CLI.
"""
import os
import subprocess
import sys

def set_env_vars_with_gcloud():
    """Set environment variables using gcloud CLI"""
    project_id = "transfercc-589f7"
    bucket_name = "transfercc-589f7-uploads"
    max_size_mb = "500"
    
    print("Setting Firebase Functions environment variables using gcloud...")
    
    # Get the function name (usually 'app' for the main HTTP function)
    function_name = "app"
    region = "us-central1"  # Default region for Firebase Functions
    
    try:
        # Set environment variables for the function
        cmd = [
            "gcloud", "functions", "deploy", function_name,
            "--gen2",
            "--runtime", "python310",
            "--region", region,
            "--source", "functions",
            "--entry-point", "app",
            "--set-env-vars", f"UPLOAD_BUCKET={bucket_name},MAX_UPLOAD_SIZE_MB={max_size_mb}",
            "--project", project_id
        ]
        
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ Environment variables set successfully!")
        print(result.stdout)
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error setting environment variables: {e}")
        print(f"stderr: {e.stderr}")
        return False
    except FileNotFoundError:
        print("❌ gcloud CLI not found. Please install Google Cloud SDK:")
        print("   https://cloud.google.com/sdk/docs/install")
        return False


def set_env_vars_with_firebase_cli():
    """Set environment variables using Firebase CLI (for Gen 1 functions)"""
    bucket_name = "transfercc-589f7-uploads"
    max_size_mb = "500"
    
    print("Setting Firebase Functions environment variables using Firebase CLI...")
    print("Note: For Gen 2 functions, use gcloud or Firebase Console")
    
    try:
        # For Gen 1 functions (deprecated but might work)
        cmd1 = ["firebase", "functions:config:set", f"upload.bucket={bucket_name}"]
        cmd2 = ["firebase", "functions:config:set", f"upload.max_size_mb={max_size_mb}"]
        
        print(f"Running: {' '.join(cmd1)}")
        subprocess.run(cmd1, check=True)
        
        print(f"Running: {' '.join(cmd2)}")
        subprocess.run(cmd2, check=True)
        
        print("✅ Environment variables set successfully!")
        print("⚠️  Note: For Gen 2 functions, you may need to use gcloud or set in Firebase Console")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")
        return False
    except FileNotFoundError:
        print("❌ Firebase CLI not found. Please install it:")
        print("   npm install -g firebase-tools")
        return False


def main():
    """Main function - tries different methods to set environment variables"""
    print("=" * 60)
    print("Firebase Functions Environment Variables Setup")
    print("=" * 60)
    print()
    
    # Try gcloud first (recommended for Gen 2)
    if set_env_vars_with_gcloud():
        print()
        print("✅ Setup complete!")
        return 0
    
    print()
    print("Trying Firebase CLI method...")
    if set_env_vars_with_firebase_cli():
        print()
        print("✅ Setup complete!")
        return 0
    
    print()
    print("=" * 60)
    print("⚠️  Could not set environment variables automatically.")
    print()
    print("Please set them manually:")
    print()
    print("Option 1: Firebase Console (Recommended)")
    print("  1. Go to https://console.firebase.google.com")
    print("  2. Select project: transfercc-589f7")
    print("  3. Go to Functions → Configuration")
    print("  4. Add environment variables:")
    print("     - UPLOAD_BUCKET = transfercc-589f7-uploads")
    print("     - MAX_UPLOAD_SIZE_MB = 500")
    print()
    print("Option 2: gcloud CLI")
    print("  gcloud functions deploy app --gen2 \\")
    print("    --set-env-vars UPLOAD_BUCKET=transfercc-589f7-uploads,MAX_UPLOAD_SIZE_MB=500")
    print()
    print("Option 3: The variables are already set in code with defaults:")
    print("  - UPLOAD_BUCKET defaults to: transfercc-589f7-uploads")
    print("  - MAX_UPLOAD_SIZE_MB defaults to: 500")
    print("  These will be used if environment variables are not set.")
    print("=" * 60)
    
    return 1


if __name__ == "__main__":
    sys.exit(main())
