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
- [ ] All dependencies are up to date: `pip audit` or `npm audit`
- [ ] Docker images do not contain secrets
- [ ] CI/CD environment variables are stored as secrets, not plaintext

---

## Claude to Memanto OKF Bundle Migration Guide

This section documents the migration process from Claude-based configurations to the Memanto OKF Bundle.

### Overview

The Memanto OKF Bundle Migration Adapter provides a structured path for transitioning existing Claude integrations to the Memanto platform while maintaining security best practices throughout the migration process.

### Configuration Conversion

When migrating from Claude to Memanto OKF Bundle, update your configuration as follows:

**Before (Claude configuration):**
```bash
# Old Claude credentials (to be removed)
ANTHROPIC_API_KEY=sk-ant-your-claude-key-here
CLAUDE_MODEL=claude-3-opus-20240229
```

**After (Memanto OKF Bundle configuration):**
```bash
# New Memanto credentials
MOORCHEH_API_KEY=mk_your_api_key_here
MEMANTO_OKF_BUNDLE=true
MEMANTO_MODEL=memanto-okf-bundle-v1
```

### Credential Replacement

⚠️ **CRITICAL SECURITY STEPS during migration:**

1. **Revoke Claude/Anthropic API keys** immediately after migration is complete
2. **Never store both old and new credentials** in the same `.env` file simultaneously
3. **Generate fresh Memanto credentials** from the Moorcheh dashboard
4. **Audit all configuration files** to ensure no Claude credentials remain:
   ```bash
   # Search for any remaining Claude/Anthropic credentials
   git grep -i "sk-ant-" "*.py" "*.ts" "*.js" "*.env*"
   git grep -i "anthropic" "*.py" "*.ts" "*.js"
   git grep -i "claude" "*.py" "*.ts" "*.js" "*.yaml" "*.yml"
   ```

### Validation

After migration, validate the new configuration:

```bash
# Verify Memanto OKF Bundle connectivity
curl -H "Authorization: Bearer $MOORCHEH_API_KEY" \
     https://api.moorcheh.ai/v1/health

# Confirm no Claude credentials are active
# Check Anthropic dashboard and revoke any remaining keys
```

### Rollback Procedure

If migration needs to be rolled back:

1. **Do not reuse revoked Claude credentials** - generate new ones if needed
2. Restore previous configuration from a secure backup
3. Document the reason for rollback
4. Re-audit credentials before attempting migration again

### Post-Migration Verification

- [ ] All Claude/Anthropic API keys have been revoked in the Anthropic console
- [ ] Memanto OKF Bundle credentials are active and validated
- [ ] Application functionality verified with new credentials
- [ ] No residual Claude configuration in codebase
- [ ] Logs audited to confirm no credential leakage during migration
- [ ] `.env.example` updated to reflect Memanto OKF Bundle configuration only

### Migration Security Checklist

- [ ] Old Claude credentials removed from all `.env` files
- [ ] Old Claude credentials removed from git history (if ever committed)
- [ ] Claude/Anthropic API keys revoked in external dashboard
- [ ] New Memanto credentials stored only in `.env` (never committed)
- [ ] All dependencies updated to Memanto OKF Bundle compatible versions
- [ ] Security scanning completed on migrated codebase
- [ ] Access controls reviewed and updated for Memanto endpoints
- [ ] Team members notified of credential rotation requirement
- [ ] CI/CD pipeline updated with new Memanto secrets
- [ ] Monitoring and alerting reconfigured for Memanto OKF Bundle endpoints