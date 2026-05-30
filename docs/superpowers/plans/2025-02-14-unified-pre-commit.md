# Unified Pre-commit Hook (Root) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up a unified `pre-commit` configuration in the project root to run backend (Ruff) and frontend (ESLint/Prettier) checks on every commit.

**Architecture:** Use the `pre-commit` framework to manage multi-language hooks. Backend hooks use standard Ruff repositories. Frontend hooks are executed via a local hook that calls `npx lint-staged` inside the `frontend` directory to reuse existing configurations.

**Tech Stack:** `pre-commit`, `ruff`, `lint-staged`.

---

### Task 1: Create Pre-commit Configuration

**Files:**
- Create: `.pre-commit-config.yaml`

- [ ] **Step 1: Create .pre-commit-config.yaml in root**

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.4
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
        files: ^backend/
      - id: ruff-format
        files: ^backend/

  - repo: local
    hooks:
      - id: frontend-lint-staged
        name: Frontend Lint Staged
        entry: bash -c "cd frontend && npx lint-staged"
        language: system
        files: ^frontend/
        pass_filenames: false
```

- [ ] **Step 2: Commit configuration file**

```bash
git add .pre-commit-config.yaml
git commit -m "chore: add .pre-commit-config.yaml"
```

### Task 2: Install and Run Pre-commit

**Files:**
- Modify: `.git/hooks/pre-commit` (via pre-commit install)

- [ ] **Step 1: Install pre-commit hooks**

Run: `source backend/venv/bin/activate && pre-commit install`
Expected: "pre-commit installed at .git/hooks/pre-commit"

- [ ] **Step 2: Run pre-commit on all files**

Run: `source backend/venv/bin/activate && pre-commit run --all-files`
Expected: Success (or automated fixes applied)

- [ ] **Step 3: Commit any automated fixes**

If any files were changed by the hooks:
```bash
git add .
git commit -m "chore: run pre-commit on all files"
```
