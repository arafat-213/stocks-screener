# Design Spec: Systemic Fix for "Cannot read properties of undefined" using lodash/fp

## Problem Statement
The application is experiencing intermittent crashes due to unsafe property access and array operations (e.g., `.map()`, `.filter()`, `.length`) on `undefined` or `null` values. These errors are prevalent across the React frontend, particularly when dealing with asynchronous data fetches or edge cases in state management.

## Goals
- Replace unsafe `.map()`, `.filter()`, and `.length` calls with safe equivalents from `lodash/fp`.
- Ensure the application handles `null`/`undefined` gracefully without crashing.
- Maintain a clean codebase using modular imports for optimal bundle size.

## Architecture & Implementation

### 1. Dependency Selection
- **Library**: `lodash` (Standard version, as `lodash-es` lacks `fp` support).
- **Style**: `lodash/fp` (functional programming style).
- **Why**: `lodash/fp` provides auto-curried, iteratee-first, data-last functions that are perfect for safe data processing.

### 2. Transformation Patterns

| Original Pattern | Safe `lodash/fp` Equivalent | Note |
| :--- | :--- | :--- |
| `data.map(fn)` | `map(fn, data)` | Returns empty array if `data` is nil. |
| `data.filter(fn)` | `filter(fn, data)` | Returns empty array if `data` is nil. |
| `data.length` | `size(data)` | Returns `0` if `data` is nil or not a collection. |
| `Array.isArray(x)` | `isArray(x)` | |
| `obj?.a?.b` | `get('a.b', obj)` | |
| `obj?.a?.b ?? 'default'` | `getOr('default', 'a.b', obj)` | |

### 3. Import Strategy
We will use **Direct Modular Imports**:
```javascript
import map from 'lodash/fp/map';
import filter from 'lodash/fp/filter';
import size from 'lodash/fp/size';
```
*Note: Using explicit paths ensures that Vite only bundles what is needed.*

### 4. Migration Scope
- **Directory**: `frontend/src/**/*`
- **Exclusions**: Non-frontend code (backend is Python), third-party libraries.

## Migration Strategy

1. **Setup**:
   - `npm install lodash`
   - `npm install --save-dev @types/lodash`
2. **Implementation Phases**:
   - **Phase A**: Automated replacement of the most common `.map` and `.filter` calls using regex where safe.
   - **Phase B**: Manual refactoring of `length` -> `size` and deep property access.
   - **Phase C**: Cleanup of unused `Array.isArray` or redundant optional chaining if it's now covered by `fp` methods.
3. **Validation**:
   - `npm run build`: Verify no syntax errors.
   - `npm test`: Ensure core logic is preserved.
   - Manual smoke test of key screens (Market Table, Screen Results).

## Risks & Mitigations
- **Argument Order**: `lodash/fp` uses `(iteratee, data)`. Traditional lodash and native methods use `(data, iteratee)`. We must be extremely careful during refactoring to avoid swapping logic.
- **Performance**: While `lodash` is fast, many small imports add up. `lodash-es` mitigates this via tree-shaking.
- **Over-refactoring**: Avoid replacing strings `.length` with `size` unless it's intended to handle `nil` strings.
