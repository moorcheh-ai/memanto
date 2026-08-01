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

## Claude-to-Memanto OKF Bundle Migration

If you are migrating from a Claude-based configuration to a Memanto OKF Bundle, follow these steps to ensure a secure and correct transition.

### Configuration

1. Export your existing Claude configuration to a compatible OKF Bundle format:
   ```bash
   memanto migrate --from claude --to okf-bundle --config claude_config.json --output memanto_bundle.okf
   ```
2. Update your environment variables to reference Memanto credentials instead of Claude API keys:
   ```bash
   # Remove old Claude credentials
   # ANTHROPIC_API_KEY=sk_...  <-- remove this

   # Add Memanto credentials
   MOORCHEH_API_KEY=mk_your_api_key_here
   ```

### Validation

After migration, validate the OKF Bundle integrity:
```bash
memanto validate --bundle memanto_bundle.okf
```

Ensure all endpoints, model references, and prompt templates have been correctly translated from Claude format to Memanto OKF format.

### Security Precautions

- **Never** include Claude API keys (`sk_ant_...`) or Memanto API keys (`mk_...`) in the bundle file itself.
- Store all credentials exclusively in environment variables or a secrets manager.
- Audit the migrated bundle for any embedded secrets before committing:
  ```bash
  git grep -i "sk_ant_\|mk_" "*.okf" "*.json"
  ```
- Rotate both your Claude and Memanto API keys after migration is complete.

### Rollback

If migration fails or produces unexpected results:

1. Restore your previous Claude configuration from backup.
2. Revert environment variables to Claude credentials.
3. Report the issue to **support@moorcheh.ai** with subject: `[MEMANTO Migration] OKF Bundle Issue`.

---

## Verification Checklist

Before making your repository public:

- [ ] `.env` is in `.gitignore`
- [ ] No `.env` file in git history: `git log --all -- .env` (should be empty after cleanup)
- [ ] `.env.example` only contains placeholders
- [ ] No hardcoded API keys in code: `git grep -i "mk_" "*.py" "*.ts" "*.js"`
- [ ] No hardcoded Claude API keys in code: `git grep -i "sk_ant_" "*.py" "*.ts" "*.js"`
- [ ] All OKF Bundle files are free of embedded credentials
- [ ] Migration bundle validated with `memanto validate`
- [ ] All secrets rotated after migration
- [ ] GitHub secret scanning alerts reviewed and resolved