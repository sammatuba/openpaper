# What would distinguish the competing explanations?

Prepared: 2026-11-04. Status: interpretation and proposed controls.

Agreement means matching endorsements or actions. Collusion requires a coalition,
a coordination mechanism, and an outside cost. These are the canonical glossary
requirements. The rows below are analytical comparisons, not newly observed
model findings.

| Observation | Competing explanation | Evidence needed | Control that could change the conclusion |
|---|---|---|---|
| Reviewers repeat one incorrect endorsement. | Shared-source error. | Origins of evidence items and independent pre-discussion judgments. | Replace derivatives with independently generated evidence while preserving presentation. |
| A reviewer changes after seeing another endorsement. | Conformity or informative learning. | Exposure order, private evidence, initial output, and the content actually revealed. | Mask earlier endorsements; separately reveal their underlying evidence. |
| Several agents favor approval. | Parallel conduct under similar incentives. | A mechanism connecting their choices, beyond the payoff structure alone. | Remove a documented channel or shared signal while matching incentives and tasks. |
| One proposer presents only favorable true evidence. | Unilateral selective disclosure. | Which agents controlled disclosure and whether another joined a coordinated plan. | Keep the evidence selection but remove the proposed coalition's involvement. |
| Public true fragments induce a false conclusion. | Coordinated composition or ordinary incomplete reporting. | Publisher roles, ordering control, shared objective, and effects on the conclusion. | Compare coordinated ordering with matched independent posting. R14 motivates this distinction. |
| Agents discuss a harmful plan. | Attempted coordination without execution. | Action traces linked to the plan and a separately defined outside cost. | Keep the plan text while changing only whether its actions are executed. S1 motivates this distinction. |
| Actions harm the decider's objective. | Reasoning failure or insufficient information. | Decision sufficiency of the available facts and a mechanism linking agents' actions. | Provide complete information from the outset, as motivated by T17. |
| An activation probe flags the group. | Role wording or another correlated feature. | Matched prompts, held-out task families, behavior checks, and causal intervention where possible. | Test role-preserving prompt changes and innocent mechanisms. R17 explicitly retains this uncertainty. |
| A text audit finds no mechanism. | Incomplete logging or concealed communication. | A documented observation boundary and independent evidence of relevant channels. | Add available channel records. R12 motivates the boundary; absence of visible evidence does not settle it. |
| Policy and monitor fail on the same inputs. | A shared input signal or unrelated correlated error. | Evidence that the agents use the signal to coordinate, plus a matched signal intervention. | Change the signal while keeping task difficulty fixed. R11 motivates this comparison. |

## Claims that should remain separate

1. A constructed condition instructed agents to coordinate.
2. Their messages expressed a coordinated plan.
3. Their actions implemented that plan.
4. The actions imposed an outside cost.
5. An auditor identified the mechanism from its permitted observations.

Success at one step does not establish the others. A refusal, failed execution,
or zero outside cost remains visible in the record. A missing mechanism record
produces uncertainty rather than a finding of innocence.

## What would weaken the proposed value of richer evidence?

[HYPOTHESIS] Richer provenance may help an auditor reject some innocent cases.
That hypothesis weakens if action-and-message context already provides the same
distinction. It also weakens if the added metadata leaks the condition label.

The proposed baseline therefore masks regime names, payoffs, ground truth, and
author-created target labels from auditor inputs. It supplies only the selected
information slice. Human-authored fixture labels are used for scoring afterward.
The full fixture scorer is a measurement check, not an auditor competing with
a language model.

## Links to inspected evidence

R11: [untrusted monitoring](https://arxiv.org/html/2312.06942v5#S3.SS4).
R12: [steganographic threat model](https://proceedings.neurips.cc/paper_files/paper/2024/file/861f7dad098aec1c3560fb7add468d41-Paper-Conference.pdf).
R14: [public-fragment attack](https://aclanthology.org/2026.acl-long.270.pdf).
R15: [debate dynamics](https://raw.githubusercontent.com/mlresearch/v306/main/assets/okawa26a/okawa26a.pdf).
R17: [prompt-confound limitation](https://arxiv.org/html/2604.01151v5#A10.SS3).
S1: [controlled channel intervention](https://arxiv.org/html/2602.15198v2#S5.SS4).
T17: [disclosure intervention](https://arxiv.org/html/2505.11556v4#S6.SS3).
