# AI-native research platform: strategy and executable blueprint

Date: 2026-11-13. Status: planning only; proposed implementation contract, not implementation authorization.

## 0. Reading contract, authority and outcome

This blueprint combines the strongest ideas from the previously inspected Storyflow and Paperguide screenshots with OpenPaper's implemented investigation workspace. It is written for any competent implementation team or coding agent; it does not depend on a model, vendor-specific agent workflow, private conversation memory or temporary files. Product names describe reference paradigms, not independently audited competitor capabilities.

The requested outcome is a personal-first, collaboration-ready AI-safety research environment in which someone can formulate a question, discover and review literature, think spatially, design and run local experiments, update an argument, and write a paper without losing evidence or context at tool boundaries.

**Central decision: one research record, several synchronized working views, local execution, explicit AI assistance.** “All-in-one” means continuity of identity, permissions, provenance and interaction. It does not mean putting the notebook kernel, every dataset and every service inside a browser or a single cloud process.

This document authorizes no application code, dependency installation, account connection, database migration, paid model/search call, corpus expansion, local experiment execution, commit, push, merge or deployment. Such work requires a subsequent explicit instruction. Recommendations and numerical targets below are proposed requirements, not measured performance or features already delivered.

Read sections 1–8 for the product and research system; subsequent sections specify the architecture, integration contracts, delivery packages, checks and handoff. Material decisions include their alternatives and reopening conditions so implementation does not require another open-ended strategy session.

### 0.1 Baseline and evidence discipline

Inspected repository baseline: branch `feat/native-investigation-workspace`, HEAD `ef2a6731f9e429d45b30055940c0238e965df3a9`, initially clean. Existing work records report deployed source `c757bbf0`, migration `project_investigation_01`, revision `openpaper-00014-vjm` at 100%, and rollback by returning traffic to `openpaper-00013-7qj`. Canonical origin is <https://papers.sammatuba.workers.dev>. These are historical release records, not a fresh production inspection in this planning session.

Authoritative local baseline records:

- [Investigation user contract](../INVESTIGATION-WORKSPACES.md).
- [Existing investigation plan](PLAN-investigation-workspace.md).
- [Executed verification](VERIFICATION-investigation-workspace.md).
- [Accepted independent review](REVIEW-investigation-workspace.md).
- [Live work pointer](current.json) and [release handoff](HANDOFF-investigation-workspace.md).
- [Prior workspace/local-research strategy](STRATEGY-project-workspaces-and-research.md).

Preserve the following distinctions throughout the revamp:

| Recorded status | Treatment in this plan |
| --- | --- |
| M0–M6 passed; M7 deployed with public gates green | Retain the release evidence; do not rerun, overwrite or relabel it as new-platform acceptance. |
| A01–A24 passed, including native-reader fidelity, leak accounting, source-forgery rejection, optimistic concurrency, no-inference boundaries and redacted exports | Turn these properties into mandatory regression invariants for every affected package. |
| Historical required isolated PostgreSQL suite: 100 tests, zero skips; full server suite: 484 tests with separately recorded guarded skips | Preserve the distinction between required integration execution and broader suite counts; test totals will change. |
| Four documented rework rounds followed by final accept, no findings | Reuse the concrete regression cases, not merely the accepted label. |
| A25: 57 staged and 57 public HTTP checks passed; authenticated account UI not exercised | Account acceptance remains open. HTTP readiness is not authenticated feature acceptance. |
| `live_inference: false` | Live model behavior, quality and charges have not been established by that release. |
| Pilot PDF/Notes check, idle-login observation, one-week billing observation, citation/project-chat validation before corpus expansion | Carry forward explicitly, with an owner and evidence when eventually executed. |
| Feature branch not merged to master; release was archive-based | Do not assume master contains the deployed feature, or perform a merge as part of planning. |

The existing authenticated acceptance is a prerequisite to claiming that the current production baseline is user-accepted. It need not block isolated design or fixture-based implementation, but no new release may obscure that outstanding check. Live-AI acceptance remains a separate explicitly budgeted action.

### 0.2 Non-negotiable invariants

1. Navigation, selection, folding, layout, ordinary search over existing local indexes, saving and deterministic exports make zero model calls.
2. Source integrity is server-checked against immutable versions; a citation click is not proof of entailment or scientific validity.
3. AI-authored content remains attributable after human editing; external model content cannot impersonate an internally authorized model request.
4. Changed dependencies require renewed review; layout changes do not change scientific dependencies.
5. Every read, mutation, tool call, export and artifact transfer checks current authorization. Private notes are not shared by association.
6. Conflicts preserve the losing editor's work. Retrying a request never silently repeats an expensive or externally visible operation.
7. Local notebook execution and uploading local material require separate, specific consent. Pairing a device grants neither blanket filesystem access nor blanket execution approval.
8. The existing native Textfold engine, source fidelity, five levels, attribution, keyboard isolation and cleanup are retained. The canvas supplements it; it is not an excuse to replace it with an imitation.
9. No migration silently invents evidence, drops authored content, promotes imported citations to verified status, or resets provenance.
10. Human reasoning, comparison and manual drafting remain useful with AI disabled and with the local notebook companion disconnected.

## 1. Product thesis: the best of both worlds without feature fragmentation

### 1.1 What to combine

| Reference strength | First-class capability in the target platform | Unifying constraint |
| --- | --- | --- |
| Storyflow: spatial freedom | A genuinely freeform infinite-pan/zoom board with draggable cards, groups, connectors, sticky notes and saved layouts | Structured cards reference canonical records; placement never becomes a second evidence database. |
| Storyflow: mixed media | PDF, image, link, video/timecode and notebook-output cards alongside claims, notes and manuscript blocks | Content types keep distinct anchoring, rights, security and provenance rules. |
| Storyflow: board templates and AI layout | Research map, tension map, experiment storyboard, review Kanban and blank board; deterministic layout and explicit AI proposals | AI layout/expansion is previewed, scoped and reversible; no hidden evidence promotion. |
| Storyflow: spatial sharing | Permission-aware board sharing, accessible list equivalents, image/PDF export with provenance legend | No anonymous sharing of private research by default; exports disclose omissions and their snapshot date. |
| Paperguide: discovery-to-synthesis workflow | Discovery, deduplication, protocol, screening, extraction, synthesis and manuscript work in one project | Every transition leaves a reviewable record rather than a hidden agent conclusion. |
| Paperguide: systematic review | Versioned criteria, title/abstract and full-text screening, independent reviewer records, adjudication and count-derived PRISMA-style flow | AI recommendations are not human decisions; method compliance is not conferred by a diagram. |
| Paperguide: evidence-backed tables and answers | Cited extraction cells, comparison matrices, bounded retrieval and source-linked assistance | A cell can be unknown or unsupported. No forced answer because a table has a blank. |
| Paperguide: manuscript production | Scientific rich-text writing, citation management, equations, figures, tables, cross-references, styles and publication exports | Semantic document and provenance survive editor and export formats. |
| OpenPaper: integrity | Immutable source versions, verified anchors, AI provenance, dependency checks, access redaction and concurrency controls | These are the foundation, not optional premium modes. |
| OpenPaper: folded reading | Native Textfold previews from board, evidence and manuscript views | Folded representations are derived views, never alternate copies of source truth. |
| New requirement: experimental work | Locally executed Jupyter notebooks, versioned runs, datasets, measurements and publication artifacts | Cloud records describe approved work; they never expose an unrestricted local kernel. |
| New requirement: native ChatGPT | Remote authenticated MCP, bounded project context and reviewable research proposals; optional embedded app components | ChatGPT and the browser use the same application services and permission decisions. |

The old strategy deferred freeform canvas. **This blueprint deliberately changes that product decision:** freeform canvas is a committed target capability, not a perpetual “maybe later.” Its delivery follows stable entity identities so the result is a real research board rather than disconnected sticky notes. Likewise, systematic review is a committed pipeline addition, not renamed project chat.

### 1.2 What not to combine

Do not copy every reference feature indiscriminately. Do not build a proprietary 200-million-paper index, an unbounded autonomous swarm, a general-purpose video editor, a cloud GPU fleet, a second notebook IDE, a universal SaaS integration marketplace, or real-time multiplayer infrastructure before the personal workflow warrants them.

Use external scholarly catalogs with explicit coverage and licensing limits. Use JupyterLab for notebook interaction rather than recreating it. Use standards-based citations and exports rather than claiming a fixed number of supported styles. A sleek interface must not hide uncertainty, costs, save failures or permission boundaries.

## 2. The connected research model

### 2.1 The research loop

**Question → candidate explanations → search/review → findings → tension/argument → discriminating experiment → observed results → revised argument → manuscript → reproducible research bundle.**

This is a loop, not a mandatory linear wizard. A literature-only project can omit experiments. An exploratory experiment can precede a systematic review. A negative result can strengthen a limitation rather than support the initial hypothesis. The UI records why an investigation moved, not just which stage is complete.

