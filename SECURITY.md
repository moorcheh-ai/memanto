# Security Policy

## Reporting Security Vulnerabilities

If you discover a security vulnerability in MEMANTO, please report it to:
- **Email**: support@moorcheh.ai
- **Subject**: [MEMANTO Security] Brief description

**Please do not** open public GitHub issues for security vulnerabilities.

---

## Secret Management Best Practices

### ⚠️ CRITICAL: Never Commit Secrets to Git

**What NOT to commit:**
- `.env` files with real credentials
- API keys (Moorcheh API keys start with `mk_`)
- JWT tokens
- Private keys (`.key`, `.pem` files)
- Database credentials
- Any file containing passwords or sensitive tokens

### ✅ How to Handle Secrets Properly

#### 1. Use Environment Variables

**Local Development:**
```bash
# Create .env file (already in .gitignore)
cp .env.example .env

# Edit .env with your REAL API key
nano .env

# The .env file is automatically ignored by git
```

**Production Deployment:**
- **Docker**: Use `--env-file` or `-e` flags
- **Kubernetes**: Use Secrets or external secret managers (Vault, AWS Secrets Manager)
- **Cloud Run/Lambda**: Use platform secret management
- **Never** hardcode secrets in code or Dockerfiles

#### 2. Use .env.example for Templates

The `.env.example` file contains placeholder values only:
```bash
# .env.example (safe to commit)
MOORCHEH_API_KEY=mk_your_api_key_here

# .env (NEVER commit)
MOORCHEH_API_KEY=mk_abc123real_key_here
```

#### 3. Rotate Compromised Keys Immediately

If you accidentally commit a secret:

1. **Rotate the key immediately** - Get a new API key from Moorcheh dashboard
2. **Remove from git history**:
   ```bash
   # Remove file from git history
   git filter-branch --force --index-filter \
     "git rm --cached --ignore-unmatch .env" \
     --prune-empty --tag-name-filter cat -- --all

   # Force push (use with caution)
   git push origin --force --all
   ```
3. **Update .gitignore** (already done in this repo)
4. **Verify removal**: Use `git log --all --full-history -- .env`

---

## GitHub Secret Scanning

This repository has GitHub secret scanning enabled. If you receive an alert:

### False Positives (Documentation Examples)

Example tokens in documentation are **not real secrets**:
- `Bearer <jwt_token_here>` - placeholder
- `mk_your_api_key_here` - placeholder
- `eyJhbGc.eyJzdWI.SflKxw...` - example format (truncated, not valid)

These are safe and will not expose your system.

### Real Secrets (Action Required)

If the alert references a **real API key**:
1. **Rotate the key** immediately in Moorcheh dashboard
2. **Remove from git history** (see above)
3. **Update local .env** with new key
4. **Verify .gitignore** is working: `git check-ignore .env`

---

## Contribution Security Guidelines

### Prohibited Content

To maintain the integrity and safety of this project, the following types of content are strictly prohibited in all contributions (code, documentation, comments, commit messages, issues, and pull requests):

#### 🚫 Financial Content
- Cryptocurrency wallet addresses or solicitations
- Investment advice or financial promotions
- Requests for monetary donations or payments
- Links to payment platforms or fundraising campaigns
- Promotional content for financial products or services

#### 🚫 Phishing and Malicious Content
- Links designed to harvest credentials or personal information
- Fake login pages or credential capture mechanisms
- Malicious scripts or obfuscated code intended to cause harm
- Content impersonating legitimate services, organizations, or individuals
- Embedded trackers or unauthorized data collection mechanisms

#### 🚫 Social Engineering Content
- Manipulative language designed to deceive contributors or users
- False urgency or artificial scarcity tactics
- Impersonation of maintainers, bots, or automated systems
- Fake security alerts or warnings intended to cause alarm
- Content designed to manipulate users into taking harmful actions

#### 🚫 Unauthorized Fundraising
- Bounty claims not sanctioned by the official project maintainers
- Crowdfunding links or solicitations
- Requests for tips, gratuities, or compensation outside official channels
- Unauthorized references to bug bounty programs or reward schemes

### Maintainer Verification

Project maintainers will review all contributions for compliance with these guidelines. Submissions that contain prohibited content will be:

1. **Immediately closed** without merge
2. **Flagged** for review by the security team
3. **Reported** to GitHub Trust & Safety if the content is malicious or abusive

### Reporting Non-Compliant Submissions

If you identify a pull request, issue, or comment that violates these guidelines:

1. **Do not engage** with the content or follow any links it contains
2. **Report it** to the maintainers via email: support@moorcheh.ai with subject `[MEMANTO Security] Non-Compliant Submission`
3. **Use GitHub's reporting tools** to flag abusive or spam content directly on the platform

---

## Verification Checklist

Before making your repository public:

- [ ] `.env` is in `.gitignore`
- [ ] No `.env` file in git history: `git log --all -- .env` (should be empty after cleanup)
- [ ] `.env.example` only contains placeholders
- [ ] No hardcoded API keys in code: `git grep -i "mk_" "*.py" "*.ts" "*.js"`
- [ ] All dependencies are up to date and free of known vulnerabilities
- [ ] No prohibited or social-engineering content present in contributions
- [ ] All contributions reviewed for phishing, financial solicitation, and fundraising material