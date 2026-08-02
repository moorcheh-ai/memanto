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

## Migration Adapter: Claude to Memanto OKF Bundle

If you are migrating from Claude to Memanto OKF Bundle, follow these guidelines to ensure secrets and credentials are handled securely during migration:

### Migration Security Checklist

- [ ] Review all existing Claude API keys and rotate before migration
- [ ] Do not reuse Claude API keys in Memanto configuration
- [ ] Generate new Memanto API keys (`mk_` prefix) from the Moorcheh dashboard
- [ ] Update all environment variables to use Memanto equivalents
- [ ] Validate that no Claude credentials remain in any configuration files
- [ ] Run a secrets scan after migration: `git grep -rn "sk-" --include="*.py" --include="*.ts" --include="*.js" --include="*.env"`

### Environment Variable Mapping

| Claude Variable | Memanto Variable | Notes |
|----------------|-----------------|-------|
| `ANTHROPIC_API_KEY` | `MOORCHEH_API_KEY` | Generate new key from dashboard |
| `CLAUDE_MODEL` | `MEMANTO_MODEL` | Update model identifiers |
| `CLAUDE_BASE_URL` | `MOORCHEH_BASE_URL` | Update endpoint URLs |

### Adapter Configuration Example

```bash
# .env.example for Memanto OKF Bundle (safe to commit)
MOORCHEH_API_KEY=mk_your_api_key_here
MEMANTO_MODEL=memanto-default
MOORCHEH_BASE_URL=https://api.moorcheh.ai

# .env (NEVER commit - contains real credentials)
MOORCHEH_API_KEY=mk_your_real_key_here
MEMANTO_MODEL=memanto-default
MOORCHEH_BASE_URL=https://api.moorcheh.ai
```

---

## Verification Checklist

Before making your repository public:

- [ ] `.env` is in `.gitignore`
- [ ] No `.env` file in git history: `git log --all -- .env` (should be empty after cleanup)
- [ ] `.env.example` only contains placeholders
- [ ] No hardcoded API keys in code: `git grep -i "mk_" "*.py" "*.ts" "*.js"`
- [ ] No Claude/Anthropic API keys remaining after migration: `git grep -i "sk-ant" "*.py" "*.ts" "*.js"`
- [ ] All dependencies updated to Memanto OKF Bundle versions
- [ ] Secret scanning alerts reviewed and resolved
- [ ] Migration adapter configuration validated in staging environment before production deployment