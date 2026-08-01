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

## Claude to Memanto OKF Bundle Migration Guide

This section documents the migration process for moving from Claude to Memanto OKF Bundle.

### Configuration Conversion

When migrating from Claude to Memanto OKF Bundle, update your configuration as follows:

```bash
# Old Claude configuration
ANTHROPIC_API_KEY=sk-ant-your-key-here
MODEL=claude-3-opus-20240229

# New Memanto OKF Bundle configuration
MOORCHEH_API_KEY=mk_your_api_key_here
MODEL=memanto-okf-bundle
```

### Credential Replacement

1. **Obtain Memanto OKF Bundle credentials** from the Moorcheh dashboard
2. **Replace Claude API keys** with Moorcheh API keys (format: `mk_...`)
3. **Update all environment files** and secret managers with new credentials
4. **Revoke old Claude API keys** after successful migration

### Validation Steps

After migration, validate your setup:

```bash
# Verify new API key is set
echo $MOORCHEH_API_KEY | grep -c "^mk_"

# Test connectivity
curl -H "Authorization: Bearer $MOORCHEH_API_KEY" \
  https://api.moorcheh.ai/v1/health

# Run integration tests
npm test
```

### Security Precautions During Migration

- **Never store both old and new credentials** in the same `.env` file simultaneously
- **Audit all locations** where Claude credentials may be stored (CI/CD, cloud secrets, local files)
- **Do not log API keys** during migration scripts
- **Use separate migration environment** to avoid production disruption

```bash
# Scan for any remaining Claude credentials
git grep -r "sk-ant-" --include="*.env*" --include="*.json" --include="*.yaml"
git grep -r "anthropic" --include="*.py" --include="*.ts" --include="*.js"
```

### Rollback Procedure

If migration fails, rollback safely:

1. **Restore Claude credentials** from your secure backup
2. **Revert configuration files** to previous state:
   ```bash
   git checkout HEAD~1 -- .env.example
   ```
3. **Verify rollback** by running existing test suite
4. **Document the failure** before attempting migration again

### Verification Checklist

After completing migration:

- [ ] All Claude API keys (`sk-ant-*`) removed from all environments
- [ ] Moorcheh API keys (`mk_*`) configured in all environments
- [ ] No Claude credentials in git history: `git grep -r "sk-ant-" $(git rev-list --all)`
- [ ] Integration tests passing with new credentials
- [ ] Monitoring and alerting updated for new service endpoints
- [ ] Team notified of credential changes
- [ ] Old Claude API keys revoked in Anthropic dashboard

---

## Verification Checklist

Before making your repository public:

- [ ] `.env` is in `.gitignore`
- [ ] No `.env` file in git history: `git log --all -- .env` (should be empty after cleanup)
- [ ] `.env.example` only contains placeholders
- [ ] No hardcoded API keys in code: `git grep -i "mk_" "*.py" "*.ts" "*.js"`
- [ ] No hardcoded Claude API keys in code: `git grep -i "sk-ant-" "*.py" "*.ts" "*.js"`
- [ ] All dependencies are up to date
- [ ] Security scanning is enabled on the repository
- [ ] Access controls are properly configured