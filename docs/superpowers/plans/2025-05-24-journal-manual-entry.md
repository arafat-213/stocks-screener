# Journal Manual Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Manual Entry" button and modal to the Trade Journal page to allow manual trade entry.

**Architecture:** Add state and modal UI to `frontend/src/pages/Journal.jsx` and call `createJournalEntry` from `api/client.js`.

**Tech Stack:** React, Tailwind CSS, Lucide Icons, Axios.

---

### Task 1: Update Imports and State in `Journal.jsx`

**Files:**
- Modify: `frontend/src/pages/Journal.jsx`

- [ ] **Step 1: Add `Plus` to Lucide imports and `createJournalEntry` to API imports**

```jsx
import {
  TrendingUp,
  TrendingDown,
  History,
  Briefcase,
  ChevronRight,
  X,
  AlertCircle,
  BarChart2,
  PieChart as PieChartIcon,
  ArrowUpRight,
  ArrowDownRight,
  Plus // Add this
} from 'lucide-react';
import {
  getJournalOpen,
  getJournalClosed,
  getJournalStats,
  closeJournalEntry,
  createJournalEntry // Add this
} from '../api/client';
```

- [ ] **Step 2: Add new state variables for creation modal and form**

```jsx
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [newTrade, setNewTrade] = useState({
    symbol: '',
    entry_price: '',
    shares: '1',
    stop_loss: '',
    target: '',
    entry_date: new Date().toISOString().split('T')[0],
    notes: ''
  });
  const [creating, setCreating] = useState(false);
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Journal.jsx
git commit -m "feat(journal): add state for manual entry modal"
```

### Task 2: Add "Manual Entry" Button and Submission Handler

**Files:**
- Modify: `frontend/src/pages/Journal.jsx`

- [ ] **Step 1: Update Header to include "Manual Entry" button**

```jsx
        <div className="flex gap-2">
          {/* New Button */}
          <button
            onClick={() => setCreateModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-dark text-white rounded-xl shadow-lg shadow-primary/20 transition-all font-black text-sm"
          >
            <Plus size={18} />
            MANUAL ENTRY
          </button>

          <div className="px-4 py-2 bg-bg-secondary border border-border rounded-xl shadow-sm">
            <div className="text-[10px] font-black uppercase tracking-widest text-text-muted mb-1">Last Updated</div>
            <div className="text-xs font-bold text-text">{new Date().toLocaleDateString()}</div>
          </div>
        </div>
```

- [ ] **Step 2: Implement `handleCreateSubmit` function**

```jsx
  const handleCreateSubmit = async (e) => {
    e.preventDefault();
    if (!newTrade.symbol || !newTrade.entry_price || !newTrade.shares) return;

    setCreating(true);
    try {
      await createJournalEntry({
        ...newTrade,
        symbol: newTrade.symbol.toUpperCase(),
        entry_price: parseFloat(newTrade.entry_price),
        shares: parseInt(newTrade.shares),
        stop_loss: newTrade.stop_loss ? parseFloat(newTrade.stop_loss) : null,
        target: newTrade.target ? parseFloat(newTrade.target) : null,
      });
      setCreateModalOpen(false);
      setNewTrade({
        symbol: '',
        entry_price: '',
        shares: '1',
        stop_loss: '',
        target: '',
        entry_date: new Date().toISOString().split('T')[0],
        notes: ''
      });
      loadData();
    } catch (error) {
      console.error('Error creating journal entry:', error);
      alert('Failed to create trade. Please check console for details.');
    } finally {
      setCreating(false);
    }
  };
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Journal.jsx
git commit -m "feat(journal): implement manual entry submission handler"
```

### Task 3: Implement Manual Entry Modal UI

**Files:**
- Modify: `frontend/src/pages/Journal.jsx`

- [ ] **Step 1: Add the `ManualEntryModal` JSX before the closing `</div>` of the main component**

