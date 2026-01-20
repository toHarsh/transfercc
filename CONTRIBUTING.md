# Contributing to TransferCC

Thank you for your interest in contributing to TransferCC! This document provides guidelines and instructions for contributing.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/your-username/transfercc.git
   cd transfercc
   ```
3. **Create a virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Development Setup

1. **Copy environment variables** (if needed for Firebase features):
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. **Run the development server**:
   ```bash
   python app.py /path/to/test/chatgpt-export
   ```

## Making Changes

1. **Create a branch** for your feature or bugfix:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bugfix-name
   ```

2. **Make your changes** and test them thoroughly

3. **Commit your changes** with clear, descriptive commit messages:
   ```bash
   git commit -m "Add feature: description of what you added"
   ```

4. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

5. **Create a Pull Request** on GitHub

## Code Style

- Follow PEP 8 style guidelines for Python code
- Use meaningful variable and function names
- Add comments for complex logic
- Keep functions focused and single-purpose
- Write docstrings for classes and functions

## Testing

Before submitting a PR, please:

1. Test your changes locally
2. Ensure the app runs without errors
3. Test with sample ChatGPT export data
4. Check that existing features still work

## Pull Request Guidelines

- **Clear title**: Summarize what the PR does
- **Description**: Explain what changes you made and why
- **Testing**: Describe how you tested your changes
- **Screenshots**: If your PR includes UI changes, add screenshots

## Reporting Issues

When reporting bugs or requesting features:

1. **Check existing issues** to avoid duplicates
2. **Use clear titles** that describe the issue
3. **Provide details**:
   - Steps to reproduce
   - Expected behavior
   - Actual behavior
   - Environment (OS, Python version, etc.)
   - Error messages or logs (if applicable)

## Security

- **Never commit** sensitive information:
  - API keys
  - Service account JSON files
  - Private keys
  - Passwords or tokens
- If you accidentally commit sensitive data, contact the maintainers immediately

## Questions?

Feel free to open an issue for questions or discussions. We're happy to help!

Thank you for contributing to TransferCC! 🎉
