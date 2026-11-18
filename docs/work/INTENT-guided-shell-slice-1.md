# INTENT: Guided shell, slice 1 (P03a) — a usable project workspace on the saved investigation

Date: 2026-11-18. Strategy: [STRATEGY-ai-native-research-platform.md](STRATEGY-ai-native-research-platform.md) §4, §16.2 (P03). Contract: [CONTRACT-ai-native-research-platform.md](CONTRACT-ai-native-research-platform.md) §8.

## Why

The owner reports that the live project interface "is just fields". The deployed Case, Evidence and Draft views are unstyled textareas labelled with raw field keys, with the older discussion page stacked underneath the Case form. P00–P02 changed the server only.

## Outcome

Replace the form wall with a guided workspace over the **existing v1 investigation document**:

- One destination bar on every project route: Overview, Evidence, Write, Discuss, with the save state, Save and export/import beside it.
- **Overview**: the question as the page heading, the current position (provisional answer, strongest tension, next test, what would change the answer), the claims as an argument outline with their evidence counts, background context, and a short next-step guide derived from what the project already contains.
- **Evidence**: findings as readable cards with the source quote, observed result separated from interpretation, claim relations, filters, side-by-side comparison, and source capture by search as well as by line.
- **Write**: the manuscript as a document with per-paragraph attribution and evidence links, and explicit insert actions.
- **Discuss**: the existing task-led discussion starter and working brief, moved to its own route instead of sitting under the Case form.

## Scope decisions

- Client only. No server, schema, migration or API change. Explicit Save, ETag conflict handling, unsaved-leave guard and offline bundle behave as before.
- No autosave: the strategy allows it only for migrated (v2) records, and no project is migrated.
- Canvas, Lab and Library destinations are not added as empty placeholders; they arrive with their packages (P04, P08, P09). Papers stay in the rail.
- Existing URLs keep working: `/projects/{id}` (Overview/Case), `/evidence`, `/draft`, deep links `?finding=`, `?claim=`, `?block=`.
- No new dependencies. No research content in browser storage (this includes the discussion starter's first prompt, which previously passed through localStorage).
- Provider calls happen only on two explicit actions that already existed: Generate paragraph in the Write assistant, and starting or continuing a discussion under Discuss. Navigation, task selection, capture, search, folding, theme changes and saving make none.

## Not in this slice (remains P03)

HTTP routes over the P02 records, v2 conversion in production, autosave, review queue, history/inspector tabs, command palette, onboarding sample project, the unfamiliar-user first-value exercise (C03).

## Checks

- `tsc --noEmit` and the production build pass.
- `npm run test:textfold` passes (unchanged engine and client validation).
- The three production-build browser journeys pass at 1440 and 390 after being updated to the new screens, with the same assertions as before: manual capture → relation → comparison → draft → save → reload; assistant review/discard/insert with provider-call counts; 412 conflict and 500 failure preserving text; leave guard; native folded preview attribution and finding links; theme change without remount; source-changed review state; viewer read-only; no unexpected API request; no horizontal page overflow.
- Screenshots of Overview, Evidence and Write at both widths, light and dark, inspected by eye.
- Not executable here and recorded as pending: authenticated production acceptance (no operator session), deployment.
