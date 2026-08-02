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

This section documents the migration adapter for transitioning from Claude-based configurations to the Memanto OKF Bundle format.

### Overview

The migration adapter provides a structured pathway for moving existing Claude AI integrations to the Memanto OKF Bundle format, ensuring compatibility and preserving functionality during the transition.

### Migration Steps

#### 1. Pre-Migration Checklist

Before beginning migration:

- [ ] Back up all existing Claude configuration files
- [ ] Document all active API endpoints and integrations
- [ ] Export current conversation history if needed
- [ ] Verify Memanto OKF Bundle version compatibility
- [ ] Ensure all environment variables are documented

#### 2. Configuration Mapping

Map Claude configurations to Memanto OKF Bundle equivalents:

| Claude Config | Memanto OKF Bundle | Notes |
|--------------|-------------------|-------|
| `ANTHROPIC_API_KEY` | `MOORCHEH_API_KEY` | Rotate key after migration |
| `claude-3-*` model refs | Memanto model identifiers | Check supported models |
| Claude system prompts | Memanto system context | May require reformatting |
| Claude tool definitions | OKF Bundle tool schemas | Update schema format |

#### 3. Running the Migration Adapter

```bash
# Install migration dependencies
pip install memanto-okf-bundle

# Run migration adapter
python -m memanto.migration.claude_adapter \
  --source ./claude-config \
  --target ./memanto-config \
  --validate

# Verify migration output
python -m memanto.migration.validate --config ./memanto-config
```

#### 4. Post-Migration Validation

After migration:

```bash
# Test Memanto OKF Bundle connectivity
curl -H "Authorization: Bearer $MOORCHEH_API_KEY" \
  https://api.moorcheh.ai/v1/health

# Validate bundle integrity
python -m memanto.okf.validate --bundle ./memanto-config/bundle.okf
```

### Security Considerations During Migration

- **Rotate all API keys** after migration is complete
- **Do not reuse** Claude API keys in Memanto configuration
- **Audit logs** for any credential exposure during migration
- **Update .gitignore** to exclude new Memanto config files with secrets
- **Verify** no Claude credentials are embedded in migrated configurations

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
- [ ] Migration adapter configurations do not contain real credentials
- [ ] Post-migration API keys have been rotated
- [ ] All secrets are stored in environment variables or secret managers