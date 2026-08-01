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

## Claude to Memanto OKF Bundle Migration Adapter

### Overview

The migration adapter facilitates seamless transition from Claude-based configurations to the Memanto OKF Bundle format. This process ensures that all existing integrations, API references, and workflow definitions are properly translated without data loss.

### Migration Steps

#### 1. Pre-Migration Checklist

Before initiating the migration:

- [ ] Back up all existing Claude configuration files
- [ ] Document current API endpoints and authentication methods
- [ ] Verify Memanto OKF Bundle version compatibility
- [ ] Ensure all dependent services are updated

#### 2. Configuration Mapping

| Claude Field | Memanto OKF Field | Notes |
|---|---|---|
| `claude_api_key` | `MOORCHEH_API_KEY` | Prefix changes to `mk_` |
| `claude_model` | `memanto_model` | Map model names accordingly |
| `claude_endpoint` | `moorcheh_endpoint` | Update base URLs |
| `claude_max_tokens` | `memanto_max_tokens` | Same format |
| `claude_temperature` | `memanto_temperature` | Same format |

#### 3. Running the Migration

```bash
# Install migration tooling
pip install memanto-migration-adapter

# Run dry-run first
memanto-migrate --source claude_config.json \
                --target memanto_okf_bundle.json \
                --dry-run

# Execute migration
memanto-migrate --source claude_config.json \
                --target memanto_okf_bundle.json \
                --validate
```

#### 4. Post-Migration Validation

```bash
# Validate migrated bundle
memanto-validate --bundle memanto_okf_bundle.json

# Test connectivity
memanto-test --config memanto_okf_bundle.json --ping

# Verify all endpoints
memanto-test --config memanto_okf_bundle.json --full-check
```

#### 5. Security Considerations During Migration

- **Never** include real API keys in migration configuration files
- Store migration artifacts in a secure, temporary location
- Delete migration logs after successful validation
- Rotate all API keys after migration is complete
- Audit access logs for any unauthorized access during migration window

#### 6. Rollback Procedure

If migration fails:

```bash
# Restore from backup
memanto-migrate --rollback --backup-dir ./pre_migration_backup

# Verify restoration
memanto-validate --legacy --config claude_config.json
```

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
- [ ] All dependencies are up to date and free of known vulnerabilities
- [ ] Migration adapter configuration files do not contain real credentials
- [ ] Post-migration API keys have been rotated
- [ ] Migration artifacts and temporary files have been securely deleted