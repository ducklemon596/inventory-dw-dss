# Simplified inventory workflow

The initial screen shows snapshot item counts and a **Create plan** action.
**Plan date** uses a calendar bounded by the available snapshot range at or after
the loaded model's supervised-data cutoff. Dates without snapshots disable
planning and show a short message. Normal snapshot validation still checks
the complete 90-day sales history.
Each plan is a decision at that snapshot date; **Stock cover (days)** sets its
coverage target, not a schedule of future daily purchase orders.

The interface now uses English throughout: **Replenishment**, **View plan**,
and **Review / Approve / History**. The simulation caption and initial sidebar
instruction were removed at the user's request. The sidebar **Data & model**
section was also removed. Source provenance remains in exported metadata.

Further reduced on 2026-11-11: title **Nhập hàng**, action **Xem đề xuất**,
tabs **Cần xem / Duyệt nhập / Lịch sử**. Main-table explanations are short
statuses (Đủ lượng, Nhập một phần, Hết giới hạn, Chưa cần nhập, Cần kiểm tra).
Full explanations remain inside each item's approval expander. Repeated
instructions and the empty-screen overview were removed; quantity units are
explained in tooltips. The simulation label remains visible.

The following describes the underlying workflow and capabilities.

The main screen answers “Hôm nay cần nhập gì?” with one scenario by default.
The sidebar asks for an analysis date, target days of stock and total quantity
that can be allocated. The quantity limit is a sum of SKU-specific units, not
a monetary budget. A collapsed advanced section retains ranking profiles,
risk thresholds, K, unlimited Q and up to four comparison scenarios.

The primary workflow has three tabs:

1. **Hàng cần chú ý**: a short table of item code, current stock, unit,
   estimated days remaining, planned quantity and a plain-language explanation.
2. **Xác nhận lượng nhập**: allocated items plus the existing accept/edit/reject
   and note workflow. Saving records a decision; it does not submit an order.
3. **Lịch sử đã lưu**: reopen exact saved results and decisions.

The main table replaces the mostly empty diagnostics column with observed
coverage and allocation explanations. Examples include partial allocation,
no allocation because the resource limit is exhausted, and no replenishment
needed under the current coverage target. Existing diagnostic flags remain
visible when present. These explanations do not claim to explain model feature
attribution, and undefined coverage remains explicitly unknown.

Exact risk scores, technical diagnostics, scenario comparison and historical
evaluation remain in a collapsed advanced section below the primary workflow.
Full CSV exports preserve all original columns. Source/version identity,
stale-parameter protection, draft preservation and SQLite persistence remain
in effect. Simulation status is prominently displayed.

Run using the command in [the UI guide](mms-ui.md). Automated UI checks cover
the one-scenario default, simplified navigation, zero-budget explanations,
advanced evaluation, stale plans and persisted manager decisions.
