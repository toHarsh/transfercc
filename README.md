# 🚀 Transfercc • ChatGPT history to Claude
[Video demo](https://youtu.be/1eRAh0mrGX0)

A beautiful tool to migrate your ChatGPT conversations to Claude. Parse your ChatGPT export, browse your history with a slick web interface, and export conversations as markdown for easy context sharing.

![Python](https://img.shields.io/badge/Python-3.8+-orange?style=flat-square)
![Flask](https://img.shields.io/badge/Flask-3.0-coral?style=flat-square)

## ✨ Features

- **📂 Parse ChatGPT Exports** – Handles the full `conversations.json` structure including projects
- **🔍 Search Everything** – Full-text search across all your conversations  
- **📁 Project Organization & Smart Groups** – Keeps your ChatGPT project folders intact and smartly groups related conversations for faster browsing
- **📝 Export to Markdown** – One-click copy for pasting into Claude as context
- **🎨 Beautiful UI** – Dark theme with smooth animations

## 🏁 Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/transfercc.git
   cd transfercc
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Start the app**
   ```bash
   python app.py /path/to/your/chatgpt-export-folder
   ```
   
   Then open [http://localhost:5000](http://localhost:5000) in your browser.

## 📥 Export Your ChatGPT Data

Before using the app, you'll need to export your ChatGPT conversations:

1. Go to [chat.openai.com](https://chat.openai.com)
2. Click your **profile picture** → **Settings**
3. Go to **Data controls** → **Export data**
4. Confirm the export request
5. Wait for the email (usually 5-30 minutes)
6. Download and **extract the ZIP file**

Use the extracted folder path when starting the app in step 4 above.

## 📖 Usage

### Web Interface

Once the app is running, you can:

1. **Browse by Project** – Use the sidebar to filter conversations by project
2. **Search** – Type in the search box to find specific conversations
3. **View Conversation** – Click any conversation to see the full thread
4. **Copy to Claude** – Click "📋 Copy as Markdown" to get the conversation ready for Claude
5. **Export All** – Click "📥 Export All as Markdown" to download everything as a ZIP

### CLI Export (Alternative)

You can also use the parser directly from the command line:

```bash
# Just view stats
python parser.py /path/to/your/chatgpt-export-folder

# Export everything to markdown files
python parser.py /path/to/your/chatgpt-export-folder --export ./output
```

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

### Environment Variables (local-only)

```bash
# Change the port (optional)
FLASK_RUN_PORT=8080 python app.py /path/to/export

# Optional secret key override (generated automatically if not set)
SECRET_KEY=your-secret-key-here
```

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
