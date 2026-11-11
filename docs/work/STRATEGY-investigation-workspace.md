# Native investigation workspace — proposed direction

The operator confirmed on 2026-11-11 that the deployed project workspace,
dossier/reader and ChatGPT connection work. They want native Textfold,
an investigation-case interface around David Africa's framework, a paper
drafter, and an intuitive explanation before the larger implementation.

Status: direction expanded into an executable intent/plan at the operator's
request on 2026-11-11. Implementation has not started. The current contracts are
[INTENT-investigation-workspace.md](INTENT-investigation-workspace.md),
[PLAN-investigation-workspace.md](PLAN-investigation-workspace.md) and
[ACCEPTANCE-investigation-workspace.md](ACCEPTANCE-investigation-workspace.md).

Primary reference: [David Africa, People Should Resolve Tensions In AI Safety
Research](https://www.lesswrong.com/posts/tn4WSyrqr7ozGLjRy/people-should-resolve-tensions-in-ai-safety-research).
The source argues for organizing around uncertainties, compiling contradictory
findings, comparing conditions, and writing a provisional reconciliation.
The interface and drafting model below are our proposed application of that idea.

Make a project an evolving investigation. Its entry point should show the
central question, current provisional answer, strongest unresolved tension,
and the next observation or experiment that could change the answer.
Keep the question open to competing explanations rather than presenting a
case as proof of its initial hypothesis.

Three connected views:

- Case: question, importance, candidate explanations, provisional argument,
  remaining uncertainty and discriminating experiment. A readable argument
  outline should work before a spatial graph is useful.
- Evidence: findings linked to exact passages/pages, paper identity and setup.
  Support/challenge/qualification attaches to a specific claim. Preserve the
  distinction between source wording, author interpretation and our inference.
  One paper may contribute multiple findings with different implications.
- Draft: a persistent manuscript assembled from chosen claims and findings,
  with section editing, citations back to the evidence, and explicit gaps or
  proposed experiments. AI edits are reviewable proposals. Source changes
  flag affected draft passages rather than silently rewriting them.

Textfold should be the reading interaction across those views: question/map,
claim, explanation, excerpt and source context can unfold in place. These are
proposed content depths, not a replacement specification for the upstream five
levels. Retain the upstream engine's actual interaction behavior, source
fidelity and attribution while investigating a host-native integration.
Today the pinned engine runs inside a sandboxed app frame and mainly reads the
saved brief; changing colors or moving that frame does not fulfill this request.

Example interaction: open an unresolved claim, unfold the supporting finding,
inspect the quoted passage and experimental conditions, compare a challenging
finding, record a candidate explanation, and add a qualified paragraph to the
draft with its evidence links intact. The draft may say the tension remains.

Material unknowns before implementation: feasibility of mounting the existing
upstream engine in the host DOM without global CSS/event collisions; persistent
claim/finding/anchor schema and source-version behavior; migration of existing
briefs without inventing evidence; draft storage/version/conflict handling;
citation export needs. The first end-to-end slice should prove one real
question → claim → exact evidence → qualified draft paragraph before expanding
the board. A freeform graph becomes worthwhile if actual cases need navigation
across many connected claims.

Separately reported defect: all paper thumbnails fail. The repair is bounded by
[INTENT-paper-thumbnails.md](INTENT-paper-thumbnails.md) and does not implement
the investigation proposal.
