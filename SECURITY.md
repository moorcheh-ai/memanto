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

### Overview

This section documents the migration adapter for transitioning from Claude-based configurations to Memanto OKF Bundle format.

### Migration Steps

1. **Backup existing configuration** before starting migration
2. **Export Claude configuration** using the provided export tools
3. **Run the migration adapter** to convert to Memanto OKF Bundle format
4. **Validate the migrated configuration** using the validation checklist
5. **Test in staging environment** before deploying to production

### Migration Adapter Usage

```bash
# Export Claude configuration
export CLAUDE_CONFIG_PATH=/path/to/claude/config

# Run migration adapter
python migrate.py --source claude --target memanto-okf --config $CLAUDE_CONFIG_PATH

# Validate migration output
python validate.py --config /path/to/memanto/okf/bundle
```

### Configuration Mapping

| Claude Parameter | Memanto OKF Bundle Parameter | Notes |
|-----------------|------------------------------|-------|
| `api_key` | `MOORCHEH_API_KEY` | Requires new Moorcheh API key |
| `model` | `okf_model` | See supported models list |
| `max_tokens` | `okf_max_tokens` | Same format |
| `temperature` | `okf_temperature` | Same format |

### Post-Migration Verification

After migration, verify:
- [ ] All API keys have been rotated and updated
- [ ] OKF Bundle configuration is valid
- [ ] Staging environment tests pass
- [ ] Production deployment checklist completed

---

## Verification Checklist

Before making your repository public:

- [ ] `.env` is in `.gitignore`
- [ ] No `.env` file in git history: `git log --all -- .env` (should be empty after cleanup)
- [ ] `.env.example` only contains placeholders
- [ ] No hardcoded API keys in code: `git grep -i "mk_" "*.py" "*.ts" "*.js"`
- [ ] All dependencies are up to date
- [ ] Security policy is reviewed and current
- [ ] Migration adapter has been tested in staging environment
- [ ] All secrets have been rotated after migration