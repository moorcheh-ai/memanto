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

## Verification Checklist

Before making your repository public:

- [ ] `.env` is in `.gitignore`
- [ ] No `.env` file in git history: `git log --all -- .env` (should be empty after cleanup)
- [ ] `.env.example` only contains placeholders
- [ ] No hardcoded API keys in code: `git grep -i "mk_" "*.py" "*.ts" "*.js"`
- [ ] All documentation examples use placeholders
- [ ] GitHub secret scanning alerts reviewed and addressed

---

## Security Features in MEMANTO

MEMANTO implements multiple security layers:

### 1. Authentication & Authorization
- Server-owned `MOORCHEH_API_KEY` required at startup for backend access
- Client `X-Session-Token` required for session-scoped and memory endpoints
- Tenant ID derived from authenticated principal (never from request body)
- Multi-tenant isolation enforced at namespace level

### 2. Rate Limiting
- Per-tenant quotas prevent abuse
- Configurable limits: 60 writes/min, 120 reads/min

### 3. Input Validation
- Content size limits (10KB text, 5KB metadata)
- Anti-poisoning validation for facts and preferences
- Pydantic model validation for all requests

### 4. Secure Defaults
- HTTPS enforced in production
- CORS properly configured
- Structured logging with PII redaction
- Safe deletion with audit trail

For detailed security architecture, see [SECURITY_ISOLATION_ONE_PAGER.md](SECURITY_ISOLATION_ONE_PAGER.md).

---

## Production Security Checklist

### Environment Configuration
- [ ] Use environment-specific API keys (dev/staging/prod)
- [ ] Rotate keys regularly (quarterly minimum)
- [ ] Use secret management tools (not .env files) in production
- [ ] Enable HTTPS/TLS for all endpoints
- [ ] Configure CORS with specific origins (not `*`)

### Monitoring & Auditing
- [ ] Enable structured logging
- [ ] Monitor for unusual API activity
- [ ] Set up alerts for rate limit violations
- [ ] Regular security audits of access logs
- [ ] Implement log aggregation (ELK, Datadog, etc.)

### Network Security
- [ ] Deploy behind API gateway or reverse proxy
- [ ] Use VPC/private networks when possible
- [ ] Implement DDoS protection
- [ ] Regular vulnerability scanning
- [ ] Keep dependencies updated

---

## Dependencies Security

### Regular Updates
```bash
# Check for security vulnerabilities
pip install safety
safety check

# Update dependencies
pip list --outdated
pip install --upgrade <package>
```

### Automated Scanning
- GitHub Dependabot enabled for this repository
- Review and merge security PRs promptly
- Test thoroughly before deploying dependency updates

---

## Contact

For security questions or concerns:
- **General**: Dr. Majid Fekri, CTO Moorcheh.ai
- **Security Issues**: support@moorcheh.ai
- **Moorcheh Platform**: https://moorcheh.ai/security

---

**Last Updated**: March 2026
