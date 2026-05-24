# Design Spec: Journal Manual Entry

Add manual trade entry capability to the Trade Journal page.

## Proposed Changes

### 1. Header Update
- Add a "Manual Entry" button in the `Journal.jsx` header.
- Style: Primary button with a `Plus` icon from `lucide-react`.
- Location: Next to the "Last Updated" status card in the header.

### 2. State Management
- `createModalOpen`: Boolean state to control the visibility of the creation modal.
- `newTrade`: Object state to hold form data:
  - `symbol` (string, required)
  - `entry_price` (number, required)
  - `shares` (number, required, default 1)
  - `stop_loss` (number, optional)
  - `target` (number, optional)
  - `entry_date` (date string, required, default today)
  - `notes` (string, optional)
- `creating`: Boolean state to track API request status.

### 3. Creation Modal
- Replicate the existing modal styling (backdrop-blur, bg-bg-secondary, etc.).
- Form fields with clear labels and validation:
  - `Symbol`: Input with uppercase transformation.
  - `Entry Price` & `Shares`: Numeric inputs.
  - `Stop Loss` & `Target`: Optional numeric inputs.
  - `Entry Date`: Date picker.
  - `Notes`: Textarea for optional trade context.

### 4. API Integration
- Use `createJournalEntry` from `api/client.js`.
- On success:
  - Close modal.
  - Reset form state.
  - Refresh data using `loadData()`.

## Success Criteria
- [ ] "Manual Entry" button is visible and functional.
- [ ] Modal opens and correctly captures all required fields.
- [ ] Form validation prevents submitting empty required fields.
- [ ] New trades are successfully saved to the backend and appear in the list after refresh.
- [ ] Styling remains consistent with the "Close Position" modal.
