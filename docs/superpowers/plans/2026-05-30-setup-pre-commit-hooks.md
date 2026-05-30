# Unified Pre-commit Hooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up a unified pre-commit hook system using the `pre-commit` framework to run Ruff for the Python backend and ESLint/Prettier for the React frontend.

**Architecture:** A single `.pre-commit-config.yaml` in the repository root will orchestrate hooks for both `backend/` and `frontend/` directories.

**Tech Stack:** `pre-commit`, `ruff` (Python), `eslint`, `prettier`, `lint-staged` (Node.js).

---

### Task 1: Backend Configuration (Ruff)

**Files:**
- Create: `backend/pyproject.toml`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Create pyproject.toml for Ruff**
Configure Ruff for linting and formatting in the backend directory.

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

- [ ] **Step 2: Add ruff to requirements.txt**
Add `ruff` to the backend dependencies.

- [ ] **Step 3: Verify Ruff works**
Run: `source backend/venv/bin/activate && ruff check backend/ --fix && ruff format backend/`
Expected: Passes or fixes files.

- [ ] **Step 4: Commit**
```bash
git add backend/pyproject.toml backend/requirements.txt
git commit -m "chore: add ruff configuration for backend"
```

### Task 2: Frontend Configuration (Prettier & ESLint)

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/.prettierrc`
- Create: `frontend/.prettierignore`

- [ ] **Step 1: Install Prettier and lint-staged**
Run: `cd frontend && npm install --save-dev prettier lint-staged`

- [ ] **Step 2: Create .prettierrc**
```json
{
  "semi": true,
  "tabWidth": 2,
  "printWidth": 80,
  "singleQuote": true,
  "trailingComma": "es5",
  "jsxSingleQuote": true,
  "bracketSpacing": true
}
```

- [ ] **Step 3: Create .prettierignore**
```
dist
node_modules
.vite
package-lock.json
```

- [ ] **Step 4: Add lint-staged config to package.json**
Add `lint-staged` configuration to handle frontend files.

- [ ] **Step 5: Verify Prettier works**
Run: `cd frontend && npx prettier --write src/`

- [ ] **Step 6: Commit**
```bash
git add frontend/package.json frontend/package-lock.json frontend/.prettierrc frontend/.prettierignore
git commit -m "chore: add prettier and lint-staged for frontend"
```

### Task 3: Unified Pre-commit Hook (Root)

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

- [ ] **Step 2: Install pre-commit hooks**
Run: `source backend/venv/bin/activate && pre-commit install`

- [ ] **Step 3: Run pre-commit on all files**
Run: `source backend/venv/bin/activate && pre-commit run --all-files`

- [ ] **Step 4: Commit**
```bash
git add .pre-commit-config.yaml
git commit -m "chore: setup unified pre-commit hooks"
```
