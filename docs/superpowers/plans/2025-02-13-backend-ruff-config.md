# Backend Configuration (Ruff) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure Ruff for linting and formatting in the backend directory and update dependencies.

**Architecture:** Add a standard `pyproject.toml` configuration for Ruff and ensure it's listed in `requirements.txt`.

**Tech Stack:** Ruff, Python 3.12+

---

### Task 1: Create pyproject.toml

**Files:**
- Create: `backend/pyproject.toml`

- [ ] **Step 1: Create backend/pyproject.toml**

```toml
[tool.ruff]
# Exclude a variety of commonly ignored directories.
exclude = [
    ".bzr",
    ".direnv",
    ".eggs",
    ".git",
    ".git-rewrite",
    ".hg",
    ".ipynb_checkpoints",
    ".mypy_cache",
    ".nox",
    ".pants.d",
    ".pyenv",
    ".pytest_cache",
    ".pytype",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    ".vscode",
    "__pypackages__",
    "_build",
    "buck-out",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "venv",
]

line-length = 88
indent-width = 4
target-version = "py312"

[tool.ruff.lint]
# Enable Pyflakes (`F`) and a subset of the pycodestyle (`E`)  codes by default.
# Unlike Flake8, Ruff doesn't enable pycodestyle warnings (`W`) or
# McCabe complexity (`C901`) by default.
select = ["E4", "E7", "E9", "F", "I"]
ignore = []

# Allow fix for all enabled rules (when `--fix`) is provided.
fixable = ["ALL"]
unfixable = []

# Allow unused variables when underscore-prefixed.
dummy-variable-rgx = "^(_+|(_+[a-zA-Z0-9_]*[a-zA-Z0-9]+?))$"

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
skip-magic-trailing-comma = false
line-ending = "auto"
```

- [ ] **Step 2: Commit pyproject.toml**

```bash
git add backend/pyproject.toml
git commit -m "chore: add ruff configuration for backend"
```

### Task 2: Update requirements.txt

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add ruff to requirements.txt**
Append `ruff==0.1.6` (or current version) to the file.

- [ ] **Step 2: Install ruff**
Run: `pip install ruff` (Assuming venv is managed externally or already active)

- [ ] **Step 3: Commit requirements.txt**

```bash
git add backend/requirements.txt
git commit -m "chore: add ruff to backend requirements"
```

### Task 3: Verify Ruff works

- [ ] **Step 1: Run Ruff check and format**
Run: `ruff check backend/ --fix && ruff format backend/`
Expected: Output showing files checked/formatted, exit code 0.

- [ ] **Step 2: Final Verification**
Run: `ruff check backend/`
Expected: "All checks passed!" or similar success message.
