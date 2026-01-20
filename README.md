# 🚀 OTC – OpenAI to Claude Migration Tool

A beautiful tool to migrate your ChatGPT conversations to Claude. Parse your ChatGPT export, browse your history with a slick web interface, and export conversations as markdown for easy context sharing.

![Python](https://img.shields.io/badge/Python-3.8+-orange?style=flat-square)
![Flask](https://img.shields.io/badge/Flask-3.0-coral?style=flat-square)

## ✨ Features

- **📂 Parse ChatGPT Exports** – Handles the full `conversations.json` structure including projects
- **🔍 Search Everything** – Full-text search across all your conversations  
- **📁 Project Organization** – Keeps your ChatGPT project folders intact
- **📝 Export to Markdown** – One-click copy for pasting into Claude as context
- **🎨 Beautiful UI** – Dark theme with smooth animations

## 🏁 Quick Start

### Step 1: Export Your ChatGPT Data

1. Go to [chat.openai.com](https://chat.openai.com)
2. Click your **profile picture** → **Settings**
3. Go to **Data controls** → **Export data**
4. Confirm the export request
5. Wait for the email (usually 5-30 minutes)
6. Download and **extract the ZIP file**

### Step 2: Install Dependencies

```bash
cd transfercc
pip install -r requirements.txt
```

**Optional:** If you plan to use Firebase features (file uploads), copy the example environment file:
```bash
cp .env.example .env
# Then edit .env with your Firebase configuration
```

### Step 3: Run the Tool

**Option A: Web Interface (Recommended)**

```bash
python app.py /path/to/your/chatgpt-export-folder
```

Then open [http://localhost:5000](http://localhost:5000) in your browser.

**Option B: CLI Export**

```bash
# Just view stats
python parser.py /path/to/your/chatgpt-export-folder

# Export everything to markdown files
python parser.py /path/to/your/chatgpt-export-folder --export ./output
```

## 📖 Usage Guide

### Web Interface

1. **Browse by Project** – Use the sidebar to filter conversations by project
2. **Search** – Type in the search box to find specific conversations
3. **View Conversation** – Click any conversation to see the full thread
4. **Copy to Claude** – Click "📋 Copy as Markdown" to get the conversation ready for Claude
5. **Export All** – Click "📥 Export All as Markdown" to download everything as a ZIP

### Using with Claude

When you want to continue a conversation in Claude:

1. Find the conversation in the web interface
2. Click "📋 Copy as Markdown"
3. Start a new Claude conversation
4. Paste the markdown and add something like:

```
Here's a conversation I had previously. Please continue helping me with this:

[paste your markdown here]

My next question is: ...
```

Claude will have full context of your previous discussion!

## 🗂️ Export Structure

When you export to markdown, the tool creates:

```
output/
├── Project Name 1/
│   ├── conversation-title-1.md
│   └── conversation-title-2.md
├── Project Name 2/
│   └── another-conversation.md
└── _Unassigned/
    └── conversations-without-project.md
```

## 📋 Markdown Format

Each conversation is exported as:

```markdown
# Conversation Title

**Project:** Project Name
**Created:** January 15, 2026
**Last Updated:** January 15, 2026
**Model:** gpt-4

---

### 👤 User – Jan 15, 2026 10:30 AM

Your message here...

### 🤖 Assistant – Jan 15, 2026 10:31 AM

ChatGPT's response...
```

## 🔧 Advanced Usage

### Programmatic Access

```python
from parser import ChatGPTParser

# Load your export
parser = ChatGPTParser("/path/to/export")
parser.parse()

# Get stats
stats = parser.get_stats()
print(f"Total conversations: {stats['total_conversations']}")

# Search
results = parser.search("machine learning")
for conv in results:
    print(f"- {conv.title}")

# Export specific conversation
conv = parser.conversations[0]
markdown = conv.to_markdown()
```

### Environment Variables

```bash
# Change the port
FLASK_RUN_PORT=8080 python app.py /path/to/export

# Firebase (required for file uploads)
FIREBASE_CONFIG=path/to/firebase-service-account.json  # Or JSON string
FIREBASE_WEB_CONFIG='{"apiKey":"...","authDomain":"...","projectId":"..."}'  # JSON string
SECRET_KEY=your-secret-key-here  # Optional, auto-generated if not set
```

### Setting Up Firebase Authentication

To enable file uploads, you need to set up Firebase Authentication. Here's a step-by-step guide:

#### Step 1: Create a Firebase Project
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click **"Add project"** or select an existing project
3. Enter a project name (e.g., "OTC Migration Tool")
4. Follow the setup wizard (you can skip Google Analytics for now)
5. Click **"Create project"**

#### Step 2: Enable Authentication
1. In your Firebase project, go to **"Authentication"** in the left sidebar
2. Click **"Get started"**
3. Go to the **"Sign-in method"** tab
4. Click on **"Google"** provider
5. Toggle **"Enable"** and select a support email
6. Click **"Save"**

#### Step 3: Get Web App Configuration
1. Click the gear icon ⚙️ next to "Project Overview"
2. Select **"Project settings"**
3. Scroll down to **"Your apps"** section
4. Click the **Web icon** `</>` to add a web app
5. Register your app with a nickname (e.g., "OTC Web")
6. Copy the **Firebase configuration object** (it looks like this):
   ```json
   {
     "apiKey": "AIza...",
     "authDomain": "your-project.firebaseapp.com",
     "projectId": "your-project-id",
     "storageBucket": "your-project.appspot.com",
     "messagingSenderId": "123456789",
     "appId": "1:123456789:web:abcdef"
   }
   ```

#### Step 4: Get Service Account Key (for backend)
1. Still in **Project settings**, go to the **"Service accounts"** tab
2. Click **"Generate new private key"**
3. Click **"Generate key"** in the popup
4. A JSON file will download – **save this file securely!**

#### Step 5: Set Environment Variables

**Option A: Using files (recommended for local development)**
```bash
# Save the service account JSON as firebase-service-account.json in project root
# The app will auto-detect it

# Copy the example Firebase web config and edit it with your values
cp config/firebase-web-config.json.example config/firebase-web-config.json
# Edit config/firebase-web-config.json with your Firebase web config

# Or set web config as environment variable
export FIREBASE_WEB_CONFIG='{"apiKey":"...","authDomain":"...","projectId":"...","storageBucket":"...","messagingSenderId":"...","appId":"..."}'
```

**Option B: Using environment variables**
```bash
# Service account JSON as string
export FIREBASE_CONFIG='{"type":"service_account","project_id":"...",...}'

# Web config
export FIREBASE_WEB_CONFIG='{"apiKey":"...","authDomain":"...","projectId":"..."}'
```

**Option C: Using a .env file** (if using python-dotenv)
```
FIREBASE_CONFIG=path/to/firebase-service-account.json
FIREBASE_WEB_CONFIG={"apiKey":"...","authDomain":"...","projectId":"..."}
```

#### Quick Reference
- **Service Account Key**: Used by the backend to verify tokens (keep it secret!)
- **Web Config**: Used by the frontend for authentication (safe to expose)
- The app will automatically look for `firebase-service-account.json` in the project root
- For production, use environment variables or secure secret management

**Note:** Make sure to add your domain to authorized domains in Firebase Console → Authentication → Settings → Authorized domains for production use.

## 🤔 FAQ

**Q: How long does parsing take?**  
A: Usually a few seconds, even for thousands of conversations.

**Q: Does this upload my data anywhere?**  
A: No! Everything runs locally on your machine. Your data never leaves your computer.

**Q: Can I use this for other LLMs?**  
A: The markdown export works great for any LLM – Claude, Gemini, local models, etc.

**Q: What about images/files in my conversations?**  
A: Currently text-only. Image/file attachments are not included in ChatGPT exports.

## 🤝 Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## 🔒 Security

If you discover a security vulnerability, please send an email to the maintainers. Do not open a public issue. See [SECURITY.md](SECURITY.md) for more information.

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  Made with 🧡 for everyone migrating to Claude
</p>
