# Security Policy

## Supported Versions

We release patches for security vulnerabilities. Which versions are eligible for receiving such patches depends on the CVSS v3.0 Rating:

| Version | Supported          |
| ------- | ------------------ |
| Latest  | :white_check_mark: |
| < Latest| :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability, please **do not** open a public issue. Instead, please report it via one of the following methods:

1. **Email**: Send details to the repository maintainers
2. **Private Security Advisory**: If available, use GitHub's private security advisory feature

Please include the following information:
- Type of vulnerability
- Full paths of source file(s) related to the vulnerability
- The location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit the issue

We will acknowledge receipt of your vulnerability report and work with you to understand and resolve the issue quickly.

## Security Best Practices for Users

When using this project:

1. **Never commit sensitive files**:
   - `firebase-service-account.json` or any service account JSON files
   - `.env` files with real credentials
   - Any files containing API keys or private keys

2. **Use environment variables** for sensitive configuration:
   - Store Firebase credentials in environment variables
   - Use `.env` files locally (and ensure they're in `.gitignore`)
   - Never hardcode credentials in source code

3. **Review dependencies** regularly:
   - Keep dependencies up to date
   - Review security advisories for dependencies

4. **If deploying publicly**:
   - Ensure proper authentication is configured
   - Use HTTPS in production
   - Configure Firebase security rules appropriately
   - Limit access to sensitive endpoints

## Known Security Considerations

- **Firebase Web Config**: The Firebase web configuration (used in frontend) is safe to expose, but service account keys must be kept secret
- **Local Processing**: By default, all data processing happens locally - your ChatGPT exports never leave your machine unless you explicitly enable cloud features
- **Authentication**: Firebase authentication is optional and only required for cloud upload features
