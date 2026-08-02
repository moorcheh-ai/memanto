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

For users migrating from Claude-based integrations to the Memanto OKF Bundle, follow these guidelines to ensure secrets and credentials are handled securely during migration.

### Migration Security Checklist

- [ ] Revoke all Claude API keys after migration is complete
- [ ] Generate new Moorcheh API keys (`mk_` prefix) from the Moorcheh dashboard
- [ ] Update all environment variable references from Claude-specific keys to Moorcheh equivalents
- [ ] Audit all configuration files for leftover Claude credentials
- [ ] Verify no Claude API keys are present in git history post-migration

### Environment Variable Mapping

```bash
# Before migration (Claude)
ANTHROPIC_API_KEY=sk-ant-your_claude_key_here

# After migration (Memanto/Moorcheh)
MOORCHEH_API_KEY=mk_your_api_key_here
```

### OKF Bundle Adapter Configuration

The Memanto OKF Bundle migration adapter handles the translation of Claude-compatible API calls to Moorcheh-native endpoints. Ensure the following during migration:

1. **Never reuse** Claude API keys in the Memanto environment
2. **Validate** all secrets are stored in environment variables, not hardcoded
3. **Test** the adapter in a staging environment before production deployment
4. **Audit logs** for any accidental credential exposure during migration

---

## Verification Checklist

Before making your repository public:

- [ ] `.env` is in `.gitignore`
- [ ] No `.env` file in git history: `git log --all -- .env` (should be empty after cleanup)
- [ ] `.env.example` only contains placeholders
- [ ] No hardcoded API keys in code: `git grep -i "mk_" "*.py" "*.ts" "*.js"`
- [ ] No Claude/Anthropic API keys remaining in codebase: `git grep -i "sk-ant-" "*.py" "*.ts" "*.js"`
- [ ] All deployment configurations use environment variable references only
- [ ] Secret scanning alerts have been reviewed and resolved
- [ ] Migration adapter configuration does not contain hardcoded credentials
- [ ] All contributors have been notified of the new secret management procedures