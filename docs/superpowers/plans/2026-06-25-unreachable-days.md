# Friend Link Unreachable Days Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show consecutive unreachable days on the friend-link reachability cards, especially for the unreachable filter.

**Architecture:** Keep the existing JSON shape and derive the display directly from `fail_count`/`fails` in `static/index.html`. Add a small helper that formats the duration once and reuse it in the card's main insight and unreachable detail chips so the UI stays consistent.

**Tech Stack:** Python tests, static HTML/JavaScript, existing Friend-Circle-Lite JSON output.

---

### Task 1: Lock the expected dashboard copy in a regression test

**Files:**
- Modify: `tests/test_refactor_contracts.py:44-106`

- [x] **Step 1: Write the failing test**

```python
        self.assertIn("unreachableDays", html)
        self.assertIn("formatUnreachableDays", html)
        self.assertIn("不可达", html)
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_refactor_contracts.py -k static_index_is_standalone_dashboard_with_view_switch -v`
Expected: FAIL because the dashboard source does not yet expose unreachable-day formatting.

- [x] **Step 3: Write minimal implementation**

Add the formatting helper and wire it into the unreachable card copy in `static/index.html`.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_refactor_contracts.py -k static_index_is_standalone_dashboard_with_view_switch -v`
Expected: PASS.

### Task 2: Render unreachable days in the card UI

**Files:**
- Modify: `static/index.html`

- [x] **Step 1: Write the failing test**

Already covered by Task 1.

- [x] **Step 2: Run test to verify it fails**

Already covered by Task 1.

- [x] **Step 3: Write minimal implementation**

Use `link.fails` as the displayed value for unreachable entries, label it as unreachable duration, and keep the existing RSS / backlink / update facts.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_refactor_contracts.py -k static_index_is_standalone_dashboard_with_view_switch -v`
Expected: PASS.
