# Frontend Prettier and lint-staged Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure Prettier for consistent formatting and set up `lint-staged` to run ESLint and Prettier on staged files.

**Architecture:** Integrate Prettier as a dev dependency with a shared configuration file and hook it into the git commit process using `lint-staged`.

**Tech Stack:** Prettier, lint-staged, ESLint, React.

---

### Task 1: Install Dependencies

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install Prettier and lint-staged**
Run: `cd frontend && npm install --save-dev prettier lint-staged`

### Task 2: Configure Prettier

**Files:**
- Create: `frontend/.prettierrc`
- Create: `frontend/.prettierignore`

- [ ] **Step 1: Create .prettierrc**
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

- [ ] **Step 2: Create .prettierignore**
```
dist
node_modules
.vite
package-lock.json
```

### Task 3: Configure lint-staged

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Add lint-staged config to package.json**
Add the following configuration to `frontend/package.json`:
```json
  "lint-staged": {
    "*.{js,jsx,ts,tsx}": [
      "eslint --fix",
      "prettier --write"
    ],
    "*.{json,css,md}": [
      "prettier --write"
    ]
  }
```

### Task 4: Verification

**Files:**
- N/A

- [ ] **Step 1: Verify Prettier works**
Run: `cd frontend && npx prettier --write src/`

### Task 5: Finalization and Commit

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json`, `frontend/.prettierrc`, `frontend/.prettierignore`

- [ ] **Step 1: Commit the changes**
```bash
git add frontend/package.json frontend/package-lock.json frontend/.prettierrc frontend/.prettierignore
git commit -m "chore: add prettier and lint-staged for frontend"
```
