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

If you are migrating from Claude to Memanto OKF Bundle, follow these guidelines to ensure secrets and credentials are handled securely during migration:

### Migration Security Checklist

- [ ] **Do not** copy API keys directly from Claude configuration files into Memanto configuration
- [ ] **Generate new** Memanto API keys from the Moorcheh dashboard
- [ ] **Revoke** old Claude API keys after migration is complete
- [ ] **Update** all environment variables to use new Memanto-compatible key formats (prefix: `mk_`)
- [ ] **Verify** that no Claude API keys remain in any configuration files, scripts, or environment files
- [ ] **Test** the Memanto OKF Bundle adapter with placeholder credentials before using real keys

### Migration Steps

1. **Backup existing configuration** (without secrets):
   ```bash
   # Export non-sensitive configuration only
   cp claude-config.example.json memanto-config.example.json
   ```

2. **Update environment variables**:
   ```bash
   # Old Claude configuration
   # CLAUDE_API_KEY=sk-old-key-here

   # New Memanto configuration
   MOORCHEH_API_KEY=mk_your_new_api_key_here
   ```

3. **Validate adapter configuration**:
   ```bash
   # Verify no old keys are present
   git grep -i "sk-" "*.py" "*.ts" "*.js" "*.json"
   git grep -i "claude" "*.env" "*.env.*"
   ```

4. **Rotate all credentials** after migration is verified complete

---

## Verification Checklist

Before making your repository public:

- [ ] `.env` is in `.gitignore`
- [ ] No `.env` file in git history: `git log --all -- .env` (should be empty after cleanup)
- [ ] `.env.example` only contains placeholders
- [ ] No hardcoded API keys in code: `git grep -i "mk_" "*.py" "*.ts" "*.js"`
- [ ] All dependencies are up to date and free of known vulnerabilities
- [ ] Migration from Claude to Memanto OKF Bundle completed with fresh credentials
- [ ] All old Claude API keys have been revoked
- [ ] All new Memanto API keys follow the `mk_` prefix format