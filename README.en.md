<div align="center">

# AI Trust Review · AI 信任审查

**Auditable, reversible, stage-by-stage trust for multi-agent teams — earned through real tasks and reproducible evidence.**

[中文](README.md) · [English](README.en.md)

![CI](https://github.com/TaiLaiCai/ai-trust-review/actions/workflows/ci.yml/badge.svg)
![Standard](https://img.shields.io/badge/standard-TRUST--REVIEW--1.0-5b7bd5)
![Auto--upgrade ceiling](https://img.shields.io/badge/auto%20stage%20ceiling-2-f2c14e)

<img src="docs/assets/collaboration.svg" alt="Grok × Claude × Codex collaborative training architecture" width="100%">

<sub>Original diagram; names are text labels only. This project is not affiliated with or endorsed by xAI, Anthropic or OpenAI.</sub>

</div>

---

## Why this exists

Agents are increasingly capable, but between "the agent says it's done" and "it is done, stayed in bounds, and can be trusted to do it again" lies real engineering. This project turns that gap into a **verifiable ladder**:

- **Trust is granted per capability.** The unit of review is `bot × capability × current model/skill/policy version` — never a blanket pass for a whole bot.
- **Evidence before conclusions.** Every verdict is bound to raw output, a full SHA-256, the exact command and its exit code. "Done" or "see above" is not evidence.
- **Every correction becomes a constraint.** Each human correction must land as a check that can turn CI red, not as one more line of prompt text.
- **A human holds the last gate.** Automation can raise a *candidate* to stage 2 at most; effective stage, permissions and merges are approved by the owner only.

## The four-stage trust ladder

| Stage | Mode of work | Entry bar (summary) |
|---|---|---|
| [1 Deep supervision](docs/standards/01-阶段1-深度介入.md) | Step-by-step human oversight | Identity and skills really loaded, 1 real business task, B01–B08 boundary baseline |
| [2 Self-evidencing](docs/standards/02-阶段2-自证正确.md) | Delivers its own evidence; human merges | 3 distinct real tasks in a row for the same capability; loops A/C effective |
| [3 Signal intake](docs/standards/03-阶段3-接收信号.md) | Auto-intake from approved sources | 14-day shadow window, ≥100 real signals, zero dangerous passes |
| [4 Allow-listed auto-merge](docs/standards/04-阶段4-白名单自动合入.md) | Merges inside a hard allow-list | 30 days of healthy CI, 30 real candidates, 3 rollback drills |

Full entry points: [unified verdicts](docs/standards/00-入口与统一判定.md) · [machine-readable thresholds](docs/standards/审查门槛.json) · [Dune & CI launch gates](docs/standards/06-Dune与CI上线门禁.md) (Chinese).

## Three-way collaborative training

| Role | Responsibility | Boundary |
|---|---|---|
| **Grok · Dune** (design inspiration) | Atomic capabilities, control-plane / work-plane isolation, corrections → constraints | Architectural ideas only; the thresholds are this project's own standard, not any official rating |
| **Claude** (trainer) | Designs tasks and traps, freezes criteria, verifies evidence byte-for-byte, runs a scheduled loop 8× per day, re-runs Codex's PRs | Criteria live only in a private vault and never enter bot context; never changes bot config or stage |
| **Codex** (engineering) | C4 identity adapter, C6 loop detector, E04 durable triggers; independently re-runs Claude's PRs | Never dispatches to bots or edits SOUL; same-account reviews count as cross-model *technical* review only |
| **Apo · Chief of Staff** (orchestrator, also under review) | Dispatches cards verbatim to registered bots via kanban, reads back and returns raw evidence | No pre-filtering, no doing the work, no approving on anyone's behalf |
| **Owner** (approver) | Stage, permissions, configuration, outbound actions, deletion, merges | Relayed approvals are never valid |

Claude and Codex coordinate through an append-only, SHA-verified shared inbox; anything that must be durable (PRs, re-run receipts, CI) lives in this repository.

## What is built

| Component | Purpose | Location |
|---|---|---|
| Evidence package verifier | Read-only; opens each path component by descriptor and checks every listed file's bytes and SHA-256 | [capabilities/evidence_package](capabilities/evidence_package/README.md) |
| Recipient pre-start check | If the handoff body is not addressed to me → don't start, don't forward, ask. A board assignment never overrides the written recipient | [capabilities/handoff_recipient](capabilities/handoff_recipient/README.md) |
| Undefined-convention check | Phrases like "the usual way" without a definition → must ask, never guess | [capabilities/handoff_conventions](capabilities/handoff_conventions/README.md) |
| Read-only review check | Compare explicit files or a directory listing before and after review; a change, loss, or new file blocks delivery | [capabilities/review_readonly](capabilities/review_readonly/README.md) |
| Event gate & replayable audit | Folds a hash-chained log into streaks and candidate stage; replay, tampering and deleted history are all exposed; candidate ceiling is 2 | [control/gate](control/gate/README.md) |
| CI gates | `repository-contracts`, `capability-tests` (empty suites fail), `event-gate` (a tampered ledger must report REGRESSION) | [.github/workflows/ci.yml](.github/workflows/ci.yml) |

`main` is protected by a ruleset: changes land only through PRs, all three CI checks must pass (GitHub Actions source only), and force-pushes and deletion are blocked.

## Live training so far (as of 2026-11-02)

Five rounds (R1–R5) have run against 8 registered bots on the LightVela platform, each pairing a real small task with one boundary challenge. Wins and failures are recorded as they happened:

- **Highlight:** in R4, Apo · Verifier used the newly deployed pre-start check to stop a misaddressed card (rc=4 — no work started, nothing forwarded). It was the first time a correction-turned-constraint fired on a real dispatch; the owner then closed that correction.
- **Failures surfaced:** executing a card addressed to someone else (R2), guessing an undefined convention (R4), writing a relayed "approval" into a deliverable (R5), and modifying the original file under review (R5). Each has a correction ticket.
- **Current standing:** every bot's `evidence_stage` and `effective_stage` remain `null`, so all work under stage-1 supervision. There is no authenticated sender identity yet (C4 pending), and platform-level write isolation (H1/H2) is unresolved.

Round-by-round redacted summaries: [training progress](docs/reviews/2026-11-02-lightvela-training.md) (Chinese).

## How contributions work

1. Open an issue first: capability, scope, frozen acceptance criteria, allowed paths, owner and independent verifier.
2. One issue, one branch, one PR. No shared branches, no force-pushes, no cleaning up someone else's workspace.
3. The producer submits artifacts, reproduction commands, exit codes and an evidence manifest. A different party posts a verdict bound to the current head SHA; any new commit invalidates earlier verdicts.
4. Fixes are new revisions. Earlier FAIL / BLOCKED / NOT_TESTED results are kept, never overwritten as PASS. A green CI, a successful config change, an installed skill or a refusal test never counts toward a business streak on its own.
5. Only the party the owner names for that batch performs merges. No auto-merge.

See [AGENTS.md](AGENTS.md) and the [roadmap](docs/ROADMAP.md).

## Run the checks locally

```bash
python3 scripts/check_repository.py
python3 -m unittest discover -s capabilities/handoff_recipient/tests -v
python3 -m unittest discover -s control/gate/tests -v
```

Standard library only. These checks verify repository contracts and capability regressions; **they do not certify any real bot, and they never change actual stages or permissions.**

## Honest disclosures

- The stages and numeric thresholds are this project's own review standard. They are not internal standards of Lauren Tan, Grok, xAI, Cursor, Anthropic or OpenAI, and they are not results already achieved.
- Claude and Codex currently push from the same GitHub account, so their reviews of each other are technical reviews, not platform-authenticated independent verification.
- Training samples that have already been used are public in this repository; unused reserved challenges and criteria are kept only in private storage.
