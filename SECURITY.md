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

## Dependency Security

### Keeping Dependencies Up to Date

Outdated dependencies can introduce vulnerabilities. Follow these practices:

#### Python Dependencies
```bash
# Check for known vulnerabilities
pip install safety
safety check

# Check for outdated packages
pip list --outdated

# Update dependencies
pip install --upgrade <package-name>
```

#### Node.js Dependencies
```bash
# Audit for vulnerabilities
npm audit

# Fix automatically where possible
npm audit fix

# Check for outdated packages
npm outdated
```

#### Automated Dependency Scanning
- Enable **Dependabot** in your GitHub repository settings
- Review and merge security updates promptly
- Pin dependency versions in production to avoid unexpected updates

---

## Container Security

### Docker Image Best Practices

```dockerfile
# Use specific, minimal base images
FROM python:3.11-slim

# Run as non-root user
RUN useradd --create-home appuser
USER appuser

# Do NOT copy .env files into images
COPY . .
# Ensure .dockerignore excludes sensitive files
```

#### .dockerignore (required entries)
```
.env
*.env
.env.*
!.env.example
*.key
*.pem
__pycache__
.git
```

#### Scanning Container Images
```bash
# Scan with Trivy
trivy image your-image-name:tag

# Scan with Docker Scout
docker scout cves your-image-name:tag
```

---

## CI/CD Secret Management

### GitHub Actions

**Never** hardcode secrets in workflow files. Use GitHub Secrets instead:

```yaml
# ✅ Correct - use GitHub Secrets
env:
  MOORCHEH_API_KEY: ${{ secrets.MOORCHEH_API_KEY }}

# ❌ Wrong - never hardcode
env:
  MOORCHEH_API_KEY: mk_abc123real_key_here
```

#### Setting GitHub Secrets
1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Add your secret name and value
4. Reference in workflows using `${{ secrets.SECRET_NAME }}`

#### Audit CI/CD Secrets Regularly
- Remove unused secrets from repository settings
- Rotate secrets on a schedule or after team member departures
- Use environment-scoped secrets for production deployments

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

## Migration Guide: Claude to Memanto OKF Bundle

If you are migrating from a Claude-based configuration to the Memanto OKF Bundle, follow these steps carefully to ensure a secure and complete transition.

### 1. Convert Configurations

Update your configuration files to replace Claude-specific settings with Memanto equivalents:

```bash
# Before (Claude)
AI_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-your-key-here
MODEL=claude-3-opus-20240229

# After (Memanto OKF Bundle)
AI_PROVIDER=memanto
MOORCHEH_API_KEY=mk_your_api_key_here
MODEL=memanto-okf-bundle
```

Review all configuration files, environment variable references, and any hardcoded provider strings in your codebase:

```bash
# Find Claude-specific references
grep -r "claude\|anthropic\|ANTHROPIC" --include="*.py" --include="*.ts" --include="*.js" --include="*.yaml" --include="*.yml" .
```

### 2. Rotate Credentials

During migration, rotate all credentials to ensure old keys are invalidated:

1. **Generate a new Moorcheh API key** from the Moorcheh dashboard
2. **Revoke the old Anthropic API key** from the Anthropic console
3. **Update all environments** (local `.env`, staging, production) with new keys
4. **Update CI/CD secrets** in GitHub Actions, or your CI provider

```bash
# Remove old keys from your .env
# Edit .env and replace ANTHROPIC_API_KEY with MOORCHEH_API_KEY
nano .env

# Verify no old keys remain
grep -i "anthropic\|sk-ant" .env
```

### 3. Validate Changes

After updating configuration, validate the migration:

```bash
# Run the test suite
pytest tests/ -v

# Test API connectivity with the new provider
python -c "from your_module import client; print(client.ping())"

# Check logs for any residual Claude/Anthropic references
grep -r "anthropic\|claude" logs/ 2>/dev/null || echo "No residual references found"
```

Ensure all integration tests pass and that the application communicates correctly with the Memanto OKF Bundle endpoints.

### 4. Roll Back (if needed)

If issues arise during migration, you can roll back to the previous configuration:

```bash
# Restore previous .env from backup
cp .env.backup .env

# Revert code changes
git revert <migration-commit-hash>

# Redeploy previous version
git checkout <previous-stable-tag>
```

Always keep a backup of your working configuration before beginning migration.

### 5. Verify the Migration

After successful migration, complete the following verification steps:

- [ ] All tests pass with the Memanto OKF Bundle provider
- [ ] No `ANTHROPIC_API_KEY` or Claude-related keys remain in any environment
- [ ] Old Anthropic API keys have been revoked
- [ ] New Moorcheh API keys are securely stored and not committed to git
- [ ] CI/CD pipelines use updated secrets
- [ ] Application logs confirm requests are routing to Memanto endpoints
- [ ] `.env.example` is updated to reflect new required variables

---

## Verification Checklist

Before making your repository public:

- [ ] `.env` is in `.gitignore`
- [ ] No `.env` file in git history: `git log --all -- .env` (should be empty after cleanup)
- [ ] `.env.example` only contains placeholders
- [ ] No hardcoded API keys in code: `git grep -i "mk_" "*.py" "*.ts" "*.js"`
- [ ] All dependencies are up to date and free of known vulnerabilities
- [ ] Docker images do not contain `.env` files or sensitive credentials
- [ ] CI/CD secrets are managed via GitHub Secrets, not hardcoded in workflow files
- [ ] Container images have been scanned for vulnerabilities
- [ ] Non-root users are used in Docker containers
- [ ] Dependabot or equivalent automated dependency scanning is enabled
- [ ] If migrating from Claude: all old credentials have been rotated and revoked
- [ ] Migration verification checklist completed (see Migration Guide above)