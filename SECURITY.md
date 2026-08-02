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

This section documents the migration adapter for transitioning from Claude-based configurations to Memanto OKF Bundle format.

### Overview

The migration adapter provides a seamless transition path for users moving from Claude AI integrations to the Memanto OKF Bundle system. This ensures continuity of service while adopting the new architecture.

### Migration Steps

#### 1. Export Claude Configuration

```bash
# Export existing Claude configuration
memanto migrate export-claude --output claude_config.json

# Verify export integrity
memanto migrate verify --file claude_config.json
```

#### 2. Convert to Memanto OKF Bundle Format

```bash
# Run the migration adapter
memanto migrate convert \
  --input claude_config.json \
  --output memanto_bundle.okf \
  --adapter claude-to-memanto

# Validate the converted bundle
memanto migrate validate --bundle memanto_bundle.okf
```

#### 3. Import into Memanto

```bash
# Import the OKF bundle
memanto bundle import --file memanto_bundle.okf

# Test the imported configuration
memanto bundle test --bundle-id <bundle_id>
```

### Configuration Mapping

| Claude Parameter | Memanto OKF Field | Notes |
|-----------------|-------------------|-------|
| `model` | `model_id` | See supported models list |
| `max_tokens` | `token_limit` | Direct mapping |
| `temperature` | `creativity_index` | Range: 0.0–1.0 |
| `system` | `system_prompt` | Direct mapping |
| `messages` | `conversation_history` | Format conversion required |
| `api_key` | `auth.api_key` | Use `mk_` prefixed key |

### Security Considerations During Migration

- **Never expose API keys** during migration scripts
- Use environment variables for all credentials:
  ```bash
  export CLAUDE_API_KEY=your_claude_key
  export MOORCHEH_API_KEY=mk_your_moorcheh_key
  memanto migrate convert --use-env-credentials
  ```
- **Rotate Claude API keys** after successful migration
- **Verify .gitignore** excludes all exported configuration files containing credentials
- Add migration artifacts to `.gitignore`:
  ```bash
  echo "claude_config.json" >> .gitignore
  echo "memanto_bundle.okf" >> .gitignore
  ```

### Rollback Procedure

If migration fails or produces unexpected results:

```bash
# Restore previous Claude configuration
memanto migrate rollback --snapshot <snapshot_id>

# Verify rollback success
memanto migrate status
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
- [ ] Migration artifacts excluded from git: `claude_config.json`, `memanto_bundle.okf`
- [ ] All credentials rotated after migration completion
- [ ] Migration adapter scripts do not log sensitive values
- [ ] Post-migration validation completed successfully