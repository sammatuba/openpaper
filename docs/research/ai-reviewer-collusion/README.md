# Evidence of collusion among AI reviewers

Prepared: 2026-11-04. Status: staged research packet, pending owner review.
OpenPaper project: `a5cf0e26-f8dd-424c-a452-dbcf6ebba946`.

The working question is whether an auditor can distinguish coordinated harmful
endorsements from shared-source error, conformity, unilateral persuasion, parallel
conduct, and plans that do not change actions.

This packet supplies a seven-paper comparison, fourteen candidate evidence
records, and a small offline diagnostic specification. It does not update the
canonical `ai-safety` bibliography, landscape claims, hypothesis registry, or
historical results. The TARA portfolio remains unselected. Existing hypothesis
IDs below are references to that repository, not new definitions.

## Read in this order

1. Read the comparison below and [alternative explanations](DISAGREEMENTS.md).
2. Inspect the short excerpts and precise locations in [evidence.json](evidence.json).
3. Use [sources.json](sources.json) to recover the inspected version and hashes.
4. Read [the offline experiment specification](EXPERIMENT.md).
5. Run [verify_packet.py](verify_packet.py) for structure and local quote checks.

## Prior-work matrix

All rows describe targeted reading of primary full text. They are not complete
reproductions or systematic literature coverage. Source links resolve to the
exact inspected full text. The bibliography IDs already exist in `ai-safety`.

| Reference / version | Setup and manipulation | Comparison and reported outcome | Limit or boundary | Implication for this question |
|---|---|---|---|---|
| [R11, v5](https://arxiv.org/html/2312.06942v5#S3.SS4) | A red team supplies an untrusted programming policy and monitor. Attacks couple backdoors to monitor omissions. | Trusted and untrusted monitoring, evaluation inputs, redaction, deferral, and editing are compared for safety/usefulness. | The deliberately selected programming setting does not establish deployment-wide safety. | Test shared input signals as possible mechanisms; channel availability alone is insufficient. See records R11-01/02. |
| [R12, proceedings](https://proceedings.neurips.cc/paper_files/paper/2024/file/861f7dad098aec1c3560fb7add468d41-Paper-Conference.pdf) | Sender, receiver, and oversight roles frame concealed communication. Capability evaluations examine encoding, decoding, and monitoring. | The authors combine a formal threat model with empirical steganographic tests and countermeasure analysis. | Paraphrasing can retain semantic communication capacity and impair useful tasks. | A visible-message audit has an explicit observability boundary. Concealed channels require separate evidence. See R12-01/02. |
| [R14, ACL proceedings](https://aclanthology.org/2026.acl-long.270.pdf) | Writer, Editor, and Director roles coordinate truthful public fragments in simulated rumor settings. | CoPHEME comparisons examine attack success, truthfulness, and downstream belief effects. | Simulated text feeds omit important live-platform dynamics. | Fragment truth alone cannot certify the inference drawn from the collection. See R14-01/02. |
| [R15, PMLR proceedings](https://raw.githubusercontent.com/mlresearch/v306/main/assets/okawa26a/okawa26a.pdf) | A social-dynamics model and controlled debates vary conformity, sampling noise, and agent mixture. | The authors report collective bias and a smoothing effect from heterogeneity. | Simplified memory, interaction, and output representations constrain transfer. | Include non-collusive debate failures before interpreting agreement as coordination. See R15-01/02. |
| [R17, v5](https://arxiv.org/html/2604.01151v5#S5) | NARCBench aggregates agent activation signals across constructed scenarios and transfer tasks. | It compares probe architectures and aggregation techniques; retained collusive runs must pass behavioral filters. | Prompt confounds and the interpretation of activation signals remain concerns. | Keep instructions, observed coordination, actions, and audit labels separate. See R17-01/02. |
| [S1, v2](https://arxiv.org/html/2602.15198v2#S5.SS4) | Colosseum uses cooperative constraint tasks, coalition objectives, and a private-channel intervention. | Regret-based action measures are compared with communication judgments; plans can diverge from actions. | Explicit objectives and decomposable rewards simplify auditing. | Measure channel effects and outside costs separately from textual plans. See S1-01/02. |
| [T17, v4](https://arxiv.org/html/2505.11556v4#S6.SS3) | Hidden Profile tasks distribute decision-relevant facts across agents. | Full-information and disclosure interventions isolate reasoning and information-sharing bottlenecks. | Controlled information tasks do not establish reliability in operational settings. | Add a matched information-complete control before attributing group failure to strategy. See T17-01/02. |

## Synthesis

[INTERPRETATION] The papers support separating three measurements: agreement,
evidence of a coordination mechanism, and resulting outside cost. They do not
license an auditor to infer all three from similar answers.

[INTERPRETATION] The useful next contrast is narrow: hold the visible endorsements
fixed while changing provenance, exposure order, or a documented mechanism.
Measure how often an auditor accuses innocent comparison cases. Compare that
with its ability to recognize an executed coordinated plan.

[HYPOTHESIS] This follows the existing `H-CORE-2` and `H-SPRINT-3` questions.
It does not establish a new contribution. The local registry records that
`H-SPRINT-3` was not supported in its confirmatory analysis. A new diagnostic
must preserve that result and explain what additional distinction it tests.

## Version and evidence boundaries

The registered R17 dossier cites v4, revised 2026-10-12. The primary archive now
lists v5, dated 2026-10-15. This packet inspects and pins v5. It does not silently
update the older dossier or claim that v4 and v5 are identical.

Every ledger entry remains `candidate`. Each contains an author claim, a short
verbatim excerpt, its exact normalized-text location, and our separate
interpretation. Short excerpts locate the inspected passage; the full passage
and its methods must be read before promoting a claim. Excerpt existence alone
does not prove that our interpretation follows.

HTML character locations refer to normalized extracted text, not PDF pages.
PDF page numbers count from the first PDF page. They may differ from printed
proceedings page labels. Raw inputs are untrusted and were downloaded only into
`/tmp/openpaper-collusion-r1-sources`. They are not committed here. Hashes detect
changed inputs; they cannot recover missing bytes. Preserve selected source
snapshots in the canonical repository's ignored sources area when promoting.

The selected sources were available on 2026-11-04. No source code, dataset,
published result, or model behavior was reproduced. No paid model call, bulk
discovery, OpenPaper import, or change to the existing library was performed.

## Verification

From the repository root:

```sh
rtk proxy python3 docs/research/ai-reviewer-collusion/verify_packet.py
rtk proxy server/.venv/bin/python docs/research/ai-reviewer-collusion/verify_packet.py --source-dir /tmp/openpaper-collusion-r1-sources
rtk proxy python3 scripts/research/collusion_cases.py
rtk proxy python3 -m unittest discover -s scripts/research -p test_collusion_cases.py -v
```

The first command checks schema, references, locations, candidate status, hashes,
and the per-source quote budget. The second additionally recomputes the primary
input and extraction hashes and verifies every excerpt at its recorded offset.
It requires `pypdf` for the three PDF sources and makes no network calls.

The fixture harness contains sixteen synthetic trajectories: eight mechanisms
in each of two topic families. Six tests check harm rules, restricted views,
missing evidence, plan/action separation, and family separation. Its results
describe fixture consistency. The structured baseline receives authored
mechanism records; it does not independently interpret natural-language plans.
The second family is a held-out example, not a blinded confirmatory test.

Canonical promotion should retain bibliography IDs, verify versions and claims,
record the selected excerpts and snapshots, run the owning repository checks,
and preserve existing hypothesis/result statuses. That promotion is a separate
step from producing this packet.
