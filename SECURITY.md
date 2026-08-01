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

## Security Guidelines

### ⚠️ Scams and Phishing

- Be cautious of unsolicited messages claiming to be from MEMANTO maintainers
- Official communication occurs only through verified GitHub accounts and the official support email
- Do **not** click links in unsolicited messages claiming to offer rewards, bounties, or urgent security fixes
- Verify the authenticity of any communication before acting on instructions

### ⚠️ Malicious Code

- Do **not** submit pull requests containing obfuscated, minified, or otherwise unreadable code without clear justification
- Do **not** introduce dependencies that have not been reviewed for security vulnerabilities
- All submitted code must be transparent, auditable, and serve a clear, documented purpose

### ⚠️ Social Engineering

- Maintainers will never ask for your credentials, private keys, or personal financial information
- Do **not** follow instructions from unverified individuals claiming authority over this project
- Report any suspicious communication to **support@moorcheh.ai**

### ⚠️ Unauthorized Fundraising

- MEMANTO does not solicit cryptocurrency payments, donations, or financial contributions through GitHub issues, pull requests, or unofficial channels
- Any requests for payment in exchange for bug fixes, features, or access are unauthorized and should be reported immediately

### ⚠️ Bounty Fraud

- Bounty programs, if any, are announced exclusively through official MEMANTO channels
- Do **not** engage with individuals claiming to offer bounties through unofficial means
- Fraudulent bounty claims or attempts to exploit bounty programs are strictly prohibited and will result in permanent bans

---

## Verification Checklist

Before making your repository public:

- [ ] `.env` is in `.gitignore`
- [ ] No `.env` file in git history: `git log --all -- .env` (should be empty after cleanup)
- [ ] `.env.example` only contains placeholders
- [ ] No hardcoded API keys in code: `git grep -i "mk_" "*.py" "*.ts" "*.js"`
- [ ] All dependencies reviewed for known vulnerabilities (e.g., using `pip audit`, `npm audit`)
- [ ] All links in documentation and code point to legitimate, verified sources
- [ ] Docker images used are from trusted, official sources and have been reviewed for vulnerabilities
- [ ] All contributors have reviewed and agreed to the project's contribution and security guidelines

---

## Maintainer Enforcement Actions

Maintainers reserve the right to take the following actions against prohibited content or behavior:

- **Remove** pull requests, issues, or comments containing malicious code, scam content, or phishing attempts
- **Ban** contributors who engage in social engineering, unauthorized fundraising, or bounty fraud
- **Report** malicious activity to GitHub Trust & Safety and relevant authorities
- **Close** issues or pull requests that violate these security guidelines without further discussion