# MMS UI execution ledger — 2026-11-10

Plan: docs/superpowers/plans/2026-11-10-mms-ui.md.
User requested the UI directly; continue with the authorized Streamlit stack,
existing feature branch, service APIs and clearly labelled synthetic demonstration.

Implemented: sidebar date/scenario controls; Vietnamese source banner; model
catalog; metrics/charts; Review/Order/comparison tables; query and CSV/JSON export;
bulk and individual manager actions; pending notes; persisted backtests; saved
sessions and data-version-checked follow-ups. Theme uses native widgets, and the
generated trained app consumes the same dashboard through the embedding API.

## Important review findings and verified fixes

- A PowerShell stdin write replaced Vietnamese literals with question marks.
  Reproduced with a failing title/button-text test, restored using UTF-8 patches,
  then verified source text and rendered browser labels.
- Streamlit removed unrendered manager widgets when switching scenarios. A failing
  regression reproduced loss of action/quantity/note; explicit per-scenario draft
  storage and change callbacks now preserve them. New runs/runtime changes clear
  drafts intentionally. The bulk-input default warning disappeared as part of
  restoring widget state without a competing default value.

No Critical findings. Review did not certify live ClickHouse/historical release
approval; those remain documented integration boundaries. Mobile/browser behavior
was subsequently checked directly against the trained app, rather than inferred
from the reviewer’s static inspection.

## Verification

- MMS + extraction suite: **96 passed, 4 subtests passed**.
- Final targeted UI/presenter/tracking run: **15 passed**, including draft and
  localized-label regressions. Further layout/export-label changes are reversible
  presentation changes; final launch/build checks are recorded in the handoff.
- Fresh headless Chrome loaded the trained app, generated plans, inspected Review
  and Order tabs, and captured desktop/mobile states. No page errors. Mobile main
  container was 390px, content/alert 358px at x=16; no page-level overflow.
- Local app runs on 127.0.0.1:8501; launch command and workflow are in mms-ui.md.
- Existing unrelated Windows/warehouse acceptance limitations are unchanged; no
  assertion that the complete repository or production warehouse passed.

Rulings: retain Streamlit and native components rather than creating a separate
frontend stack; use Vietnamese labels and show synthetic provenance; allow notes
on pending decisions without treating them as purchase approval. The cost of
these choices is documented session-local draft behavior and the need for an
approved real source before production use.
