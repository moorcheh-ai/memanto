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

### Overview

The Claude to Memanto OKF Bundle Migration Adapter enables seamless migration of configurations, conversation history, and API integrations from Claude-based setups to the Memanto OKF Bundle format.

### Migration Steps

1. **Export Claude Configuration**
   ```bash
   # Export existing Claude configuration
   memanto-migrate export --source claude --output ./migration-bundle.json
   ```

2. **Validate Migration Bundle**
   ```bash
   # Validate the exported bundle before import
   memanto-migrate validate --bundle ./migration-bundle.json
   ```

3. **Import to Memanto OKF Bundle**
   ```bash
   # Import configuration into Memanto OKF Bundle
   memanto-migrate import --bundle ./migration-bundle.json --target memanto-okf
   ```

4. **Verify Migration**
   ```bash
   # Verify all resources migrated correctly
   memanto-migrate verify --target memanto-okf
   ```

### Security Considerations During Migration

- **Never store migration bundles in version control** - they may contain sensitive configuration data
- **Rotate API keys** after migration is complete
- **Validate all endpoints** are updated to point to Memanto services
- **Review permissions** assigned to migrated API keys

### Environment Variable Mapping

| Claude Variable | Memanto OKF Variable | Notes |
|----------------|---------------------|-------|
| `ANTHROPIC_API_KEY` | `MOORCHEH_API_KEY` | Rotate key after migration |
| `CLAUDE_MODEL` | `MEMANTO_MODEL` | Check model compatibility |
| `CLAUDE_MAX_TOKENS` | `MEMANTO_MAX_TOKENS` | Verify token limits |
| `CLAUDE_BASE_URL` | `MOORCHEH_BASE_URL` | Update to Memanto endpoint |

### Rollback Procedure

If migration fails or produces unexpected results:

```bash
# Restore previous Claude configuration
memanto-migrate rollback --bundle ./migration-bundle.json

# Verify rollback completed successfully
memanto-migrate verify --target claude
```

---

## Verification Checklist

Before making your repository public:

- [ ] `.env` is in `.gitignore`
- [ ] No `.env` file in git history: `git log --all -- .env` (should be empty after cleanup)
- [ ] `.env.example` only contains placeholders
- [ ] No hardcoded API keys in code: `git grep -i "mk_" "*.py" "*.ts" "*.js"`
- [ ] All dependencies are up to date and free of known vulnerabilities
- [ ] Migration bundles are excluded from version control
- [ ] Post-migration API keys have been rotated
- [ ] All secrets are stored in appropriate secret management systems
- [ ] Access logs reviewed for any unauthorized access during migration period