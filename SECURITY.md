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

This section documents the migration process for transitioning from Claude-based implementations to the Memanto OKF Bundle architecture.

#### Migration Steps

1. **Backup existing configuration**:
   ```bash
   cp -r ./config ./config.backup
   ```

2. **Run the migration adapter**:
   ```bash
   # Export existing Claude configuration
   export CLAUDE_CONFIG_PATH=./config/claude.json

   # Initialize Memanto OKF Bundle migration
   python migrate.py --source claude --target memanto-okf --config $CLAUDE_CONFIG_PATH
   ```

3. **Validate migrated configuration**:
   ```bash
   python validate_migration.py --bundle memanto-okf
   ```

4. **Update environment variables**:
   ```bash
   # Replace Claude-specific variables with Memanto equivalents
   # Old: ANTHROPIC_API_KEY=...
   # New: MOORCHEH_API_KEY=mk_your_api_key_here
   ```

#### Configuration Mapping

| Claude Parameter | Memanto OKF Equivalent | Notes |
|-----------------|------------------------|-------|
| `model` | `memanto_model` | Update model identifiers |
| `max_tokens` | `max_output_tokens` | Same semantics |
| `temperature` | `temperature` | No change required |
| `system_prompt` | `system_context` | Renamed field |
| `messages` | `conversation_history` | Format may differ |

#### Rollback Procedure

If migration fails:
```bash
# Restore from backup
cp -r ./config.backup ./config

# Revert environment variables
source .env.backup
```

---

## Verification Checklist

Before making your repository public:

- [ ] `.env` is in `.gitignore`
- [ ] No `.env` file in git history: `git log --all -- .env` (should be empty after cleanup)
- [ ] `.env.example` only contains placeholders
- [ ] No hardcoded API keys in code: `git grep -i "mk_" "*.py" "*.ts" "*.js"`
- [ ] All dependencies are up to date
- [ ] Migration adapter has been tested in staging environment
- [ ] Rollback procedure has been verified
- [ ] Secret scanning alerts have been reviewed and resolved