# Vox Architecture Invariants

This document defines the non-negotiable invariants for Vox.
They are platform rules, not domain rules.

## 1) Intent Fidelity

- Vox must preserve the user's explicit goal.
- No layer may rewrite intent into a different task.
- If required inputs are missing, ask for them explicitly (`ask_user`) instead of guessing.

## 2) Single Execution Spine

All requests must follow exactly one spine:

`Intent -> Plan -> Build -> Execute -> Verify -> Deliver`

- No hidden bypasses from fallback paths to direct synthesis execution.
- Every successful delivery must pass verification.

## 3) Contract-Driven Runtime

All execution is governed by contracts:

- `PlanContract`: planner tool + structured input
- `ActionContract`: action type + params + on_error + save_as
- `SkillContract`: `RUN_SPEC` + `async run(...)`
- `OutcomeContract`: delivery + checks
- `ErrorContract`: stage + reason + retryability

Contracts must remain domain-agnostic.

## 4) Transparent Failure Semantics

- If planner is unavailable, return safe degraded chat/error.
- If synthesis fails, return synthesis failure.
- If execution fails, return execution failure.
- If validation fails, return validation failure.

Never return placeholder success or unrelated results.

## 5) Artifact Isolation

- Session state is isolated by `session_id`.
- Dynamically generated one-shot artifacts are request-scoped artifacts.
- Dynamic one-shot artifacts must not bias future planner decisions.

## 6) Evidence Before Claims

- Claims based on retrieval/tool output must include evidence in `render` and/or `ui`.
- No conclusion should be presented before corresponding evidence-bearing action has run.

## 7) Frontend Delivery Invariant

- Frontend renders structured outputs (`speak`, `render`, `ui`) only.
- Frontend does not infer business intent; it displays server-provided state and results.

## 8) Regression Policy

Every production bug must be converted into an invariant regression test.
Release is blocked when invariant tests fail.

## 9) Fixed Gate Set (Not Case Rules)

- Vox uses a fixed, small set of invariant gates.
- New user examples should be fed into the same gates, not converted into new domain-specific rules.
- If a new failure appears, first map it to an existing invariant.
- Only add a new invariant gate when the failure reveals a genuinely new platform failure mode.

Current invariant IDs:

- `INV-01`: response envelope sanity (`kind/speak/render`)
- `INV-02`: no placeholder pseudo-success
- `INV-03`: no link-only pseudo-completion
- `INV-04`: no modality drift (non-media intent must not produce media UI)
- `INV-05`: factual answers must include verifiability markers/evidence

