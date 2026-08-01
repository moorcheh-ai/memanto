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

This section documents the migration adapter for transitioning from Claude-based configurations to the Memanto OKF Bundle format.

### Migration Steps

1. **Export existing Claude configuration**:
   ```bash
   # Export your current Claude bundle configuration
   export CLAUDE_CONFIG_PATH=/path/to/claude/config
   ```

2. **Run the migration adapter**:
   ```bash
   # Execute the OKF bundle migration
   python migrate_okf_bundle.py --source claude --target memanto
   ```

3. **Validate the migrated bundle**:
   ```bash
   # Verify the migration output
   python validate_okf_bundle.py --bundle output/memanto_bundle.okf
   ```

4. **Update environment variables**:
   ```bash
   # Replace Claude-specific variables with Memanto equivalents
   MOORCHEH_API_KEY=mk_your_new_api_key_here
   MEMANTO_BUNDLE_PATH=/path/to/memanto/bundle
   ```

### Configuration Mapping

| Claude Config Key | Memanto OKF Key | Notes |
|---|---|---|
| `CLAUDE_API_KEY` | `MOORCHEH_API_KEY` | Rotate key during migration |
| `CLAUDE_MODEL` | `MEMANTO_MODEL` | Update model identifiers |
| `CLAUDE_ENDPOINT` | `MOORCHEH_ENDPOINT` | Update endpoint URLs |
| `CLAUDE_BUNDLE_PATH` | `MEMANTO_BUNDLE_PATH` | Update bundle paths |

### Security Considerations During Migration

- **Never expose old Claude API keys** during the migration process
- **Rotate all API keys** before and after migration
- **Validate bundle integrity** using checksums before deployment
- **Test in staging environment** before production migration

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
- [ ] Migration adapter has been tested in a non-production environment
- [ ] OKF bundle integrity verified with checksums
- [ ] All Claude-specific credentials have been rotated and replaced with Memanto equivalents