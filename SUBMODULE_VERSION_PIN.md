# Hummingbot Submodule Version Management

## Current Pinned Version

**Commit:** `8f25258790b867677402d26204e1f098a280435d`
**Date:** 2025-11-27
**Description:** Merge pull request #62 - Fix errors deploy prod

This commit includes all custom funding arbitrage strategy code and critical bug fixes.

## Why Pin the Submodule Version?

1. **Stability**: Prevents unexpected breakages from upstream Hummingbot changes
2. **Reproducibility**: Ensures all team members and deployments use the same code version
3. **Testing**: Allows thorough testing before upgrading to newer versions
4. **Rollback**: Makes it easy to revert if a new version causes issues

## How to Maintain the Pinned Version

### Current Setup

The `hummingbot/` directory is a git submodule pointing to:
- **Repository:** https://github.com/hummingbot/hummingbot.git
- **Pinned Commit:** 8f25258790b867677402d26204e1f098a280435d

### Verification

To verify you're on the correct pinned version:

```bash
cd hummingbot
git rev-parse HEAD
# Should output: 8f25258790b867677402d26204e1f098a280435d

# Verify no uncommitted changes
git status
# Should show: nothing to commit, working tree clean
```

### If Submodule Gets Accidentally Updated

If someone runs `git submodule update --remote` or pulls a different commit:

```bash
# Reset to pinned version
cd hummingbot
git checkout 8f25258790b867677402d26204e1f098a280435d
cd ..

# Commit the reset
git add hummingbot
git commit -m "Reset hummingbot submodule to pinned version 8f252587"
```

## Updating to a New Version (When Ready)

**⚠️ IMPORTANT: Only update after thorough testing in development environment!**

### Step 1: Test New Version

```bash
# Create a test branch
git checkout -b test-hummingbot-update

# Update submodule to latest
cd hummingbot
git fetch origin
git checkout <new-commit-hash>  # or origin/main
cd ..

# Stage the update
git add hummingbot
git commit -m "Test: Update hummingbot to <new-commit-hash>"

# Run comprehensive tests
python -m pytest tests/
# Run paper trading for 24-72 hours
# Monitor for errors and issues
```

### Step 2: If Tests Pass, Update Pin

```bash
# Merge test branch to main
git checkout main
git merge test-hummingbot-update

# Update this document
# Edit SUBMODULE_VERSION_PIN.md with new commit hash and date
git add SUBMODULE_VERSION_PIN.md
git commit -m "Update hummingbot submodule pin to <new-commit-hash>"

git push origin main
```

### Step 3: If Tests Fail, Revert

```bash
# Delete test branch
git checkout main
git branch -D test-hummingbot-update

# Submodule remains on old pinned version
```

## Production Deployment Best Practices

### For Docker Deployments

In your Dockerfile or deployment script:

```dockerfile
# Clone the repo
RUN git clone https://github.com/DaniilMusin/funding_arbitrage_bot_multiple.git
WORKDIR /funding_arbitrage_bot_multiple

# Initialize and update submodule to pinned version
RUN git submodule init
RUN git submodule update  # This will use the pinned commit

# Verify we're on the right version
RUN cd hummingbot && git rev-parse HEAD | grep 8f25258790b867677402d26204e1f098a280435d
```

### For Manual Deployments

```bash
# Clone the repository
git clone https://github.com/DaniilMusin/funding_arbitrage_bot_multiple.git
cd funding_arbitrage_bot_multiple

# Initialize submodule
git submodule init

# Update to pinned version (will use commit from .gitmodules)
git submodule update

# IMPORTANT: Never run --remote flag in production!
# git submodule update --remote  # ❌ DON'T DO THIS - will update to latest

# Verify correct version
cd hummingbot
git rev-parse HEAD  # Should be 8f25258790b867677402d26204e1f098a280435d
```

## Version History

| Date       | Commit   | Description                                    | Reason for Update |
|------------|----------|------------------------------------------------|-------------------|
| 2025-11-27 | 8f252587 | Merge PR #62 - Fix errors deploy prod         | Initial pin       |

## Emergency Rollback

If you need to emergency rollback to this version:

```bash
cd hummingbot
git checkout 8f25258790b867677402d26204e1f098a280435d
cd ..
git add hummingbot
git commit -m "EMERGENCY: Rollback hummingbot to known good version 8f252587"
git push origin main

# Redeploy immediately
```

## Notes

- **DO NOT** modify files inside `hummingbot/` directory directly unless:
  1. You're on a dedicated development branch
  2. Changes are thoroughly tested
  3. Changes are documented and committed to the submodule repo first

- **ALWAYS** test submodule updates in a non-production environment first

- **COMMUNICATE** any submodule version updates to the entire team

- **DOCUMENT** the reason for each version change in the Version History table above
