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

## Migration Adapter: Claude to Memanto OKF Bundle

### Overview

The Claude to Memanto OKF Bundle Migration Adapter provides a structured pathway for migrating configurations, workflows, and data from Claude-based integrations to the Memanto OKF Bundle format.

### Migration Steps

#### 1. Pre-Migration Checklist

Before beginning migration:

- [ ] Back up all existing Claude configuration files
- [ ] Document current Claude API usage and endpoints
- [ ] Ensure Memanto OKF Bundle dependencies are installed
- [ ] Verify Moorcheh API key is available and valid
- [ ] Review Memanto OKF Bundle schema documentation

#### 2. Configuration Mapping

Map Claude configuration parameters to Memanto OKF Bundle equivalents:

| Claude Parameter | Memanto OKF Bundle Parameter | Notes |
|-----------------|------------------------------|-------|
| `model` | `okf_model` | Use Memanto model identifiers |
| `max_tokens` | `okf_max_output` | Same unit (tokens) |
| `temperature` | `okf_temperature` | Same scale (0.0–1.0) |
| `system` | `okf_system_prompt` | Direct mapping |
| `messages` | `okf_conversation` | Format conversion required |
| `api_key` | `MOORCHEH_API_KEY` | Store in `.env`, never hardcode |

#### 3. Message Format Conversion

Claude messages use the following format:
```json
{
  "messages": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there!"}
  ]
}
```

Memanto OKF Bundle format:
```json
{
  "okf_conversation": [
    {"okf_role": "user", "okf_content": "Hello"},
    {"okf_role": "assistant", "okf_content": "Hi there!"}
  ]
}
```

#### 4. Running the Migration

```bash
# Install migration dependencies
pip install memanto-okf-bundle

# Run migration adapter
python -m memanto.migration.claude_adapter \
  --input claude_config.json \
  --output memanto_okf_config.json \
  --validate

# Verify migration output
python -m memanto.migration.validate --config memanto_okf_config.json
```

#### 5. Post-Migration Validation

After migration, verify:

- [ ] All message formats converted correctly
- [ ] System prompts preserved and functional
- [ ] API authentication works with Moorcheh API key
- [ ] Response formats match expected OKF Bundle schema
- [ ] No sensitive data exposed in configuration files

### Security Considerations for Migration

- **Never** include Claude API keys in migration scripts
- **Always** use environment variables for both Claude and Moorcheh credentials
- **Audit** migrated configuration files before committing to version control
- **Rotate** all API keys after migration is complete

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
- [ ] Post-migration validation has been completed successfully