The conceptual foundation remains the tension-resolution approach in the existing strategy: organize around uncertainties and competing explanations; compare experimental conditions; state a provisional reconciliation and what would change it. Reference: [People Should Resolve Tensions In AI Safety Research](https://www.lesswrong.com/posts/tn4WSyrqr7ozGLjRy/people-should-resolve-tensions-in-ai-safety-research), previously supplied in the repository.

### 2.2 One object, many views

An investigation is the project-level container. The following are first-class records with stable identifiers:

- Research question, hypothesis/claim, assumption and decision.
- Bibliographic work, exact source version, passage/region anchor and finding.
- Relation, including support, challenge, qualification and explicit non-evidential links.
- Search run, review protocol, candidate record, screening decision and extraction cell.
- Experiment specification, run, dataset/model reference, metric and artifact.
- Manuscript, section, block, citation and dependency review.
- Board, board item, group and presentation connector.
- Proposal, approval, task and audit event.

Examples of shared identity:

- Editing a claim in the board updates that same claim in the Case outline and evidence filters.
- Pinning a finding on two boards does not duplicate the finding or create two “votes” for it.
- A cited extraction cell opens the same source version used by the manuscript citation.
- An experiment result pinned beside a paper points to its run and artifact, not a pasted screenshot without lineage.
- A ChatGPT-proposed paragraph appears in the same review tray as an in-app proposal, with its external origin preserved.

Boards store positions, grouping and references. Manuscripts store authored text and typed citations. Findings store interpretations and anchors. No view gets a private, silently diverging copy of canonical research state.

### 2.3 Separate the kinds of confidence

Never collapse these into one green “verified” badge:

| Dimension | What can be established |
| --- | --- |
| Source identity/integrity | Bytes, extracted text and location match the recorded version. |
| Access | The current actor is permitted to see the source or artifact now. |
| Citation support | A named reviewer judges that the cited material supports the particular sentence, with qualifications. |
| Study quality | Method, controls, sample, measurement and reporting meet selected review criteria. |
| Generalization | Evidence is relevant to the target deployment setting; this often remains uncertain. |
| Replication | A specified protocol was repeated under recorded conditions with reported agreement/tolerance. |
| Decision confidence | A researcher records a qualitative judgment and rationale; not an automatically calibrated probability. |

Hash anchoring makes the chain inspectable; it does not establish that a paper is correct, that an AI interpretation is sound or that an evaluation predicts deployment behavior.

## 3. Guided AI-safety research

### 3.1 Default project templates

Offer five well-scoped starting templates and a blank investigation:

1. **Resolve an empirical tension:** apparently conflicting findings, condition matrix, competing explanations and discriminating tests.
2. **Replication and robustness:** target result, implementation differences, seeds, uncertainty, stress tests and failure analysis.
3. **Evaluation validity:** capability/safety construct, observable proxy, scorer validation, contamination, judge dependence and external validity.
4. **Mechanistic or causal investigation:** causal question, interventions, controls, alternative mechanisms and limits of interpretation.
5. **Systematic/scoping review:** protocol, searches, screening, extraction, synthesis and reporting. Systematic and scoping modes retain their methodological differences.

Examples for onboarding can concern monitoring reliability, reward hacking, scalable oversight or multi-agent coordination. They must be clearly synthetic demonstrations, not implied experimental findings. Never encode “show that this model is unsafe/safe” as the default objective.

### 3.2 AI-specific evidence schema

Show a short finding form by default, with an expandable method sheet:

- Model family and exact checkpoint/provider snapshot; base versus instruction-tuned model; training/fine-tuning details when actually known.
- Task, prompts, tools, permissions, scaffolding, agents/roles, communication topology and deployment assumptions.
- Dataset identity/version, split, sampling, prompt-development set and genuinely held-out set.
- Intervention/manipulation, baseline, controls and comparator.
- Unit of analysis, number of tasks/samples/seeds, dependence between samples and missingness.
- Outcome definition, scorer/rubric, human or model judge identity, blinding and validation.
- Point estimates, units, uncertainty intervals, effect sizes and analysis choices when available.
- Contamination/leakage risks, distribution shift, proxy validity, selective reporting and multiple comparisons.
- Resource envelope: compute, provider calls, latency and cost where relevant.
- Observed result, source authors' interpretation, our interpretation, limitations and applicability kept separate.

Each field can be “not reported,” “not applicable,” “not yet inspected” or a cited value. Missingness is not zero. An AI extraction suggestion does not erase those distinctions.

### 3.3 Guidance that does not require continuous inference

A deterministic research checklist supplies useful next actions from actual state:

- No explicit question → formulate the question and target decision.
- Only supporting findings → inspect counterevidence or document search limits; do not invent disagreement.
- Apparently conflicting results with different setups → compare conditions before calling it contradiction.
- Claim without an observable discriminator → specify what would change the conclusion.
- Experiment without a validated scorer/control → validate the measurement before running models.
- Results recorded before a frozen confirmatory protocol → label exploratory and record the amendment.
- Manuscript claim with stale citations → inspect affected sources before export.

Users can dismiss or defer suggestions with a reason. No opaque “research quality score,” forced gamification or agent-driven task treadmill. Optional AI can help explain a suggestion or propose a plan only after an explicit action.

### 3.4 Experimental rigor and safety

An experiment specification includes the question, hypotheses, exploratory/confirmatory status, observable outcomes, sampling plan, comparison/control conditions, budget, stopping rules, exclusion rules, analysis plan, data handling and expected limitations. Freeze a version before a confirmatory run; later changes become timestamped amendments, not silent edits to the original.

Treat model judges and multiple AI reviewers as potentially correlated. Report judge calibration and disagreement; two prompts to one model do not become two independent human reviews. Separate development and holdout evaluation, record negative and inconclusive results, and show why exclusions occurred.

Authorized AI-safety evaluations remain bounded to permitted models, datasets and environments. Experiments involving harmful content, sensitive data or external tools receive restricted artifact handling and an explicit review step. The platform is not a facility for unauthorized testing of third-party systems, uncontrolled internet actions or publishing unsafe raw outputs by default.

## 4. Information architecture and interaction design

### 4.1 A calm workspace, not a dashboard of everything

Keep the existing project shell and evolve it into six stable destinations:

| Destination | Purpose | Default content |
| --- | --- | --- |
| **Overview** | Resume the investigation and decide the next useful action | Question, provisional answer, strongest tension, next test, recent changes and review queue. |
| **Library** | Discover, collect, screen and manage sources | Search, saved searches, import queue, coverage, review pipeline and source records. |
| **Evidence** | Compare findings and develop the argument | Finding table, claim outline, extraction matrix and side-by-side comparison. |
| **Canvas** | Think spatially across evidence, experiments and draft ideas | Current freeform board; list/outline alternative always available. |
| **Lab** | Design experiments and inspect local runs | Specifications, paired-device status, run ledger, metric tables, plots and artifacts. |
| **Write** | Author and prepare a manuscript | Section outline, editor, references, figures, review checks and export. |

Case is retained as the Overview/argument entry concept; existing Case/Evidence/Draft URLs remain navigable through deliberate route migration. Chat is a contextual assistant drawer and a history destination, not a seventh competing research database. A command palette offers fast navigation and actions without hiding critical controls from new users.

Use a persistent but narrow project rail, a central work surface and one contextual inspector. The inspector has source, provenance and history tabs. Do not stack a source modal, chat sheet and evidence drawer on mobile. Closing an inspector returns focus and selection to its opener.

### 4.2 Visual system

Use restrained light and dark themes, readable document typography, strong hierarchy, consistent spacing and low-noise borders. Color represents stable meanings: support, challenge, qualification, pending review and access unavailable; icons and text repeat the meaning so color is never the only cue.

Document reading and drafting prioritize comfortable line length. Dense tables use tabular numbers. Canvas cards show one key proposition, source/status and a small type marker; details unfold on demand. Avoid glass effects, decorative motion, permanently glowing agents and oversized dashboards that reduce useful research space.

Motion should preserve spatial context: short transitions between board and inspector, visible insertion previews and understandable undo. Honor reduced motion; no auto-moving canvas while a researcher is reading or dragging. Skeletons match the content area, and background jobs have honest states rather than simulated progress percentages.

Target WCAG 2.2 AA through implementation and testing; a library's accessibility features alone do not establish conformance. Include keyboard-only operation, screen-reader labels/live announcements, 200% zoom, sufficient contrast, non-drag alternatives, visible focus and meaningful error recovery.

### 4.3 Frictionless onboarding

First-run path:

1. Sign in and arrive in a usable manual workspace; do not require an AI key, a notebook installation or ChatGPT connection.
2. Enter one research question or choose a clearly marked sample. Title, description and methodological fields can wait.
3. Add one paper through file, URL, identifier, existing library or Zotero; show metadata/text/index readiness separately.
4. Select a passage and create one finding with observed result versus interpretation visible.
5. Link the finding to a claim and produce a manual draft paragraph. This is the first value event.
6. Offer “Explore on canvas,” “Connect ChatGPT” and “Set up local lab” as independent optional next steps.

A short contextual checklist replaces a lengthy tutorial. Existing users resume existing projects without repeating onboarding or accepting a forced migration. Empty states explain the next action and show one example, not invented populated results.

First-value target: an unfamiliar user completes steps 2–5 within ten minutes on a provided small, already readable fixture, without assistance. Separately measure real import latency rather than hiding it inside that usability target.

### 4.4 Save, history, recovery and collaboration behavior

During early packages, preserve the proven explicit workspace Save behavior. Do not bolt debounce writes onto the current whole-document contract.

After the revisioned entity model and recovery checks ship, introduce autosave for ordinary authored edits, board layout and manuscript blocks. Display “Saved,” “Saving,” “Offline/unsaved,” “Conflict” or “Save failed” with a precise last-saved version. Method decisions, screening decisions, applying AI proposals, approving runs, publication and sharing remain explicit actions.

A saved edit and a scientific decision are different events. Use named checkpoints for important argument/protocol/manuscript versions. Undo creates a new revision; it does not erase history or AI attribution. Edits to separate records can merge when their dependencies are independent. Edits to the same record require explicit conflict resolution; no silent last-writer-wins prose loss.

Keep in-memory unsaved state and explicit recovery export. Do not silently persist PDFs, sources, prompts or manuscripts to browser localStorage. A future opt-in encrypted offline workspace requires a real key-management and device-loss design; browser encryption with an adjacent stored key is not a security solution.

Initial collaboration is durable comments, mentions, review assignments and conflict-safe editing. Real-time cursors and CRDT coediting are deferred until concurrent authoring is measured; the personal UX must not depend on a live presence service.

## 5. Freeform canvas: spatial freedom with evidence integrity

### 5.1 Required capabilities

The board must support infinite pan/zoom, arbitrary card placement, multi-select, drag-to-restructure, groups/frames, sticky notes, connectors, undo/redo, duplicate view references, search, fit selection, minimap, saved views and deterministic arrange. Provide keyboard equivalents and an accessible board-as-list/outline representation.

Card types: question/claim, finding, paper/PDF, plain note, image/figure, link, video/timecode, experiment specification, run/result, dataset/table/chart, manuscript block and explicit gap. Display unsupported or unavailable media as a labeled placeholder rather than breaking the board.

A note can be exploratory and need not pretend to be evidence. “Promote to claim/finding” is explicit and requires the missing structure and source review. A connector drawn freely is a presentation link until the user selects a scientific relation type and supplies its rationale. Spatial closeness and a visual arrow do not mean empirical support.

### 5.2 Relationship semantics

Support/challenge/qualify relations reference a finding and a claim. Additional typed relations can represent assumes, motivates, tests, measures, derived-from and cites. Define allowed endpoint types and reject invalid combinations server-side. Presentation-only connectors stay outside the scientific dependency graph.

Dragging a card changes layout only. Editing a claim changes the claim revision and invalidates dependent reviews. Duplicating a card creates another board reference, not another piece of evidence. Deleting a board reference leaves the research record intact. Archiving a referenced research record preserves backlinks and warns about dependent manuscript blocks.

### 5.3 AI board behavior

Offer three distinct controls:

- **Arrange:** deterministic layout of selected cards; no model call; preview and undo.
- **Suggest connections:** an explicitly generated proposal over selected, authorized records; proposed relations carry rationale and remain unaccepted.
- **Expand this area:** a bounded research proposal that lists missing evidence, candidate questions or proposed searches. Actual external searches/imports require approved scope and budget.

Every AI request shows selected material, excluded material, provider and spending boundary. No automatic reading of the whole board, private notes, hidden groups or external media. Review board-wide changes as a diff; layout suggestions must not silently rewrite claims.

### 5.4 Media and board export

Images retain original artifact identity and derived preview identity; image-region anchors include original dimensions and coordinates. Video cards initially support an authorized link, metadata and manually selected timecodes. Automated download/transcription/frame extraction is a separate licensed, resource-bounded job and never fires merely because a link is pasted.

A link-only video card is an **unverified external locator**. Its URL, metadata and manually selected timecode do not establish immutable media identity, and it is ineligible for source-integrity-verified findings or verified quotation nodes. It may be referenced as an explicitly unverified observation; an unchanged URL must never produce a “source unchanged” assurance. If remote content changes or becomes unavailable, preserve the locator/history and mark the card unavailable or requiring inspection rather than silently rebinding it.

Verified multimedia anchors require an approved immutable media or transcript snapshot with an artifact digest, declared version and an inspected locator. Verification coverage is explicit: a transcript-text anchor verifies wording in that transcript, not that a transcription faithfully represents the recording; a frame anchor verifies a frame captured from the identified media snapshot, not an interpretation of the event. Human checks of transcription/timing remain separate review records. A transcript has its own version and provenance. Timecodes are media locators, not PDF line numbers. Frame grabs inherit media permissions. Remote embed content is allowlisted or replaced by a safe link preview; untrusted HTML is not rendered in the application's trust context.

Board PNG/PDF export uses a chosen viewport or named frames, includes a legend and source/reference appendix, and warns about inaccessible or omitted cards. The accessible textual outline and research bundle remain available because a board image cannot carry the full evidence chain. Export is deterministic and makes no model call.

## 6. Discovery, reference management and rigorous review

### 6.1 Acquisition and source identity

Keep Zotero, existing uploads, Exa and OpenAlex adapters. Add DOI/arXiv/PMID resolution where supported, BibTeX and RIS import, and standards-based transfer from other managers through their documented exports. A direct Mendeley API integration is not a prerequisite; do not promise access without checking current authorization and terms.

Separate bibliographic work from exact version and actual bytes. Match exact content hashes confidently within an authorized scope; use identifiers and metadata to propose merges. Never merge solely by similar title. A preprint and later publication may belong to one work but remain distinct evidence versions. Merging duplicates preserves annotations, review decisions, aliases and a reversible merge record.

Display catalog coverage, query, filters, date, pagination and provider errors. Use “no indexed match” rather than “no evidence exists.” Discovery snippets may nominate candidates but cannot substantiate methods or results that require inspecting the source.

#### Review identity and counting contract

Freeze a versioned count policy with each review protocol before acquisition/screening. The default literature-review mode has these distinct identities:

| Identity | Meaning and counting rule |
| --- | --- |
| Acquisition occurrence | One provider hit or explicitly imported record within a specific search/import execution. Retrying delivery or resuming a page does not create another occurrence; a genuinely new search can retrieve the same report again and creates another occurrence. “Records identified” counts the frozen included occurrence set. |
| Report and report version | One scholarly report, with separately preserved exact document versions. Confirmed preprint/publication versions of the same report may share a report ID only after explicit identity review; a related companion report remains distinct even if it describes the same experiment. Mere title/DOI similarity cannot decide this. |
| Review candidate | One candidate per review/report, bound to an explicitly selected report version for screening. Deduplication maps acquisition occurrences to candidates; the retained representative and all removed occurrences remain inspectable. Screening counts candidates, not search hits or source bytes. |
| Study/experiment | The underlying empirical investigation at the protocol's declared unit. Reports and studies have a many-to-many relationship: a report can describe several studies, and several reports can describe one study. Linkage requires recorded rationale/evidence. Unresolved linkage remains unknown; it is not automatically counted as independent corroboration. |

For the default flow, every identified occurrence is either a retained representative, a recorded duplicate removal, or another explicitly categorized pre-screen removal. These sets are disjoint. Candidates are screened once per active protocol/version; included/excluded/pending states form explicit disjoint sets at each stage. Full-text reports sought, not retrieved, assessed, excluded and included count candidate reports, not underlying studies. Included-study totals count the distinct linked study IDs and disclose unresolved study linkage separately. Synthesis uses the declared study/measurement dependencies, never the number of reports as a proxy for independent evidence.

Repeated searches can be added to the review through a versioned acquisition-set update; historic flow snapshots retain their original sets. A reversible report merge stores the mapping and representative-version decision. It changes current dedup/candidate sets through an explicit event; incompatible previous screening decisions enter adjudication rather than choosing one silently. Splits and report-version replacements similarly trigger affected review. Confirmatory synthesis must not silently mix results from different versions of one report.

P01/P02 must freeze these identities, count policy and mapping events before P04 implements deduplication. Other review modes can declare different units and flow stages, but must provide equally explicit definitions and their own expected-count fixtures; a generic “unit of analysis” text field is insufficient.

### 6.2 Research search agent

Provide bounded, explicit search plans: question, sources/providers, query variants, inclusion hints, maximum queries/results, time/cost budget and stop conditions. The user previews the plan; execution records actual queries and returned identifiers. Search results are candidates, not included studies.

First use lexical/full-text search and metadata filters over the authorized library. Add semantic/hybrid retrieval only after a corpus-specific evaluation demonstrates meaningful misses and a measured improvement. Do not build a new graph database or remote vector service solely to describe the product as AI-native.

### 6.3 Protocol and screening

A review protocol records review type, research questions, scope, databases, date ranges, query versions, eligibility criteria, unit of analysis, reviewers, screening stages, extraction fields, synthesis method and limitations. Criteria are stable IDs with versions, not an unstructured prompt alone.

For each candidate, retain retrieval provenance and duplicate decisions. Title/abstract and full-text screening are separate stages. Each decision records actor, protocol version, criterion-level judgment, reason, cited supporting text where available and timestamp. “Unclear” is a real state; absent full text is not an automatic exclusion disguised as evidence.

Dual-review mode hides the other reviewer's decision until both are submitted. Conflicts enter an adjudication queue. An authorized named reviewer records the final decision and rationale. A solo researcher can use a single-human workflow with AI suggestions, but the report must disclose that it was not independent dual-human review.

Revising a protocol invalidates affected decisions selectively and makes amendments visible. AI may recommend screening decisions with cited reasons, but final inclusion/exclusion remains an explicit human action. Avoid biased early stopping or automatically excluding low-ranked results without a declared, validated method.

### 6.4 Extraction and synthesis

Extraction tables support typed columns, units, repeated measurements, citations per cell, missingness, reviewer identity, status and a source version. Store AI suggestions separately from accepted cells. Computed columns record expression/query version and input dependencies; their values are derived, not source quotations.

Offer a method-comparison matrix, contradiction/qualification view, evidence-gap view, structured narrative synthesis and approved statistical analyses. Do not calculate pooled effects merely because several papers contain numbers: require compatible estimands, units and assumptions, and disclose heterogeneity and dependence.

PRISMA-style diagrams derive from actual search, deduplication, screening and inclusion events. Each box opens its underlying set. Counts reconcile after amendments and duplicate merges; manual overrides are explicit annotated corrections, not edits to a picture. A generated flow diagram is not a certification of PRISMA compliance or review quality.

### 6.5 Bibliographic and source-strength signals

Add reference correction, collections/tags, identifier resolution and citation-key management. Preserve original and corrected metadata and their provenance. Support CSL-based style selection and versioned style assets rather than advertising an unverified number of styles.

If licensed and available, display journal/source metrics such as SJR/SNIP as contextual metadata with provider, year and retrieval date. Never turn venue metrics into a paper truth score or use them to automatically reject unconventional AI-safety work. Retraction/correction/version notices are more directly actionable and should link to the exact affected work/version.

## 7. Scientific writing inside the platform

### 7.1 Editor capabilities

Adopt a mature schema-based rich-text editor rather than grow the current block editor into a bespoke word processor. The target includes headings, paragraphs, lists, inline/display math, tables, figures with captions, citations, cross-references, footnotes, comments, tracked proposal diffs and section-level history. Keyboard-centric authoring and a readable focused-writing mode matter more than a large toolbar.

Use typed nodes for citations, source quotations, results/figures and gaps. A citation references canonical work/version and finding or run IDs, with dependency pins. Human prose is editable; exact-quotation nodes preserve captured wording and require explicit conversion to ordinary prose if edited.

Rich editor rendering and exported HTML/LaTeX are separate adapters over the same semantic document. An attractive custom citation widget is not, by itself, a portable citation implementation.

### 7.2 Writing workflows

- Start from a research question, a venue outline or a blank manuscript; never auto-fill results for an unrun experiment.
- Assemble selected findings into a manual outline or evidence bundle without inference.
- Ask the assistant for a bounded paragraph, revision or counterargument; show selected evidence and a diff, then insert explicitly.
- Insert a figure from a run artifact with caption, analysis version and source lineage.
- Inspect a sentence's citation → finding → paper passage or run result → source/experiment artifact.
- Review stale dependencies in a dedicated queue before freezing a manuscript checkpoint.
- Show uncited, unsupported, stale, externally AI-authored and access-unavailable states distinctly.

An accepted paragraph can remain scientifically disputed. Citation-marker validation only proves the reference exists in the permitted selection, not that every generated sentence is supported.

### 7.3 Publication and portability

Deliver Markdown, BibTeX and the existing research bundle first without regressions; add CSL JSON, RIS, CSV/XLSX tables, semantic manuscript JSON, DOCX and LaTeX/PDF publication export. Use a pinned document conversion pipeline and venue/style assets with tested fixtures. Publication export does not execute notebooks by default.

Choose a canonical manuscript checkpoint for each export; collect a source manifest, bibliography, cited figure/table versions, stale/uncited warnings and reproducibility appendix. Offer a review-ready export with visible warnings and a publication-preflight mode that requires unresolved integrity/access problems to be resolved or explicitly disclosed. Never silently drop warnings to make a clean-looking paper.

Local Quarto/Pandoc-based rendering is the preferred first reproducible publication path, with optional sandboxed cloud rendering later. LaTeX shell escape, external resource fetching and automatic notebook execution remain disabled in untrusted exports. DOCX round trips are import-as-proposal, not lossless live synchronization. Venue-specific formatting is tested; do not promise arbitrary templates are perfect.

Keep code/notebooks in the selected research repository, manuscript state in the platform after explicit adoption, and publication bundles as immutable snapshots. Existing externally authored manuscripts remain externally canonical until a deliberate import/cutover; never silently establish two masters.

## 8. Local Jupyter lab and reproducibility

### 8.1 Product decision

Use an optional local companion that pairs a selected workspace directory with a project. The companion initiates authenticated outbound connections to the application. JupyterLab remains local and is opened through a local launch action; the cloud app shows the experiment record, run status and approved artifacts. No inbound tunnel or public kernel endpoint is required.

Do not iframe an unrestricted notebook server into the cloud application or send a Jupyter token through ChatGPT. Pairing is not remote execution permission. The initial release supports a documented Linux/WSL2 path; macOS/native Windows support requires separately executed packaging, filesystem and credential-storage tests before it is advertised.

### 8.2 Binding and ownership

The user selects an existing research directory. A versioned binding records project UUID and relative artifact paths; machine-specific roots and credentials remain local and unversioned. Preserve existing shared-literature/project layouts rather than create a new repository for every investigation.

Cloud-canonical: investigation claims/findings, review decisions, manuscript after adoption, approved artifact metadata and selected uploaded artifacts. Local-canonical: notebook/code working tree, environments, raw local datasets and unpublished outputs. Git commits are user actions or separately approved integration actions; pairing never auto-commits or pushes.

Initial synchronization is explicit pull, compare, approve and publish. Cloud-to-local edits become proposed file changes, with an inspected diff. Concurrent changes fail safely; no overwrite based solely on filename or project title.

### 8.3 Run lifecycle

1. Prepare an experiment specification and select a local notebook or proposed template.
2. Local preflight shows exact code/notebook digest, selected directory, environment, inputs, network access, provider usage, limits and expected outputs.
3. Approve the run locally. Any change to code, inputs, environment or permissions invalidates that approval.
4. Execute in the chosen isolated environment with resource limits and a visible stop control. Inspect status locally; cloud progress is a bounded outbound summary.
5. Seal a run manifest and local artifacts. Mark interrupted/failed/uncertain states honestly.
6. Preview upload contents and data classifications. Publish only selected artifacts; default to aggregate measurements and figures, not raw sensitive prompts/responses.
7. Compare runs, review the interpretation and explicitly promote a result to a finding.
8. Update dependent argument/manuscript records through reviewed changes.

An optional future remote “run request” creates a pending local approval, not an executable command. Unattended approved protocols are a later, separately scoped capability with bounded permissions and costs; they are not required for the first coherent platform.

### 8.4 Reproducibility contract

A run manifest records experiment/specification version; notebook and cell identifiers plus source hashes; dirty working-tree status and captured patch or source snapshot; code commit when present; dependency lock/environment digest; runtime/OS/hardware and accelerator libraries where relevant; dataset/split hashes; model snapshot or weights identity; prompts/tool/scorer versions; seeds and sampling parameters; timestamps, limits and actual usage; output hashes and error states.

Run status distinguishes interactive exploration from a fresh-kernel ordered execution. A notebook saved after arbitrary interactive execution is not automatically reproducible. Preserve whether outputs were manually edited or imported. Record non-determinism and tolerance-based reproduction criteria; seeds do not guarantee bit-for-bit results on GPUs or hosted model APIs.

Notebook attachments, HTML/JavaScript outputs and widgets are untrusted content in cloud previews. Use sanitized or rasterized previews and retain raw notebook files as authorized downloads. A notebook's local trust signature does not make its content safe for the platform's web origin.

A research result needs both artifact identity and scientific interpretation. A successful kernel exit, a matching hash or a reproducible plot does not prove the hypothesis.

## 9. Architecture: a modular application with a separate analytical data path

### 9.1 Keep the working platform

Retain Next.js/React for the web client, FastAPI/Pydantic for application contracts, PostgreSQL/SQLAlchemy/Alembic for transactional state, the current object-storage abstraction, and existing production Cloud Run/Cloud Tasks infrastructure. Preserve the current Cloudflare front door until actual latency measurements and an approved origin migration justify changing it. Do not introduce a second public origin casually: cookies, OAuth resource metadata, redirects and streaming all depend on it.

Use a modular monolith for research services, with existing asynchronous workers for expensive tasks. Split deployments only for independently measured resource or isolation needs: parsing, document conversion and analytical jobs do not belong in latency-sensitive request handlers. The local companion is a separate trust domain, not another cloud microservice.

```text
Browser ── canonical HTTPS origin ── Web shell / FastAPI
                                      │
ChatGPT ── remote MCP adapter ─────────┤ shared application services
                                      ├─ PostgreSQL: identity, revisions, evidence, approvals
                                      ├─ Queue/workers: parsing, indexing, conversion
                                      └─ Object storage: private immutable artifacts

Browser worker ── approved object/range reads ── analytical subsets

Local Jupyter + native DuckDB
          │ local execution and local approval
Local companion ── outbound authenticated control + approved artifact transfer
```

API and MCP adapters call the same domain services; do not have MCP call a browser route which calls Next.js which calls FastAPI. Browser application requests use the canonical API route rather than an unnecessary second backend-for-frontend hop. Large authorized artifact bytes can travel directly between storage and browser/companion, bypassing application buffering, after permission checks mint a bounded capability.

Keep the production queue backend explicit. Supporting Celery for self-hosted installations does not mean operating Celery/RabbitMQ and Cloud Tasks simultaneously for the same task. Do not add Redis, Kafka, a graph service or a standalone vector database unless a measured requirement justifies their operating cost.

### 9.2 Control path versus analytical data path

| Information | Canonical representation | Why |
| --- | --- | --- |
| Accounts, project roles, grants, revisions, approvals, budgets | PostgreSQL records; bounded JSON API messages | Transactionality, constraints and authorization dominate. |
| Manuscript/editor state and small research records | Schema-versioned semantic JSON plus relational identity/revisions | Natural document semantics; no benefit from columnar encoding. |
| Source PDFs, images, notebooks, model responses | Original private binary/JSON/text artifacts plus metadata | Preserve exact bytes and content-type semantics. |
| Large evaluation tables | Immutable Parquet, with schema and manifest | Compressed columnar storage and selective reads. |
| Batched query results | Arrow IPC when measurements justify it; JSON for small results | Typed transfer without row-by-row object inflation. |
| Repeated local analytical exchange | Arrow-compatible in-process interfaces or memory-mapped IPC where appropriate | Reduce unnecessary buffer copies within known boundaries. |
| Interactive plots/table viewport | Small selected columns and aggregates | Do not make the UI render the entire experiment dataset. |

### 9.3 Arrow: precise use of zero-copy

Use Arrow as an analytical interchange layer, not as a general application architecture slogan.

- Within one Python process, Arrow C Data/C Stream interfaces can share compatible buffers between libraries. Ownership and lifetime must be correct; joins, casts, sorts and aggregations still allocate.
- For repeated local cross-process reads, immutable uncompressed Arrow IPC files can be memory-mapped. File construction, writes, metadata and page faults still have costs. C pointers cannot be passed between processes as a transport.
- Parquet compression and decoding require work and usually allocations. A remote object is not a memory-mapped local buffer.
- In browser workers, transferring an `ArrayBuffer` can avoid a worker-message payload copy and detaches the sender. That does not guarantee zero-copy into WebAssembly memory or out of DuckDB query results.
- Conversion to ordinary JavaScript row objects, pandas blocks, strings or different types can reintroduce copies. Use typed/columnar views where practical and measure the actual path.
- TLS, network transfer, decompression, GPU movement and rendering are not eliminated by Arrow.

Do not introduce SharedArrayBuffer and cross-origin isolation headers merely for theoretical performance. They can complicate OAuth popups and embedded resources. Start with dedicated workers and transferable buffers; add shared-memory paths only after compatibility and memory tests show a material improvement.

### 9.4 DuckDB, HTTP and Flight decisions

Use native DuckDB for local analysis of experiment artifacts. Offer lazy-loaded DuckDB-Wasm in a dedicated browser worker for bounded, already authorized datasets and results. The ordinary project, canvas and editor must not download the analytical engine.

Start with HTTP range reads of immutable Parquet and HTTP Arrow IPC streams for computed batches. Verify CORS, `HEAD`, byte ranges/206, expiry, cancellation and bounded buffering. Query selectivity depends on row-group statistics, layout and predicates; do not promise every filtered query downloads only the result rows.

Do not add Arrow Flight initially. Flight is a gRPC-based analytical transport, not a browser-native replacement for fetch. Reconsider for sustained native-client/service throughput after profiling proves HTTP is the bottleneck and the additional service, authentication and transport complexity pays for itself.

No arbitrary SQL runs in a privileged cloud process. DuckDB can access files, URLs and extensions; use approved dataset identities and bounded query templates or a genuinely isolated execution environment. Engine settings are defense-in-depth, not a sandbox. Validate extension loading, memory, CPU, output size and network behavior.

### 9.5 Artifact and table contracts

Every artifact manifest includes project/owner, immutable artifact ID, content kind/media type, byte count, raw-byte SHA-256, schema version where applicable, storage object/generation reference, creation origin, parent artifacts, run ID, classification and retention policy. Content digests are not access capabilities and must not expose cross-user deduplication information.

Analytical schemas define nullable fields, units, timestamp precision/time zone, decimal semantics, categoricals and nested fields explicitly. A common evaluation table can include run ID, sample ID, condition, model revision, dataset/split ID, seed, metric name/value/unit, outcome state, latency, token usage, cost estimate and artifact references. Large prompts or responses belong in referenced restricted artifacts, not repeated in every metric row.

Enforce schema evolution rules: additive nullable columns are compatible only when declared; type changes and unit changes create a new schema version. Preserve integers beyond JavaScript's safe range as exact values, not rounded numbers. Round-trip tests cover nulls, NaN/infinities policy, decimals, time zones, Unicode and nested data.

Store immutable analysis query/specification and input IDs alongside results. A figure captures plot specification, analysis version and data dependencies. Record whether the artifact was generated locally, uploaded manually or produced in a managed job. A hash verifies bytes, not the trustworthiness of the producer.

### 9.6 Reliable jobs and bounded inference

Use durable task identities, a transactional dispatch/outbox record where a database mutation must initiate work, leases where appropriate, and monotonic job states. Queue delivery is at least once. Checkpoint completed outputs before acknowledging, and reconcile orphaned states without automatically rerunning uncertain paid work.

Keep separate contracts for deterministic re-executable jobs and provider calls with uncertain external completion. For model calls, preserve the existing durable request/hash, single-claim execution and explicit retry boundary. Exactly-once end-to-end inference cannot be guaranteed merely by a queue or object checkpoint.

Limit ingestion concurrency; release database transactions before slow downloads or provider calls. Stream or stage large files rather than load them into request memory. Cloud Run temporary files are not durable storage and may consume instance memory; use bounded scratch space and artifact storage deliberately.

The current computed-column path uses generated scripts and E2B. Inspection found no explicit network-restriction setting at sandbox creation; “no network” in a prompt is not proof of enforcement. It also has generation/repair attempts and separate server-side commit boundaries. Before broadening this feature, verify actual sandbox controls, budget each attempt, and checkpoint/reconcile compute outcomes so a retried webhook cannot silently spend again. Do not replace sandbox execution with unrestricted local execution.

## 10. Persistence, provenance and migration contracts

### 10.1 Why evolve the current document

The current 2 MB, whole-investigation JSONB document with project-level ETag is suitable for its bounded release. It should not become a container for thousands of review records, media metadata, run tables and every board coordinate update. Preserve its integrity semantics while evolving storage deliberately.

Target a relational identity/revision layer with typed, bounded payloads and first-class foreign keys for important relationships. Keep PostgreSQL as the graph store; normal indexed relations and bounded graph traversals are sufficient initially. Do not introduce a generic unvalidated entity-attribute-value store.

### 10.2 Proposed durable record families

| Family | Required identity and integrity rules |
| --- | --- |
| Investigation/project state | Project ID, active schema generation, project change sequence, question/context and retained legacy snapshot. |
| Research entities | Stable UUID, project, type, revision, typed payload, archive status, actor and timestamps; append-only revision records where authored state changes. |
| Scientific relations | Typed endpoints with project consistency and endpoint constraints; rationale and revision. |
| Works and source versions | Work identity independent from immutable bytes/extracted-text version; extractor/version, bibliography provenance and permissions. |
| Evidence anchors/findings | Typed anchors against identified source/artifact snapshots: text lines, PDF/image regions, media timecodes, table cells or run metrics, with digest and captured quotation/value. Link-only external media is a separate unverified-locator type, never a verified anchor. |
| Manuscript records | Document/section/block IDs, semantic nodes, provenance spans or block origins, typed references and pinned dependency versions. |
| Review protocol/events | Protocol/count-policy versions, acquisition-occurrence → report/version → candidate mappings, many-to-many report/study links, independent decisions, reversible merges, amendments, adjudication and extraction revisions. |
| Experiment/run/artifact | Frozen specification, run state, environment/input identities, immutable manifest and approved artifact references. |
| Boards | Board ID and revision; layout/presentation items referencing entities; non-evidential notes/links distinctly typed. |
| Proposals and approvals | Origin/client/actor, payload hash, target revisions, selected dependencies, expiry, approval and application receipt. |
| Job/budget/audit records | Request identity, state transitions, reservation/usage, redacted audit metadata and reconciliation status. |

Avoid duplicating a reference manager's private annotations into shared findings. A researcher explicitly promotes chosen text into shared evidence only when permitted. Experimental artifacts get native evidence kinds; do not counterfeit a paper ID or text-line anchor to fit the old schema.

### 10.3 Source-version and review rules

Re-extraction creates a new source-text version with extractor/version metadata. Replacing PDF bytes creates a new source version. Old versions remain available only according to current rights and retention policy; unchanged original bytes do not imply unchanged extraction offsets.

Existing v1 findings initially bind to a captured version of the current source text only if their hashes and quotes match. A mismatch remains stale/unbound and enters review. Unknown PDF page maps remain unknown; never infer a precise page from an extracted line number alone.

A block review records the exact dependency versions and source access checked. New evidence, changed findings or updated experiment outputs make affected reviews stale. Changing a board color or card position does not. The UI should show why the review became stale and the smallest affected set.

If access is revoked, redact protected source captures and derived previews on subsequent reads/exports. Preserve authored prose and expose citation-unavailable status; do not pretend already downloaded files can be recalled. Retention/deletion policies must account for backups and legally permitted historical records.

### 10.4 Concurrency and autosave contract

Every mutable entity has a revision; the project also has a monotonically increasing change sequence for synchronization. Mutations carry expected revisions. Multi-record semantic actions validate all target revisions and commit atomically; return a receipt with resulting versions.

Same-record conflicts return 412; missing required preconditions return 428; source/dependency incompatibility returns 409; malformed/schema/reference failures return 400/422 as defined. Permissions are rechecked inside the mutation transaction. A request with an idempotency key replays its original receipt only after current access checks; different payload reuse returns a conflict.

Independent record edits may succeed concurrently. A new relation, promotion to a finding or AI proposal application is a transaction across its affected records, not a sequence of partially saved HTTP calls. Choose and document one database lock order. No database transaction spans an LLM call, artifact upload or notebook execution.

Autosave begins only after conflict, retry, recovery, history and access-revocation tests pass. Debounce ordinary editing with a bounded maximum unsaved interval; flush on explicit navigation when possible without assuming unload requests will complete. A failed flush preserves in-memory work and offers explicit recovery. Server acknowledgment, not a local timer, changes the UI to Saved.

### 10.5 External AI provenance

Add a distinct externally AI-authored provenance category for ChatGPT and other external assistants. Store validated MCP client identity, submitting actor, submitted content hash, time, selected evidence and available declared model metadata. Model/conversation labels supplied by a client are declarations, not cryptographic attestations.

Do not fabricate internal draft-request or message IDs to satisfy existing native assistant constraints. Imported unknown text retains unknown/imported origin rather than being promoted to human-authored. Editing, copying or accepting text creates derived provenance, not a reset. The renderer and all exports must show the appropriate origin and human-review state.

### 10.6 Migration and cutover sequence

1. Inventory current schema heads, source-version coverage, active clients, documents and exports. Capture an authorized backup and prove restore in an isolated environment before production cutover.
2. Add new tables and constraints through additive migrations. Do not modify a deployed migration or create a second Alembic head.
3. Build a deterministic converter from a v1 snapshot to typed records. Preserve existing UUIDs, order, text, archive state, assistant provenance, quote snapshots and dependency meaning. Store conversion version and a mapping/verification manifest.
4. Dry-run conversion on copied fixtures and an explicitly authorized data snapshot. Compare counts, references, renderings and exports; do not auto-bind unmatched sources.
5. For a selected project, acquire its write lock, verify the v1 revision has not changed, convert and verify atomically, then mark the new storage generation authoritative. Abort without partial state on any mismatch. Large data preparation may occur before the lock, but the final compare-and-swap is mandatory.
6. Retain the pre-cutover v1 snapshot read-only. There is one authoritative write path per project, never permanent dual writes. An old client attempting a v1 write receives an explicit upgrade/conflict response that preserves its local content.
7. Make legacy bookmarks resolve to equivalent new views. The v1 frozen snapshot is clearly historical; it is not presented as current research state. Keep existing paper, note and discussion APIs unchanged unless a separately tested contract requires a change.
8. Roll out by explicit pilot-project migration state, not opaque random feature flags. Verify one complete research loop and export round trip before migrating more projects.
9. Rollback new UI/services only to versions that understand already migrated records, or place affected projects read-only while repairing. Never send new v2 writes to old v1 code or downgrade/drop tables as an application rollback.
10. Reconcile retained histories, artifacts, backups and privacy/deletion policy before retiring obsolete read paths in a later separately approved change.

## 11. AI assistance, cost control and research quality

### 11.1 A bounded assistant, not an autonomous authority

Expose explicit task types: search planning, evidence extraction suggestion, setup comparison, candidate reconciliation, critique, experiment-specification proposal, notebook-code proposal, board organization and manuscript revision. Each has an input schema, allowed sources/tools, output schema, budget, stop condition and review step.

Use the current provider abstraction and durable request infrastructure rather than adding an orchestration platform. A simple state machine suffices: prepared → authorized → queued/running → completed/failed/uncertain → reviewed → applied/discarded. State reads, reconnects and progress polling do not generate or retry.

The assistant cannot create verified evidence by assertion. Structured output is validated against selected IDs and source versions, then checked by a person for support. Any model-based verifier is an additional signal, not an independent empirical witness or a replacement for human acceptance.

### 11.2 Context policy

Compose context from current project state, selected records, bounded retrieved passages and user instructions. Explicitly exclude other members' private notes, unapproved local files, hidden restricted artifacts and unrelated conversations. Show a compact “what will be sent” preview and provide a manual mode.

Reuse source parsing, cached exact passages and stable selected context to reduce repeated token use. Cache keys include relevant content versions, model/prompt configuration and authorization scope; cached content is access-checked again. Do not share private embeddings, response caches or provider prompt-cache identifiers across unrelated users/projects.

New external content is data, never control instructions. A paper telling an agent to upload credentials or ignore policy has no authority. Model-generated URLs, paths, SQL and commands do not bypass service validators or local approval.

### 11.3 Budget ledger

Before an explicit paid action, estimate input/output, calls, search requests and possible repair attempts; reserve the allowed maximum or a conservative bounded amount using a versioned pricing table. Set project/session/run caps, output limits, concurrency limits and a platform-level stop switch. Reconcile actual usage and expose estimates separately from settled charges.

Never assume a ChatGPT subscription pays for OpenPaper's API inference, Exa, E2B or cloud jobs. An external ChatGPT-authored proposal need not invoke another paid platform model; validating schemas and anchors is deterministic. Local provider keys stay local unless the user explicitly configures a cloud provider, and no key enters MCP results or manifests.

For uncertain provider completion, retain the reservation or unresolved cost status pending reconciliation. Do not promise an invoice-exact hard cap where provider metering is delayed; enforce admission limits and bounded in-flight exposure. Price-table changes or missing price data block unapproved spending, not manual research.

No monthly dollar budget is invented here. Implementation must request or use an already configured explicit budget before live calls. Cost reports separate fixed infrastructure, parsing/indexing, model/search/compute usage, storage/egress and local compute.

**Delivery prerequisite:** the admission/reservation, idempotency and uncertain-completion core belongs in P02, before any new metered dispatch is enabled in P04, P06 or later packages. C29 must pass for each enabled paid operation before that operation ships, not only when P11 is reached. A cost preview or user click alone does not satisfy this gate. Until an operation has enforceable limits and replay handling, its metered dispatch stays unavailable; deterministic import, local parsing and manual research remain usable. P11 extends the established ledger with cross-workspace AI task types and reporting rather than introducing spending enforcement for the first time.

### 11.4 Model quality evaluation

Build a human-reviewed AI-safety retrieval and synthesis set using authorized sources and synthetic boundary cases. Include no-evidence questions, ambiguous formulations, contradictory setups, unsupported causal claims, inaccessible sources and contamination-sensitive examples.

Measure retrieval recall and ranking, exact anchor correctness, citation support/unsupported claims, appropriate uncertainty, context leakage, proposal acceptance/edit distance and cost per useful accepted result. Report both failures and exclusions. Do not optimize solely for polished prose, number of papers collected or agreeable answers.

Use cheaper deterministic or smaller-model routes only when the evaluation supports them. Route difficult synthesis to a stronger model by explicit policy and budget; do not silently multiply calls into an ensemble. Actual live quality acceptance is separately authorized and cannot be inferred from mocked-provider tests.

## 12. Native ChatGPT integration through MCP

### 12.1 What native integration means

Keep a remotely reachable, authenticated MCP endpoint over HTTPS, backed by the same research services as the web app. Prefer a tested Streamable HTTP path. An SSE response inside Streamable HTTP is different from the older HTTP+SSE transport; pin and test the installed FastMCP/SDK and actual ChatGPT client's supported protocol versions.

Official documentation evolves, including newer protocol and MCP Apps/UI conventions. Do not adopt the newest transport revision blindly or assert that the current ChatGPT account supports every feature. Negotiate and test the supported intersection through the existing reverse proxy, including disconnects and retries.

Preserve the existing compatible `search`/`fetch` tools for research-oriented surfaces. Domain-specific tools serve general custom-MCP use. Optional Apps SDK/MCP Apps components can show a source inspector or proposed manuscript diff inside ChatGPT, but tools must remain usable without those components. Do not rebuild the entire platform in an embedded ChatGPT UI.

ChatGPT sees only selected authorized cloud material. It does not connect to localhost, acquire a local notebook token or read the research directory by virtue of the MCP connection. Any optional tunnel product is outside this design's default trust model.

### 12.2 Proposed bounded tool surface

Names below describe proposed contracts; they are not claims that these tools already exist. Retain useful current tools and avoid introducing redundant aliases.

| Operation | Contract | Side effect |
| --- | --- | --- |
| `search` / `fetch` | Authorized, citable versioned research items; complete bounded items or explicitly identified sections | Read only. |
| `get_investigation_context` | Question, argument, reviewed findings, gaps, next actions, versions and coverage; cursor pagination | Read only; replaces neither private note ownership nor complete export. |
| `list_research_items` / `get_research_item` | Typed claims, findings, board summaries, protocol versions and manuscript sections | Read only, bounded views. |
| `inspect_artifact` | Approved run manifest, metric slice, sanitized notebook excerpt or figure metadata | Read only; never execute content. |
| `propose_change` | Whitelisted semantic patch, target versions, selected evidence and request ID | Persists an unaccepted proposal; is a write. |
| `stage_import` | Source descriptor, destination and request identity; validation/duplicate review | Quarantines or stages an import; network/paid parsing requires separately approved policy. |
| `get_operation_status` | Existing request/proposal/import receipt and state | Read only; no retry or hidden recovery action. |
| `apply_approved_change` | Exact proposal ID, expected revisions and idempotency key | Later capability; requires a server-recorded authenticated approval. |

Do not expose generic SQL, arbitrary HTTP fetch, arbitrary file paths, shell, kernels, package installation, unrestricted deletion, publishing or deployment. Explicit existing import tools must continue using approved source policies and per-object access checks.

Read responses include object IDs, version/digest, provenance, canonical application links, completeness/coverage and next cursor. Default context targets a small summary; deep fetches retrieve bounded sections. Search/fetch compatibility must not silently truncate an item while claiming to return its full text.

### 12.3 OAuth and permission requirements

Reuse a maintained, standards-compliant OAuth implementation and inspect the installed FastMCP broker behavior before deciding whether to extend or replace it. Google sign-in can remain upstream identity authentication; it is not automatically the ChatGPT-facing authorization contract.

Required checks include protected-resource metadata, authorization-server discovery, authorization-code flow with advertised PKCE S256, exact redirect validation, issuer checks, resource/audience binding, scopes, expiry and revocation. Support only client registration methods actually implemented and accepted by the account; current documentation includes predefined clients, CIMD and DCR with version-dependent recommendations.

Do not confuse upstream Google identity-token audience with the resource audience of the MCP access token. Validate each at its own boundary. Never pass ChatGPT's bearer token to downstream providers or accept an arbitrary downstream token as authority for the platform. Audit per-user/per-MCP-client consent, including dynamic registration if enabled.

Define app scopes such as research read, proposal write, approved import and approved apply; combine scopes with current project roles and object rights. OAuth scopes do not substitute for row/object authorization. Use separate client identities/audiences for a local companion; a ChatGPT grant must not authorize local device control.

Refresh tokens, if issued, use appropriate rotation/reuse detection and secure storage; revocation invalidates grants and associated refresh families under a documented access-token expiry policy. Do not assume disconnecting an app in ChatGPT invokes server revocation; test both explicit platform revoke and account-side disconnect.

### 12.4 Approval and provenance

Tool annotations and UI confirmations are descriptive safeguards, not access control. A tool that writes a proposal is not read-only. Hiding a tool in a component or receiving `confirmed=true` from a client does not prove approval.

Consequential application requires a server-recorded approval from the authenticated platform review flow, bound to the actor, exact proposal hash, target versions, permissions and expiry. Revalidate at application time and consume/replay it safely. A stale proposal returns to review. Notebook execution still requires local consent even if a cloud proposal was approved.

External ChatGPT text retains external-AI origin under section 10.5. The app can verify received bytes and client/actor identity; it cannot attest to a model name the external client did not securely establish.

### 12.5 Account-side acceptance

Operator verification must establish actual ChatGPT plan, workspace, role, admin approval, allowed surfaces, tool-write availability and optional component support. Documentation is not proof of account entitlement. A working protocol test is not proof that attachment handoff, tool refresh or the selected workspace works.

Test a fresh connection, search/fetch, bounded current investigation context, a proposed paragraph, authenticated review/application/readback, stale conflict, revoked access, expired token, refreshed grant and disconnect. Test optional UI separately. Use synthetic material first; no paid platform inference is required for these deterministic tool checks.

## 13. Security, privacy and trust boundaries

### 13.1 Identity and authentication

Default to private projects and invitation-based collaboration. Reuse current sign-in where it meets requirements rather than migrate identity providers for novelty. Require verified identity; protect account linking against email changes and ambiguous identity merges. Provide visible active sessions/devices, revoke-all, logout and recovery behavior.

Harden cookie sessions with Secure/HttpOnly and an appropriate SameSite policy; protect state-changing browser requests against CSRF; enforce strict origin/CORS rules. Check idle and absolute lifetimes, session rotation, fixation resistance, OAuth state/nonce and redirect handling. Never store access or refresh tokens in browser localStorage.

Use managed passkeys/MFA or the upstream identity provider's supported assurance mechanisms where available; do not build custom cryptography or claim Google login alone proves MFA. Require recent authentication/step-up for credential changes, new device pairing, broad sharing and other high-consequence operations. A lower-assurance fallback must not silently bypass a configured assurance requirement.

### 13.2 Authorization and roles

Preserve owner/admin/editor/viewer semantics and current private-note ownership. Map source association, review assignments, artifact classification, proposal approval and device grants explicitly. Harmonize owner-without-membership behavior across API and MCP without accidentally granting broader rights.

Every query and mutation is scoped by current actor/project, including caches, search, revisions, history, exports, signed URLs and job callbacks. An artifact's parent-project UUID is checked server-side, not trusted from client input. Hash equality and object-store path knowledge never grant access.

Keep the application authorization service authoritative. Add database row-level security only as a separately verified defense-in-depth measure with transaction-local tenant context, pool reset tests and narrowly defined worker roles; do not claim RLS exists today or rely on it without those tests. Comprehensive project-scoping tests are mandatory regardless.

### 13.3 Threat model and required controls

| Threat | Enforcement and acceptance focus |
| --- | --- |
| Cross-project access / confused deputy | Central service authorization, scoped grants, opaque IDs, per-request checks, cross-user fixtures and revoked-membership tests. |
| Prompt injection in papers, websites, notebooks or logs | Treat retrieved content as data; narrow tool schemas, allowlisted actions, independent approval and no credential-bearing context. |
| SSRF via imports, previews or OAuth metadata | Approved schemes/hosts as applicable, DNS/address/redirect validation, private/link-local/metadata blocking, pinned resolution strategy and byte/time limits. |
| Malicious PDFs, archives, images and converters | Separate low-privilege parser/conversion processes, bounded resources, patched libraries, archive traversal/decompression limits and quarantine. |
| Notebook/output XSS | No active notebook HTML/widgets on the primary origin; sanitization/isolated previews; CSP and safe downloads. |
| Local credential theft / arbitrary execution | No remote kernel, narrow workspace mounts, local approval, OS-level isolation, restricted network and no ambient cloud credentials. |
| Token theft/replay | TLS, scoped short-lived access, secure refresh handling, token-family revocation, no secrets in logs/manifests/URLs shared with tools. |
| Approval/TOCTOU races | Approval binds immutable digest and target versions; repeat permission/version checks at apply/upload/run boundaries. |
| Cost denial / runaway processing | Admission budgets, quotas, concurrency/resource limits, bounded retries, cancellation and uncertain-job reconciliation. |
| Sensitive artifact disclosure | Private storage, minimal upload, classification, short-lived capabilities, redacted derivatives and explicit export/share review. |
| Compromised dependencies | Locked builds, vulnerability/license checks, software inventory and reviewed updates; no runtime installation of model-suggested packages. |
| Data loss | Revision history, tested backups/restores, retention policies and rollback that preserves migrated data. |

### 13.4 Local companion controls

Use a public-client OAuth flow with PKCE or another maintained pairing mechanism supported by the selected identity implementation. Pair from a local action, verify the account and project in both places, and store recoverable credentials in an OS credential store. WSL2/native-platform storage must be tested; do not silently fall back to world-readable plaintext.

Bind approvals to canonical paths under user-selected roots and exact immutable file bytes. Reject traversal and symlink escapes; revalidate file identity at publication to prevent replacement after preview. Retry the approved snapshot, not whatever later occupies the same pathname.

Jupyter listens on loopback with its own authentication and origin/host protections. Keep its token local. Do not disable XSRF checks, authentication or host validation for integration convenience. Localhost is not a sufficient defense against malicious browser requests or DNS rebinding.

Executing a notebook runs code with its kernel privileges. For untrusted code, use an appropriately configured isolated OS account/VM or sandbox with minimal mounts, resource limits and enforceable network policy. A container or a natural-language instruction alone is not the required security boundary. Record the selected isolation strength and reject stronger claims on unsupported OS/GPU configurations.

### 13.5 Data lifecycle and operations

Private artifacts use encryption at rest and in transit, separate application/worker/backup permissions and controlled secret rotation. Store only needed research text in logs; default telemetry to IDs, timings and status rather than paper content, prompts or tokens. Restrict audit access and define retention.

Signed download URLs are bearer capabilities. Limit them to exact object/version, short lifetime and appropriate content disposition; do not persist them in manuscripts, MCP records or Git. Short lifetime does not provide instantaneous revocation after issuance. Highly restricted artifacts may require authenticated streaming instead of direct capabilities.

Backup success is not restore success. Test restoration of relational state and referenced artifacts together, including identity mappings, revisions, encrypted token dependencies and source permissions. Prefer not restoring active sessions/grants blindly after an incident; document forced reauthentication and key recovery.

Do not claim SOC 2, ISO 27001, GDPR compliance or end-to-end encryption from architectural intentions. Maintain a privacy/retention description and controls evidence; pursue formal assurance only if a real requirement and audit scope justify it. Uploaded copyrighted papers, datasets and model outputs retain their licenses and access restrictions regardless of platform features.

## 14. Implementation technology choices and existing extension points

### 14.1 Default choices

These are decisions for subsequent implementation, subject to the bounded compatibility checks named here—not instructions to install packages now.

| Area | Default | Reason / rejection criterion |
| --- | --- | --- |
| Web platform | Keep Next.js, React, existing Radix/shadcn, styling and SWR conventions | A framework rewrite would not improve the research model. Upgrade supported versions in bounded maintenance work, not an unrelated rewrite. |
| Freeform research board | React Flow as the graph/card interaction foundation, with explicit presentation/semantic distinction | Custom nodes and edges fit the mixed research model. A spike must prove arbitrary placement, grouping, undo, accessibility and target performance; retain a list view. Do not describe a hierarchical graph alone as the required freeform board. |
| Manuscript editor | Tiptap/ProseMirror using suitable open-source core/extensions and custom typed nodes | Schema-based editing, custom citations and export adapters. No dependency on paid collaboration or proprietary cloud storage for the core workflow. |
| Tables | A virtualized typed table layer, preferably TanStack Table/Virtual after compatibility checks | Separates editing/filtering from analytical execution; does not require loading every row. Existing simple tables can remain until migrated. |
| Native reading | Existing pinned upstream Textfold integration | Preserve the actual engine and tested invariants; use sanitized derived previews. |
| Research services | Existing FastAPI/Pydantic/SQLAlchemy modules with shared authorization and transactions | API/MCP consistency; avoid duplicated business rules. |
| Persistence | PostgreSQL relational identities/revisions plus bounded typed JSON | Strong relationships and useful indexing without a new database. |
| Analytical storage/compute | Parquet, Arrow IPC, native DuckDB; optional worker-isolated DuckDB-Wasm | Efficient for large tables; not required for ordinary reading/editing. |
| Local notebooks | Existing JupyterLab plus a small paired companion | Preserve a mature scientific environment; avoid a new cloud IDE or exposed kernels. |
| Publication | Local pinned Quarto/Pandoc and tested CSL/venue assets; cloud rendering only if later justified | Reproducible conversion without automatic notebook execution. |
| MCP | Existing maintained FastMCP stack, upgraded only after interoperability tests where necessary | Reuse infrastructure but audit discovery/token/scope behavior rather than assume compliance. |
| Search | PostgreSQL FTS + scholarly provider adapters; evaluate hybrid retrieval later | Lower operating cost and clear coverage at personal scale. |

React Flow's accessibility primitives and memoization guidance are helpful starting points, not acceptance evidence. Tiptap custom node views are distinct from serialized/exported output; test both. License and package-version review is mandatory for all selected extensions and redistributed tools. OpenPaper's AGPL obligations, Textfold notices and transitive/bundled tool licenses must remain intact.

### 14.2 Verified current source seams

Links are starting points, not a requirement to put every new capability in these files. New modules should have clear bounded responsibilities; do not turn the current workspace component or MCP registration file into a monolithic feature implementation.

| Current seam | Observed behavior and revamp implication |
| --- | --- |
| [Database models](../../server/app/database/models.py#L1818) | One current investigation JSONB row and durable draft requests; new review/board/run records need new storage, not arbitrary fields in v1. |
| [Strict schema](../../server/app/schemas/investigation.py#L108) and [client contract](../../client/src/lib/investigation.ts#L3) | Coordinated client/server/bundle versioning is required. |
| [Investigation service](../../server/app/services/investigation.py#L117) | Reuse conditional write, source-validation and provenance semantics; extend via shared services. |
| [Investigation provider](../../client/src/components/project/InvestigationProvider.tsx#L15) | Explicit save and recovery today; autosave must wait for the new concurrency contract. |
| [Current workspace](../../client/src/components/project/InvestigationWorkspace.tsx#L79) | Structured textarea drafting today; rich editor is a real new implementation, not a cosmetic restyle. |
| [Draft service](../../server/app/services/investigation_drafting.py#L111) | Preserve durable claim, single-attempt provider boundary and failed/uncertain states. |
| [Export service](../../server/app/services/investigation_export.py#L18) | Preserve access redaction, imported-source distrust and portable exports. |
| [Native reader](../../client/src/lib/textfold-native/index.ts#L28) | Derived preview; not a manuscript editing or shared-annotation store. |
| [MCP server](../../server/app/mcp/server.py#L50) and [research context](../../server/app/mcp/research.py#L137) | Existing paper/project tools do not expose investigation, board, manuscript, review or notebook state. |
| [Source endpoint](../../server/app/api/projects/project_investigation_api.py#L49) | Indexed-only search and exact line inspection; no guaranteed PDF page mapping. |
| [Compute helper](../../server/app/helpers/compute_agent.py#L299) | E2B table computation is distinct from local Jupyter; verify actual isolation and retry costs before extension. |
| [Task transport](../../server/app/helpers/task_backend.py#L34) and [job runner](../../jobs/src/app.py#L63) | Reuse configured backend and allowlisted job types; do not expose an arbitrary execution RPC. |
| [Client scripts/dependencies](../../client/package.json#L5) and [isolated database tests](../../server/tests/test_project_investigation_postgres.py#L39) | Extend real verification entry points, including browser and database evidence; retain required non-skipped lanes. |

Specific integration issues to resolve early: API/MCP differences in owner-versus-membership authorization; private versus shared-paper context; native assistant provenance versus external AI proposals; v1 source anchors versus run artifacts; table computation provenance versus accepted evidence; and existing import/readiness behavior versus the new no-surprise-spending UX.

## 15. Performance, cost and operational targets

### 15.1 Workload assumptions

Design first for one primary researcher, with up to five concurrently active collaborators/analytical sessions as a test envelope—not a promise of production scale. Benchmark a project with 500 sources, 2,000 findings, 1,000 board items across named boards, 1,000 manuscript blocks, 10,000 review candidates and 100 experiment runs. Large projects must paginate and progressively load rather than inflate the initial response.

Analytical fixtures: 100,000, 1 million and 10 million rows; numeric, nullable, categorical/string-heavy and nested variants. The smallest fixture is the browser interaction target. Larger datasets are analyzed locally or in bounded jobs, with aggregates/subsets sent to the browser. Model weights are not browser table assets.

Reference test environments must be recorded: a representative 16 GB development desktop, a 390 px mobile viewport with constrained memory/CPU, and a stated network profile. These are proposed test conditions, not detected hardware. Record real cloud/database/object-storage regions before assuming locality; do not migrate regions from this planning document.

### 15.2 Initial budgets and measurements

| Concern | Proposed target / acceptance method |
| --- | --- |
| Manual interaction | p95 interaction latency ≤200 ms for tested ordinary edits, selection and navigation after relevant data is loaded. |
| Warm project entry | Useful question/next-action surface ≤2 seconds on the defined desktop/network profile; no eager PDF/canvas/WASM downloads. |
| Cold project entry | Measure separately; initial goal ≤8 seconds to useful content. Show honest loading and retry. Do not mask cold-start results with warm averages. |
| Initial project payload | Summary JSON ≤250 KB uncompressed; full findings, reviews, notebook outputs and manuscript bodies are separately paginated. |
| Ordinary warm API reads | p95 ≤500 ms for bounded summary/item reads, measured with query count and database checkout time. Parsing and analytics are separate jobs. |
| Canvas | 1,000 stored items with viewport culling/collapse; benchmark about 200 visible simple cards, p95 frame time ≤32 ms while panning, with usable keyboard/list fallback. |
| Analytical browser memory | Starting incremental worker/analytics budget ≤512 MiB on desktop; no dependency on the theoretical WASM memory ceiling. Mobile uses smaller subsets and aggregates. |
| Analytical transfer | Initial browser subset capped at the lower of 100,000 rows and 50 MB transferred; exceedance requests aggregation/local analysis rather than attempting an unbounded load. |
| Analytical latency | Measure download and compute separately. After data is loaded, common aggregate/filter results target ≤2 seconds on the defined small fixture. |
| Source/citation navigation | No lost editor state; one authorized source inspection path, with loading/error/unknown-page states measured. |
| Idle operation | Zero provider calls. Device synchronization uses adaptive/backoff behavior; no per-second permanent polling. |
| Reliability | No lost acknowledged edits in injected application failures; interrupted jobs have discoverable states and recoverable receipts. |
| Recoverability | Proposed initial production objectives: RPO ≤24 hours and RTO ≤4 hours for research state/artifacts, only claimed after backup configuration and a timed restore drill prove them. |

Performance targets are revisionable engineering budgets. A missed budget requires a recorded profile and explicit disposition, not silently lowering the target or announcing success from a build passing.

### 15.3 Benchmark Arrow rather than assume it wins

Compare compressed JSON, Arrow IPC with appropriate compression choices, and Parquet for representative operations. Measure end-to-end and stage-level p50/p95, CPU, peak RSS/PSS or browser memory, allocated/transferred bytes, request count, time to first useful result, completion, cancellation and output equality.

Record where copies occur: source decode, Python conversion, transport, worker handoff, WASM ingestion, query materialization and UI row rendering. Use native Arrow interfaces when beneficial, but retain JSON for small results if it is simpler and as fast. Choose row-group/batch sizes from measurements; avoid tiny-file proliferation.

Test HTTP range correctness, expired capability renewal, malformed files, oversized/nested data, cross-tenant denial and interrupted streams. A partial range cannot be independently checked using only a full-file SHA-256; distinguish transport checks, full-object verification and any deliberately designed chunk manifest.

### 15.4 Cost controls and deployment shape

A project cost report uses this decomposition:

**Fixed application/database cost + stored bytes + storage/region egress + parsing/indexing/conversion CPU + external search + model inference + sandbox/experiment compute.**

Record unit prices and timestamps rather than embedding guessed vendor prices in this plan. Measure idle week cost, ten-paper import cost, one explicit synthesis task, a small local-evaluation publication and a manuscript export. Obtain approval before any workload that incurs new spending.

Default cloud scale-to-zero where compatible with the measured UX; justify minimum instances with observed cold-start cost/latency. Bound instance count, job concurrency, database pools and inflight requests together. Instance caps alone do not bound provider spending.

Reduce hops by using shared in-process services and direct authorized artifact transfer; reduce repeated work with immutable artifact/content identities and versioned caches. Place analytical processing near data where approved and feasible; cross-provider region changes are not justified until measured egress/latency outweigh migration risk and residency requirements.

### 15.5 Observability and incident recovery

Propagate correlation IDs across browser, API, MCP, queue jobs, local run receipts and artifact publication, without logging secrets or entire research documents. Track failed saves/conflicts, source-version changes, revoked-access denials, job age, retries, budget reservations, uncertain provider completions, missing artifacts and backup age.

Provide a compact project status/doctor view: source readiness, index coverage, stalled jobs, local device status, unresolved reviews and reproducibility completeness. A disconnected local machine is not a failed cloud experiment; show the last acknowledged state and where execution actually lives.

Alert only on actionable conditions: repeated save failures, stuck paid requests, unauthorized access anomalies, backup failures and budget thresholds. Avoid alerts for expected scale-to-zero or an intentionally offline laptop.

## 16. Delivery plan: dependency-ordered, agent-independent work packages

### 16.1 Execution rules

Each package must leave a usable vertical slice, its versioned contracts, tests, executed evidence and a precise handoff. A package is not complete because files compile or mock screenshots look plausible. Unexecuted checks remain pending with the reason; never convert them to passes.

For each package, the implementer records baseline commit/tree, files and schemas affected, authorization/side effects, test commands actually available, fixture versions, failures and resolutions, migration/rollback behavior and the next step. Use the repository's MEOS lifecycle and current work pointer; no particular agent/model is required.

Dependencies define order, not a requirement to run several agents. Separate implementation tasks may run in parallel only when their schemas/interfaces are agreed and file ownership does not conflict. Avoid speculative scaffolding for later packages.

### 16.2 Package definitions

#### P00 — Re-establish the baseline and secure extension seams

- **Depends on:** nothing; read the current release records and actual repository state first.
- **Deliver:** inventory of deployed/source divergence, existing test commands, role semantics, current OAuth behavior, computed-column execution/retry boundaries and outstanding operator gates. Preserve all existing records.
- **Checks:** reproduce applicable current local regression suites in an isolated setup; verify owner/member/private-note parity and no-provider boundaries; classify existing E2B network control and webhook/retry behavior without executing unsafe code or paid calls.
- **Exit:** baseline invariants and unresolved issues have named evidence; no new source of insecure or unbudgeted execution is carried into the new surface. Existing A25 remains pending until an operator actually exercises it.
- **Rollback:** no production change; documentation/test fixtures are reversible.

#### P01 — Prove the product loop and freeze interface contracts

- **Depends on:** P00 inventory.
- **Deliver:** navigable, fixture-backed interaction prototype for Overview → finding → board → experiment specification → manuscript, plus desktop/mobile states, schema/API proposals, the review identity/count policy from section 6.1, and the golden fixture in section 17 with expected counts. No fake research results.
- **Checks:** first-value usability exercise; keyboard path; single-inspector behavior; clear support/challenge/qualification and source-versus-interpretation distinctions; manual work with AI disabled.
- **Exit:** coherent navigation and stable identifiers/data ownership are established; confirm React Flow and editor compatibility/licensing without building the whole feature set.
- **Rollback:** prototype remains isolated from authored production data.

#### P02 — Implement versioned research identity and safe persistence

- **Depends on:** P00/P01 contracts.
- **Deliver:** source versions, typed research entities/relations, review occurrence/report/candidate/study identities and mapping events, revision history, shared authorization, conditional transactions, external-AI provenance, proposal/approval core, the metered-operation admission/reservation/replay core and deterministic v1 conversion.
- **Checks:** schema bounds, dangling IDs, source forgery, project isolation, race/rollback, retry receipts, stale dependency review and lossless conversion/export comparison on fixtures. Verify the count-policy fixture and C29 with fake metered providers before any new paid operation can be enabled. One Alembic head and additive migration discipline.
- **Exit:** one v1 project converts atomically in an isolated database and retains every claim, finding, citation, quote snapshot, origin and manuscript block; no dual-write ambiguity.
- **Rollback:** original v1 snapshot retained; failed conversion leaves original authority intact. Production cutover is not part of this package unless separately authorized.

#### P03 — Ship the guided shell and low-friction manual workflow

- **Depends on:** P01/P02.
- **Deliver:** six-destination shell, onboarding, Overview/Case guidance, contextual inspector, review queue, history/conflict recovery and safe autosave for migrated records only.
- **Checks:** manual first-value journey; actual dev-server/browser use at desktop and mobile widths; reload/navigation/network failure; two-tab conflicts; revocation; light/dark/reduced-motion; zero provider calls.
- **Exit:** research can be created, resumed and safely edited without AI, ChatGPT or a notebook companion.
- **Rollback:** retain legacy read/view routes and data-compatible service version; disable new edits explicitly if a severe persistence defect appears.

#### P04 — Connect discovery, reference identity and evidence tables

- **Depends on:** P02/P03.
- **Deliver:** identifier/BibTeX/RIS imports, duplicate/version review, readiness/coverage, typed extraction cells, method comparison and bounded search adapters. Source-region improvements remain honest when page mapping is absent.
- **Checks:** exact duplicates versus distinct versions, malformed bibliography, unauthorized URLs, missing full text, multiple-page results, Unicode/null/unit handling and cell-level citation inspection. Import planning shows any nonzero inference/search costs.
- **Exit:** papers, existing table outputs and accepted findings connect without manually copying uncited values; deterministic CSV/XLSX exports retain a provenance companion sheet/manifest. Each enabled metered import/search path passes C29 against its P02 admission controls; otherwise only its deterministic/manual path ships.
- **Rollback:** new adapters can be disabled without deleting existing sources or changing their identity.

#### P05 — Deliver the scientific manuscript editor

- **Depends on:** P02/P03 and source/citation contracts from P04.
- **Deliver:** rich editor, typed citations/quotes/gaps, math/figures/tables, manual evidence assembly, comments/history, native Textfold preview and basic portable exports.
- **Checks:** citation → finding → exact source; stale source and revoked access; quotation editing rules; AI origin preservation; crash/conflict recovery; schema/export round trips; no inference for writing or preview.
- **Exit:** a complete short manuscript can be authored manually and reloaded/exported with evidence relationships intact. Legacy paragraphs import without changing scientific meaning.
- **Rollback:** retain semantic document snapshots and export; never discard blocks the legacy textarea editor cannot express.

#### P06 — Extend and harden native ChatGPT/MCP integration

- **Depends on:** P02; P03/P05 for authenticated proposal review UI.
- **Deliver:** current investigation context, item/artifact reads, proposal staging, capability/version diagnostics, scoped authorization and approval receipts. Add optional embedded evidence/diff UI only after tools work independently.
- **Checks:** transport/discovery/PKCE/audience, exact callbacks, scopes, refresh/revoke, access parity, bounded context, hostile tool inputs, immutable external-AI origin, duplicate/stale proposal application and forged approval rejection.
- **Exit:** protocol tests pass and deterministic browser review works. Any tool that dispatches metered imports/search/processing must also pass C29 using the P02 core before it is exposed; proposal-only and deterministic read/staging tools remain independent. Actual ChatGPT-account connection/refresh/attachment/UI acceptance is separately recorded as passed or pending, never inferred.
- **Rollback:** disable newly exposed tool capabilities; preserve stored proposals and existing compatible paper tools. Revoke affected grants if authorization defects appear.

#### P07 — Pair a local workspace safely

- **Depends on:** P02/P03 and device/auth contracts validated with P06 work.
- **Deliver:** initial Linux/WSL2 companion packaging, account/project pairing, OS credential integration, directory binding, local Jupyter launch, explicit snapshot upload and artifact receipts. No cloud-triggered execution.
- **Checks:** wrong project/account, revoked device, expired token, symlink/traversal, changed file after preview, interrupted upload, repeat publication, secret scanning/redaction warnings and offline behavior. Inspect listening ports; no public notebook/kernel service.
- **Exit:** a manually created local notebook and selected static outputs publish to the correct project once, without exposing other local files or credentials.
- **Rollback:** revoke device and remove only integration-owned local state after confirmation; leave research files untouched.

#### P08 — Complete reproducible local experiments and analytical views

- **Depends on:** P04/P07; P05 for manuscript artifact insertion.
- **Deliver:** frozen experiment specifications, local approval/run manifests, fresh-kernel versus exploratory status, Parquet/Arrow artifacts, native DuckDB analysis, bounded browser tables/plots and result-to-finding promotion.
- **Checks:** deterministic synthetic run, failed/interrupted run, dirty notebook, changed input/approval, no-network isolation where claimed, integer/decimal/null parity, memory caps, cancellation, artifact tampering and manuscript lineage. Real model runs require separate budget approval.
- **Exit:** question → local synthetic experiment → result → finding → manuscript figure is reproducible and inspectable without a paid provider call. Arrow adoption is backed by recorded comparisons, not a zero-copy slogan.
- **Rollback:** analytical UI can fall back to authorized precomputed aggregates/downloads; immutable runs/artifacts remain readable.

#### P09 — Ship the genuine freeform multimedia canvas

- **Depends on:** P02/P03; P04/P05/P08 supply the full card families.
- **Deliver:** arbitrary positioning, drag/restructure, groups, typed and presentation connectors, sticky notes, mixed media, templates, deterministic arrangement, history, saved views, list equivalent and permission-aware board export.
- **Checks:** moving a card changes no evidence; duplicate views do not duplicate findings; accepted content edits propagate to every view; deleted references leave canonical records; source revocation and malformed embeds; changed/unavailable remote video and rejection of link-only locators as verified evidence; keyboard/mobile/list paths; viewport performance.
- **Exit:** researchers can build a blank freeform board, combine a paper/video/image/claim/run/manuscript reference, restructure it and export it without losing evidence identity. Textfold remains available, not substituted for the board.
- **Rollback:** disable editing a broken presentation layer while retaining board records and the accessible outline; do not delete canonical research records.

#### P10 — Deliver the rigorous literature-review pipeline

- **Depends on:** P02/P04 and usable shell from P03.
- **Deliver:** protocol versions, search sets, dedup records, staged screening, independent reviewer decisions, adjudication, cited extraction, amendment review and count-derived reporting/flow diagrams.
- **Checks:** two reviewers cannot see each other's pending decisions in independent mode; conflicts require explicit adjudication; solo/AI-assisted reviews are labeled honestly; amended criteria invalidate affected decisions; count reconciliation and retraction/version updates.
- **Exit:** a small fixture review can be reconstructed from search retrieval through final inclusion and cited extraction, with every flow count opening its actual records.
- **Rollback:** retain immutable decisions/protocols; presentation changes cannot rewrite historical counts or final decisions.

#### P11 — Add bounded AI assistance across the connected workspace

- **Depends on:** P04–P10 contracts for the capabilities being assisted; do not delay manual versions awaiting AI.
- **Deliver:** explicit context/budget preview, typed task proposals, source-grounded drafting/critique, extraction suggestions, board expansion, search plans and notebook-code proposals; extend the P02 task/usage ledger with these task types and quality evaluations. Budget enforcement is already a prerequisite for earlier metered capabilities.
- **Checks:** fixture/fake-provider tests for invalid citations, injection, unapproved tools, quota, provider timeout, ambiguous completion, duplicate retry, stale dependencies and provenance; independent human review of separately authorized live samples.
- **Exit:** every assisted action has a bounded input/output contract, cost disposition, review/apply boundary and useful manual alternative. AI never silently screens in/out, runs code, publishes, or rewrites accepted claims.
- **Rollback:** disable provider dispatch while preserving manual work and saved proposals; never delete uncertain request identities to allow blind retries.

#### P12 — Publication, operational hardening and release acceptance

- **Depends on:** completed target packages and their local evidence; can prepare infrastructure checks earlier.
- **Deliver:** tested DOCX/LaTeX/PDF and board exports, research reproducibility bundles, permissions/sharing review, license inventory, backup/restore evidence, cost/latency dashboards, security regression matrix and a data-compatible rollout/rollback plan.
- **Checks:** full golden journeys, existing regressions, real browser use, isolated PostgreSQL transactions, malicious imports/outputs, publication rendering sandbox, restore drill and measured performance budgets. Fresh production/account and live-AI checks require explicit authorization.
- **Exit:** independent review has no unresolved release-blocking findings; every promised capability is either evidenced or explicitly outside the selected release. Open account/live gates cannot be described as full acceptance.
- **Rollback:** documented traffic/service rollback compatible with migrated schema, retained artifacts and revocation plan; never a destructive schema downgrade.

### 16.3 Milestones and parallel opportunities

| Milestone | Packages | User-visible result |
| --- | --- | --- |
| A — Safe connected research core | P00–P05 | Guided evidence-to-manuscript workflow with durable identity, history and low-friction manual authoring. |
| B — Connected assistant and local lab | P06–P08 | ChatGPT can inspect/propose; local experiments produce traceable findings and figures. |
| C — Both reference paradigms fully represented | P09–P10 | Real freeform multimedia boards and an auditable systematic-review workflow over the same records. |
| D — Reviewed AI-native platform | P11–P12 | Bounded assistance, publication/reproducibility, security, costs and operational evidence. |

P06 and early P07 can proceed alongside manuscript work after P02 contracts stabilize. P09's board foundation can proceed alongside P08; final card-family acceptance waits for actual artifacts. P10 can run alongside canvas/lab work after P04. P11 can add one validated task at a time, but milestone D requires complete cost/approval boundaries.

Canvas and systematic review are part of the intended complete platform, not optional omissions hidden behind an MVP label. The milestones allow useful interim releases; no interim release should be called the completed all-in-one revamp. Package sizing and calendar estimates should be produced from implementation spikes and available capacity, not fabricated here.

## 17. Acceptance specification and golden research fixture

### 17.1 Golden fixture

Use a small, openly usable or synthetic corpus with explicit fixture labels:

- Two papers that appear to disagree but differ in task/setup, a companion report of the same experiment as one paper, one qualifying paper, repeated retrievals, a duplicate download and a later version. The exact count fixture below also includes a title/abstract-excluded report.
- One source without full text, one missing page map, one source revoked during the workflow and one malicious-instruction excerpt treated as inert data.
- A claim with supporting, challenging and qualifying findings; a documented candidate reconciliation and an unresolved gap.
- A review protocol with title/abstract and full-text stages, disagreement/adjudication, an amendment and known expected counts.
- A small deterministic local notebook with no provider call, plus a deliberately failed run and a dirty/out-of-order exploratory notebook.
- A typed result table including nulls, exact large integers, units and timestamps; a figure with dataset/query/run lineage.
- A freeform board containing structured cards, a sticky note, an image, a safe video/timecode link and presentation-only connectors.
- A manuscript containing human prose, an exact quotation, native-AI and external-AI fixture proposals, a figure, a stale citation and an explicit gap.

Never present fixture outputs as measured real-model results. Use the same stable IDs/manifests across API, browser, MCP, local companion and export tests, with account-specific IDs isolated for authorization cases.

#### Exact review-count fixture

For the default literature-review count policy, freeze ten acquisition occurrences and six report candidates. Delivery retries are not new occurrences.

| Occurrences | Report/version mapping | Study mapping and decision under protocol v1 |
| --- | --- | --- |
| O01, O02, O03 | A-preprint, repeated A-preprint retrieval, A-published; explicitly verified as versions of report A, with published version selected for screening | Report A describes study SA; included. |
| O04, O07 | Report B and an independently submitted exact duplicate download | Report B describes study SB; included. |
| O05 | Distinct companion report C, not a duplicate of B | C also describes SB; included as another report, not another independent study. |
| O06, O10 | Qualifying report D and repeated retrieval of D | D describes study SD; full-text excluded under v1's narrower task criterion. |
| O08 | Report E with no available full text | Passes title/abstract; report sought but not retrieved; study linkage unknown. |
| O09 | Report F | Excluded at title/abstract; no full-text retrieval required. |

Expected v1 counts: **10 identified occurrences = 4 duplicate removals + 6 retained screening candidates; 6 screened = 1 title/abstract exclusion + 5 reports sought; 5 sought = 1 not retrieved + 4 full-text assessed; 4 assessed = 1 full-text exclusion + 3 included reports; 3 included reports link to 2 distinct studies (SA, SB).** No other pre-screen removals or pending decisions exist in this baseline fixture.

Protocol v2 broadens the task criterion, explicitly reopens D and includes it after review. All upstream sets are unchanged; full-text exclusions become 0, included reports become 4 and included studies become 3. The v1 snapshot keeps its original counts. A separate reversible merge/split test creates conflicting candidate decisions and must enter adjudication rather than silently changing inclusion. Permission-loss and unavailable-media tests run as separate scenarios and do not silently rewrite what was retrieved at an earlier review checkpoint.

### 17.2 Required journeys

**J1 — Guided first value:** sign in → formulate question → add/read source → capture exact finding → link claim → write manual paragraph → reload → inspect citation → export. AI disabled throughout.

**J2 — Spatial sensemaking:** pin two apparently conflicting findings → freely arrange/group/media-link them → inspect setup → record a qualified reconciliation → see the same change in Evidence and Write → undo layout without undoing evidence → export board with reference appendix.

**J3 — Rigorous review:** freeze protocol → retrieve/deduplicate candidates → independent decisions → adjudicate → extract cited cells → reconcile flow counts → amend criteria → inspect affected records and synthesis.

**J4 — Local experiment:** pair selected directory → approve exact synthetic notebook/input environment → run locally → inspect manifest → publish selected aggregate/figure → promote a reviewed finding → insert figure and qualified result into manuscript → follow lineage back to notebook/input.

**J5 — Native ChatGPT:** connect authorized remote MCP → fetch current context → inspect evidence → submit externally attributed paragraph proposal → review in authenticated platform → apply once → inspect updated manuscript from a fresh MCP call. No platform model call or local execution implied.

**J6 — Failure and revocation:** lose network during save/upload → retry safely → edit same record from two tabs → preserve losing edits → revoke source/project/device access → confirm reads, exports, proposals and uploads honor revocation and explain any already-issued capability window.

### 17.3 Observable acceptance matrix

All checks below start **pending**. Mapping to a package does not mean it passed.

| ID | Observable check | Main packages |
| --- | --- | --- |
| C01 | Historical release evidence and open A25/live-AI/older observations remain explicitly separate from new acceptance. | P00/P12 |
| C02 | J1 completes manually; navigation, folding, layout, saving and deterministic export make zero provider calls. | P03–P05 |
| C03 | First-value usability target is tested with an unfamiliar user and recorded task/time/errors, not inferred from author familiarity. | P01/P03 |
| C04 | Same claim/finding identity appears in all views; board duplication creates no extra evidence. | P02/P09 |
| C05 | Forged quote, source version, cross-project reference and invalid endpoint relation are rejected server-side. | P02/P04 |
| C06 | Source change, archive, interpretation change and relation change invalidate the correct dependent reviews; layout change does not. | P02/P05/P09 |
| C07 | API/MCP/history/search/export/cache all enforce owner/member/viewer/private-note rules and current revocation. | P02/P06/P12 |
| C08 | Same-record concurrent edits cannot overwrite silently; disjoint edits can succeed; cross-record actions roll back atomically. | P02/P03 |
| C09 | Autosave acknowledgment, failed save, offline state, reload conflict and recovery preserve authored text without implicit sensitive localStorage. | P03/P05 |
| C10 | V1 conversion preserves IDs/text/quotes/origins/pins, aborts on changed revision and leaves a single authoritative write path. | P02 |
| C11 | Native Textfold fidelity, two-instance isolation, 20-remount cleanup, theme and keyboard regressions remain passing. | P03/P05/P09 |
| C12 | Arbitrary canvas placement, groups, connectors, mixed media, undo, templates and drag alternatives work—not only a generated hierarchy. | P09 |
| C13 | Media preview cannot execute untrusted content or expose restricted bytes; changed/unavailable remote video remains an unverified locator. Link-only references cannot become verified evidence, and snapshot anchors state exactly what was verified. | P02/P09/P12 |
| C14 | Identifier/import/dedup tests distinguish exact duplicates, aliases and revised studies; readiness/coverage and failures are visible. | P04 |
| C15 | Extraction cells retain types, units, missingness, reviewer and exact provenance; computed values identify their inputs/analysis. | P04/P08/P10 |
| C16 | Independent review hides pending peer decisions; AI suggestions cannot submit final human decisions; conflicts require named adjudication. | P10 |
| C17 | Versioned occurrence/report/candidate/study mappings reproduce section 17.1's exact counts, including repeated retrievals, preprint/publication versions, companion reports, reversible merges and protocol amendments; synthesis cannot count linked reports as independent studies. | P01/P02/P04/P10 |
| C18 | Rich editor and exports preserve citations, math, figures, gaps, source-quote semantics and AI origin through tested round trips. | P05/P12 |
| C19 | Every cited run figure links to a manifest, analysis/query version, source dataset and executed notebook snapshot. | P08/P05 |
| C20 | Pairing grants no arbitrary path/shell/kernel access; credentials remain local; wrong-project and revoked-device publication fail. | P07 |
| C21 | Changed notebook/input/environment invalidates local approval; failed/dirty/interactive runs are not labeled clean reproducible runs. | P08 |
| C22 | File replacement/symlink/size attacks and interrupted/repeated uploads cannot publish unapproved bytes or duplicate a run. | P07/P08 |
| C23 | Arrow/JSON/Parquet benchmarks report correctness, allocations, transfer, memory and latency for all declared fixture shapes. | P08 |
| C24 | Browser analytics stay within caps, support cancellation and do not block ordinary writing/reading; exact numeric semantics survive. | P08 |
| C25 | MCP discovery/PKCE/resource audience/scopes/revocation work through the canonical origin with the pinned tested protocol. | P06 |
| C26 | Tool annotations match side effects; forged confirmations, model-supplied actor IDs and stale approvals cannot apply changes. | P06 |
| C27 | External-AI origin cannot impersonate native assistant requests or be erased by edit/copy/export. | P02/P05/P06 |
| C28 | Actual ChatGPT-account J5 is recorded separately from mocks/protocol tests; unavailable account access remains pending. | P06/P12 |
| C29 | Before any new metered operation is enabled, its P02 admission core enforces reservations, limits, retry bounds and uncertain outcomes under replay/status/concurrency tests; unsupported paid paths remain unavailable while deterministic paths work. | P02/P04/P06/P11; every later paid path |
| C30 | Prompt injection fixtures cannot gain new tools, upload local files, alter accepted evidence or cause paid execution. | P06–P11 |
| C31 | Publication export runs no notebooks/remote filters/shell commands by default; restricted content and unresolved integrity states are handled visibly. | P12 |
| C32 | Desktop/mobile/keyboard/screen-reader/reduced-motion/zoom and role-specific UI journeys run in a real browser; source close restores focus. | P03–P12 |
| C33 | Performance targets and warm/cold/resource profiles are measured; any misses have explicit dispositions. | P08/P09/P12 |
| C34 | Backup restore recovers a selected project and its referenced artifacts; RPO/RTO claims match executed evidence. | P12 |
| C35 | Full existing server/jobs/worker/research/client/native/browser/required-Postgres regressions run as applicable, with skips disclosed. | P00/P12 |
| C36 | Fresh deployment, authenticated operator UI and explicitly budgeted live-AI checks are separately evidenced; no merge/deploy implied by planning. | P12 |

### 17.4 Verification layers and completion language

1. Schema/unit tests: deterministic graph, provenance, parsing, numeric and state-machine rules.
2. Real disposable PostgreSQL/HTTP tests: transactions, locks, roles, migration and failure injection; required lane cannot silently skip.
3. Storage/queue integration: capability constraints, checksums, expiry, replay and reconciliation using isolated fixtures.
4. Real dev-server/browser tests: actual feature use, not just screenshots or TypeScript checks; fake providers for no-spend coverage.
5. Local companion tests: supported OS and real local synthetic notebook execution under its claimed isolation.
6. Operator ChatGPT/account acceptance: actual workspace/tool availability and app-specific flows.
7. Explicitly authorized live quality/cost checks: small fixed cases, human inspection and spend receipts.
8. Independent review: code, contracts, executed evidence and security boundaries, with unresolved findings tracked.
9. Authorized production rollout and fresh acceptance: separate from all local proof.

Use precise statuses: designed, implemented, locally verified, account-verified, deployed, production-accepted. Never use “complete” for an entire milestone while a required journey is only designed or blocked.

## 18. Decision register, tradeoffs and reopening conditions

| Decision | Why this is the default | What would change it |
| --- | --- | --- |
| One canonical research model across board/review/lab/manuscript | Prevents duplicated evidence and broken handoffs. | Only a proven distinct ownership/lifecycle need; not a convenience shortcut in a UI component. |
| Freeform canvas and rigorous review are both target features | Explicit user requirement to combine both paradigms. | User changes scope; not an implementer silently deferring either forever. |
| Preserve the current platform/infrastructure | Minimizes migration risk, operating burden and unnecessary hops. | Measured unsupported requirements or total-cost/security evidence for a bounded replacement. |
| Normalize identities/revisions, keep typed JSON where useful | Whole-document v1 cannot support review scale and low-conflict autosave. | Spike proves a simpler model meets all concurrency/scale requirements without compromising integrity. |
| Cloud research state, local execution and explicit artifact publication | Coherent UI without handing a cloud assistant laptop execution authority. | Explicit user requirement for managed compute with a separately reviewed trust/budget design. |
| No automatic two-way filesystem sync | Protects existing research and avoids multiple canonical owners. | Proven ownership/conflict semantics and an explicit request for continuous sync. |
| Arrow/Parquet only for analytical data | Real benefits where data is columnar; avoids complexity on ordinary APIs. | Representative benchmarks show no advantage or an alternative is materially simpler/faster. |
| HTTP first, no Flight service initially | Existing browser/storage path suffices and has fewer components. | Native sustained streaming workloads measurably bottleneck on the current transport. |
| React Flow and Tiptap as foundations | Established interaction/document primitives without rebuilding engines. | Compatibility, license, accessibility or measured performance spike fails required behavior. |
| No real-time CRDT collaboration initially | Revisioned editing/comments address personal-first needs. | Repeated real concurrent editing conflicts justify coediting, with a separate permission/revocation/history design. |
| Existing FTS first; hybrid retrieval measured later | Current workload has known lexical capabilities and no demonstrated vector-service need. | Human-reviewed benchmark shows materially better recall/utility at acceptable cost with hybrid retrieval. |
| Protocol/screening records before AI automation | Makes decisions auditable and avoids overtrusting suggestions. | No change absent a stronger, explicitly validated and approved methodology. |
| MCP reads/proposals before application tools | Controls the impact of model mistakes and injection. | Server-recorded approval, access and conflict checks pass; execution still remains locally consented. |
| No mandatory journal impact score | Venue metrics are not scientific validity and may mislead in AI research. | Licensed metrics are useful as optional contextual metadata, with provenance and limitations. |
| Local publication first | Lower cloud execution risk and reproducibility through pinned tools. | User needs one-click cloud publication and an isolated renderer can meet security/cost targets. |

## 19. Material unknowns and how to retire them

| Unknown | Bounded resolution | Consequence if unresolved |
| --- | --- | --- |
| Current operator acceptance and deployed behavior | Execute the existing authenticated Case/Evidence/Draft/citation/export checks when a session is available. | Keep A25 open; do not claim production user acceptance. |
| ChatGPT plan, permissions and protocol/tool/UI support | Operator inspects actual workspace and runs deterministic connector acceptance. | Keep browser/local workflow usable; mark account integration pending. |
| FastMCP broker token/resource semantics | Inspect installed implementation and run discovery/audience/consent tests. | Do not expose new write capabilities until resolved. |
| Actual compute sandbox network controls and retry spending | Inspect configured SDK/platform behavior and use safe isolated tests with fake providers. | Do not broaden generated-code execution or assert network isolation. |
| Research data size, local OS/GPU and device credential support | Run the declared fixture/memory/packaging matrix and inventory selected local environment with consent. | Ship the tested platform subset only; no unsupported cross-platform claim. |
| Region alignment, idle cost and database contention | Measure timings, deployment configuration and authorized billing observations. | Retain current infrastructure; no speculative migration. |
| Canvas/editor accessibility, export and license fit | Narrow prototype on real fixture, keyboard/browser tests and locked-package license review. | Replace that component choice before broad implementation, not the product requirement. |
| Bibliographic/source-metric API access and licensing | Read current provider terms and test authorized small requests. | Use standards-based import and omit unavailable metrics honestly. |
| Dataset/model/publication rights | Record licenses and restricted/public derivative policy during artifact approval. | Keep restricted originals private; block unapproved dissemination. |
| Scientific utility of assistance | Human-reviewed corpus-specific evaluation and explicit small live budget. | Manual workflow remains the reliable baseline; no autonomous promotion. |
| Backup/artifact recoverability | Isolated timed restore with cross-object consistency checks. | No recovery objective is claimed achieved. |

Primary failure modes are scope sprawl, two sources of truth, hiding uncertainty behind polished UI, overclaiming zero-copy, allowing prompt-based permissions, and adding infrastructure faster than evidence of need. The package order and acceptance matrix are designed to expose those failures early.

## 20. Exact next action and handoff

This is a strategy/execution blueprint only. The next implementation action, **if explicitly requested**, is P00 followed by P01/P02: re-establish the real baseline, preserve the existing release gates, prove the shared product loop, then build versioned identity and safe persistence before expanding views.

A subsequent implementer should read this document, the root repository guidance, the current work pointer and the existing investigation verification record. Compare the actual working tree and schema with the recorded baseline; preserve intervening work. Use the package dependencies and C01–C36 as the execution checklist. Record acceptance evidence rather than relying on this document's intent.

Do not start by installing a canvas, replacing authentication, moving cloud providers, launching autonomous research, rewriting the entire UI, or executing a notebook. First establish the contracts and protections that make those features coherent.

Planning-pass verification is documentation/source research and consistency review, not application verification. No new feature, migration, live account flow or performance target is claimed implemented or passed by this blueprint. The existing production pointer and open operator acceptance remain intact; a separate strategy reference identifies this proposed revamp.

### 20.1 Planning review and verification

The first independent strategy review returned **rework** for three bounded issues: spending enforcement was scheduled after early metered features; review identity/count units were underspecified; and link-only video locators could be confused with verified evidence. Corrections move the admission core/C29 gate to P02 and every paid-path enablement, define occurrence/report/candidate/study mappings with exact count fixtures, and prohibit verified anchors from link-only media. Independent rereview returned **accept, no remaining material contract findings** after reading the full amended strategy and checking the preserved release boundaries. This was a read-only strategy review, not implementation acceptance; it ran no application tests or live checks and did not repeat the author's mechanical validations.

Mechanical checks in this planning pass verify local link targets/line-anchor bounds, unique P00–P12 and C01–C36 entries, valid work-pointer JSON, no changes to pre-existing work-pointer values, and documentation-only modifications. These are document checks, not executed application acceptance or a live security audit.

## 21. Sources and research limitations

Primary technical documentation consulted during planning is listed below. It informs design, not claims that the current installation implements every documented feature. Pin and retest actual package/protocol versions at implementation time. Some vendor naming and entitlement documentation is time-dependent; actual account capability remains an operator check. The direct Tiptap persistence-page fetch failed, so persistence decisions are not presented as verified from that page.

### Existing application and reference paradigms

- The source seams and local records in sections 0.1 and 14.2 are the current-code baseline.
- Storyflow/Paperguide feature comparisons derive from the screenshots inspected in the preceding investigation. Marketing claims such as corpus size, style counts and certifications were not independently audited; the plan does not repeat them as platform guarantees.
- The tension-resolution essay is linked in section 2.1 and was already referenced in the repository's strategy.

### Analytical data and local execution

- [Arrow C Data interface](https://arrow.apache.org/docs/format/CDataInterface.html).
- [Arrow IPC and memory mapping](https://arrow.apache.org/docs/python/ipc.html).
- [Arrow/pandas conversion considerations](https://arrow.apache.org/docs/python/pandas.html).
- [Arrow Flight protocol](https://arrow.apache.org/docs/format/Flight.html).
- [DuckDB Parquet support](https://duckdb.org/docs/2.0/data/parquet/overview.html).
- [DuckDB HTTP reads](https://duckdb.org/docs/2.0/core_extensions/httpfs/https.html).
- [DuckDB-Wasm overview and limitations](https://duckdb.org/docs/2.0/clients/wasm/overview.html).
- [DuckDB security boundaries](https://duckdb.org/docs/2.0/operations_manual/securing_duckdb/overview.html).
- [MDN transferable objects](https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API/Transferable_objects).
- [MDN SharedArrayBuffer](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/SharedArrayBuffer).
- [Jupyter Server security](https://jupyter-server.readthedocs.io/en/latest/operators/security.html).
- [Jupyter notebook format](https://nbformat.readthedocs.io/en/latest/format_description.html).
- [JupyterLab collaboration](https://jupyterlab-realtime-collaboration.readthedocs.io/en/latest/).
- [Quarto JupyterLab workflow](https://quarto.org/docs/tools/jupyter-lab.html).
- [Quarto execution/cache/freeze](https://quarto.org/docs/projects/code-execution.html).
- [Quarto licenses](https://quarto.org/license.html).
- [Pandoc security](https://pandoc.org/MANUAL.html#security).
- [Object-storage metadata](https://docs.cloud.google.com/storage/docs/metadata) and [data validation](https://docs.cloud.google.com/storage/docs/data-validation).
- [Cloud Run container contract](https://docs.cloud.google.com/run/docs/container-contract).

### ChatGPT, MCP and authorization

- [OpenAI custom MCP servers](https://developers.openai.com/api/docs/guides/custom-mcp-server).
- [OpenAI research-compatible MCP servers](https://developers.openai.com/api/docs/mcp).
- [OpenAI authentication requirements](https://developers.openai.com/plugins/build/auth).
- [OpenAI MCP UI integration](https://developers.openai.com/plugins/build/chatgpt-ui).
- [OpenAI UI/metadata reference](https://developers.openai.com/plugins/reference).
- [OpenAI security and privacy guidance](https://developers.openai.com/plugins/guides/security-privacy).
- [MCP Streamable HTTP, 2026-07-28 specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http).
- [MCP authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization).
- [MCP authorization security considerations](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations).
- [MCP security best practices](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices).
- [OpenAI account/workspace help](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt): research used indexed official excerpts where direct retrieval returned 403; this is not account-side verification.

### UI foundations

- [React Flow accessibility](https://reactflow.dev/learn/advanced-use/accessibility).
- [React Flow performance](https://reactflow.dev/learn/advanced-use/performance).
- [Tiptap custom node views and serialization distinction](https://tiptap.dev/docs/editor/extensions/custom-extensions/node-views).
