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

## Claude to Memanto OKF Bundle Migration

### Migration Adapter Overview

If you are migrating from Claude-based configurations to Memanto OKF Bundle, follow these steps to ensure a secure and smooth transition:

#### 1. Pre-Migration Checklist

- [ ] Back up all existing Claude API keys and configurations
- [ ] Document all active integrations using Claude endpoints
- [ ] Review current `.env` files for Claude-specific variables
- [ ] Ensure Memanto OKF Bundle credentials are provisioned

#### 2. Environment Variable Mapping

Map your existing Claude environment variables to Memanto equivalents:

```bash
# Claude (legacy)
ANTHROPIC_API_KEY=sk-ant-your_claude_key_here
CLAUDE_MODEL=claude-3-opus-20240229
CLAUDE_MAX_TOKENS=4096

# Memanto OKF Bundle (new)
MOORCHEH_API_KEY=mk_your_api_key_here
MEMANTO_MODEL=memanto-okf-bundle-v1
MEMANTO_MAX_TOKENS=4096
```

#### 3. Migration Adapter Configuration

The migration adapter handles translation between Claude and Memanto API formats:

```bash
# Enable migration adapter in .env
MIGRATION_ADAPTER_ENABLED=true
MIGRATION_SOURCE=claude
MIGRATION_TARGET=memanto-okf-bundle

# Legacy Claude fallback (optional, for gradual migration)
CLAUDE_FALLBACK_ENABLED=false
```

#### 4. Secure Key Rotation During Migration

1. **Provision new Memanto OKF Bundle keys** from the Moorcheh dashboard
2. **Add new keys to your secrets manager** before removing old Claude keys
3. **Test connectivity** with new Memanto credentials before cutover
4. **Revoke Claude API keys** after successful migration verification
5. **Update all deployment environments** (staging, production) in sequence

#### 5. Rollback Procedure

If migration fails, revert using:

```bash
# Restore Claude configuration
MIGRATION_ADAPTER_ENABLED=false
ANTHROPIC_API_KEY=sk-ant-your_backup_claude_key_here

# Redeploy with legacy configuration
docker-compose down && docker-compose up -d
```

#### 6. Security Considerations During Migration

- **Never** store both Claude and Memanto keys in the same `.env` file simultaneously in production
- Use separate secret manager entries for migration period credentials
- Audit logs should be enabled during migration to track any authentication failures
- Rotate all migrated keys 30 days after successful migration completion

---

## Verification Checklist

Before making your repository public:

- [ ] `.env` is in `.gitignore`
- [ ] No `.env` file in git history: `git log --all -- .env` (should be empty after cleanup)
- [ ] `.env.example` only contains placeholders
- [ ] No hardcoded API keys in code: `git grep -i "mk_" "*.py" "*.ts" "*.js"`
- [ ] No hardcoded Claude API keys in code: `git grep -i "sk-ant-" "*.py" "*.ts" "*.js"`
- [ ] Migration adapter configuration reviewed and secured
- [ ] All deprecated Claude credentials have been rotated and revoked
- [ ] All deployment environments updated with Memanto OKF Bundle credentials
- [ ] Secret scanning alerts reviewed and resolved
- [ ] `.gitignore` verified to exclude all credential files