```jsx
      {/* Manual Entry Modal */}
      {createModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-bg-secondary border border-border w-full max-w-lg rounded-3xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center p-6 border-b border-border sticky top-0 bg-bg-secondary z-10">
              <h3 className="text-xl font-black text-text uppercase tracking-tight">New Trade Entry</h3>
              <button
                onClick={() => setCreateModalOpen(false)}
                className="p-2 hover:bg-bg-elevated rounded-full transition-colors"
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleCreateSubmit} className="p-6 flex flex-col gap-5">
              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-2">
                  <label className="text-[10px] font-black uppercase tracking-widest text-text-muted ml-1">Symbol</label>
                  <input
                    type="text"
                    required
                    value={newTrade.symbol}
                    onChange={(e) => setNewTrade({...newTrade, symbol: e.target.value})}
                    className="w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 font-bold text-text focus:outline-none focus:ring-2 focus:ring-primary/50"
                    placeholder="RELIANCE.NS"
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <label className="text-[10px] font-black uppercase tracking-widest text-text-muted ml-1">Entry Date</label>
                  <input
                    type="date"
                    required
                    value={newTrade.entry_date}
                    onChange={(e) => setNewTrade({...newTrade, entry_date: e.target.value})}
                    className="w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 font-bold text-text focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-2">
                  <label className="text-[10px] font-black uppercase tracking-widest text-text-muted ml-1">Entry Price (₹)</label>
                  <input
                    type="number"
                    step="0.01"
                    required
                    value={newTrade.entry_price}
                    onChange={(e) => setNewTrade({...newTrade, entry_price: e.target.value})}
                    className="w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 font-bold text-text focus:outline-none focus:ring-2 focus:ring-primary/50"
                    placeholder="0.00"
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <label className="text-[10px] font-black uppercase tracking-widest text-text-muted ml-1">Shares</label>
                  <input
                    type="number"
                    required
                    min="1"
                    value={newTrade.shares}
                    onChange={(e) => setNewTrade({...newTrade, shares: e.target.value})}
                    className="w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 font-bold text-text focus:outline-none focus:ring-2 focus:ring-primary/50"
                    placeholder="1"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-2">
                  <label className="text-[10px] font-black uppercase tracking-widest text-text-muted ml-1">Stop Loss (₹)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={newTrade.stop_loss}
                    onChange={(e) => setNewTrade({...newTrade, stop_loss: e.target.value})}
                    className="w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 font-bold text-text focus:outline-none focus:ring-2 focus:ring-primary/50"
                    placeholder="Optional"
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <label className="text-[10px] font-black uppercase tracking-widest text-text-muted ml-1">Target (₹)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={newTrade.target}
                    onChange={(e) => setNewTrade({...newTrade, target: e.target.value})}
                    className="w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 font-bold text-text focus:outline-none focus:ring-2 focus:ring-primary/50"
                    placeholder="Optional"
                  />
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-[10px] font-black uppercase tracking-widest text-text-muted ml-1">Notes</label>
                <textarea
                  value={newTrade.notes}
                  onChange={(e) => setNewTrade({...newTrade, notes: e.target.value})}
                  className="w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 font-bold text-text focus:outline-none focus:ring-2 focus:ring-primary/50 min-h-[80px]"
                  placeholder="Why did you take this trade?"
                />
              </div>

              <button
                type="submit"
                disabled={creating}
                className="w-full bg-primary hover:bg-primary-dark disabled:opacity-50 text-white font-black py-4 rounded-2xl transition-all shadow-lg shadow-primary/20 flex items-center justify-center gap-2 mt-2"
              >
                {creating ? 'SAVING...' : 'SAVE TRADE ENTRY'}
                {!creating && <ChevronRight size={18} />}
              </button>
            </form>
          </div>
        </div>
      )}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Journal.jsx
git commit -m "feat(journal): add manual entry modal UI"
```

### Task 4: Verification

- [ ] **Step 1: Verify syntax and basic functionality**
Since I can't run a browser, I'll double check the code for syntax errors and ensure all props and states are correctly used.

- [ ] **Step 2: Commit final changes if any**
```bash
git commit -m "chore(journal): final polish and verification"
```
