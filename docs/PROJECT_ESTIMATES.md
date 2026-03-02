# spec-engine — Project Estimates (Build from Scratch)

> **Purpose:** Realistic effort estimates for planning, resourcing, and executive approval.
> All estimates assume building spec-engine from scratch. They are based on the complexity of
> the implemented system and known engineering effort from comparable internal tooling projects.

---

## Table of Contents

1. [Scope & Assumptions](#1-scope--assumptions)
2. [Team Composition](#2-team-composition)
3. [Work Breakdown — Engine Build](#3-work-breakdown--engine-build)
4. [Work Breakdown — Deployment Phases](#4-work-breakdown--deployment-phases)
5. [Consolidated Timeline](#5-consolidated-timeline)
6. [Effort Summary Table](#6-effort-summary-table)
7. [Risk Buffers & Confidence Levels](#7-risk-buffers--confidence-levels)
8. [What Could Accelerate or Delay](#8-what-could-accelerate-or-delay)
9. [Milestones & Decision Gates](#9-milestones--decision-gates)

---

## 1. Scope & Assumptions

### What is being estimated

The full lifecycle from zero to a production-grade automated spec generation system:

1. **Engine build** — the spec-engine codebase (scanners, inferrers, assembler, validator, publisher, CLI)
2. **Batch tooling** — CSV orchestrator, CI templates, utility scripts
3. **Documentation** — developer guide, stakeholder overview, runbooks
4. **Deployment Phase 1** — initial CSV batch load across full API inventory
5. **Deployment Phase 2** — platform-level CI enforcement (with Platform Engineering)
6. **Deployment Phase 3** — steady state, monitoring, expansion

### What is NOT estimated

- API Explorer catalog development (assumed to be an existing system)
- Application team work (no app code changes required — see Assumption A1)
- Platform Engineering internal effort (estimated separately as a dependency)
- OpenAPI spec authoring for MANUAL-confidence cases (falls to API teams)

### Estimation basis

These estimates are grounded in:
- The actual spec-engine codebase that was prototyped (6 framework scanners,
  4 schema inferrers, assembler, validator, publisher, 365 tests, 2,200+ lines of docs)
- Typical effort ratios for AST-based static analysis tooling
- Known complexity drivers: Go binary companion, Node.js subprocess management,
  javalang annotation quirks, DRF nested router detection, cycle detection in inferrers

---

## 2. Team Composition

### Recommended team (minimum viable)

| Role | FTE | Who | Notes |
|---|---|---|---|
| Senior Backend Engineer (Python) | 1.0 | SRE Frameworks | Leads scanner, inferrer, CLI, assembler |
| Senior Backend Engineer (Polyglot) | 1.0 | SRE Frameworks | Leads Go/TypeScript tooling, batch scripts, CI integration |
| Platform Engineer | 0.5 | Platform Engineering | Runner images, Required Workflow, Jenkins lib — **external dependency** |
| Product/Project Manager | 0.2 | SRE Frameworks | Coordination, stakeholder comms, milestone tracking |

**Core engine team: 2 FTE senior engineers**

### Acceptable with reduced scope

| Reduced scope | Impact |
|---|---|
| 1 senior engineer | Double all engine timelines; batch and deployment phases serialise |
| Skip Go/TypeScript inferrers initially | Save 3–4 weeks; cover 70% of inventory (Java + Python dominant) |
| Skip batch tooling initially | Run spec-engine manually per repo; add orchestrator in Phase 2 |

---

## 3. Work Breakdown — Engine Build

Estimates are **wall-clock weeks with 2 engineers working in parallel**
unless otherwise noted. Each sub-item shows the primary owner (Eng A = Python lead,
Eng B = polyglot lead).

---

### 3.1 Discovery & Architecture — 3 weeks

| Task | Owner | Notes |
|---|---|---|
| Framework inventory: catalogue annotation patterns across target repos | Both | 20–40 sample repos; Spring, FastAPI, Django, Express, NestJS, Gin |
| Explorer catalog API integration spec | Eng A | Auth, endpoints, payload shape, rate limits |
| Architecture design + ADRs | Both | Tech stack, pipeline stages, confidence model, config layering |
| Technology spikes | Eng B | Prove out Go binary approach; prove NestJS Node subprocess path |
| Dev environment, CI for spec-engine itself | Eng B | GitHub Actions, pytest, coverage gates |

**Risk:** Framework inventory reveals unusual patterns (annotation inheritance, custom wrappers)
that require additional scanner complexity → +1 week buffer built into engine phases.

---

### 3.2 Core Infrastructure — 3 weeks

| Task | Owner | Complexity |
|---|---|---|
| Data models: `RouteInfo`, `SchemaResult`, `ParamInfo`, `Confidence` | Eng A | Low |
| `Config` system with YAML loading and CLI override layering | Eng A | Medium |
| `BaseScanner` + `_iter_files()` with SKIP_DIRS | Eng A | Low |
| `BaseInferrer` with cycle detection, `_rank_candidates()` | Eng A | Medium |
| CLI skeleton (Click groups: generate, scan, schema, assemble, validate, publish) | Eng A | Low |
| `Assembler` skeleton (operationId generation, error schemas, x- field injection) | Eng B | Medium |
| Test infrastructure (pytest fixtures, `tmp_path`, monkeypatching patterns) | Both | Low |

---

### 3.3 Spring Boot Scanner + Java Inferrer — 3.5 weeks

**This is the most complex scanner.** Spring annotation parsing has significant edge cases.

| Task | Owner | Complexity | Key difficulty |
|---|---|---|---|
| `SpringScanner`: `@RestController`, `@Controller` detection | Eng A | Medium | Class-level vs method-level path join |
| `@RequestMapping`, `@GetMapping`, `@PostMapping`, etc. | Eng A | Medium | Compound annotations, `produces/consumes` |
| Path variable extraction (`{id}`, regex path variables) | Eng A | Medium | Named groups, optional trailing slash |
| `@RequestBody` and `@RequestParam` extraction | Eng A | High | `required`, `defaultValue`, annotation element parsing |
| javalang annotation quirk: `element` vs `elements` lists | Eng A | High | Only discovered during real repo testing |
| `JavaASTInferrer`: class/field traversal with javalang | Eng B | High | Java type hierarchy, generic types |
| Jackson annotations: `@JsonProperty`, `@JsonIgnore` | Eng B | Medium | |
| Bean Validation: `@NotNull`, `@Size`, `@Min`, `@Max` | Eng B | Medium | Maps to `required`, `minLength`, etc. |
| Unit tests: ~50 tests, real Spring fixture files | Both | Medium | |

---

### 3.4 Python Scanners + Inferrer — 3 weeks

| Task | Owner | Complexity | Key difficulty |
|---|---|---|---|
| `FastAPIScanner`: decorator detection, path param extraction | Eng A | Medium | |
| FastAPI global BaseModel pre-pass (models imported from other files) | Eng A | High | Repo-wide pre-pass before per-file scan |
| `DjangoScanner`: two-pass URL routing + views AST | Eng A | High | `include()` chains, `router.register()` |
| DRF mixin ViewSets: `ReadOnlyModelViewSet`, mixin combos | Eng A | High | `_MIXIN_ROUTE_MAP`, `_compute_allowed_actions()` |
| DRF nested routers: `NestedSimpleRouter` path rewrite | Eng A | High | AST pre-pass for router var types |
| `PythonASTInferrer`: Pydantic v1/v2 fields, dataclasses | Eng B | Medium | `Field(...)` parsing, `model_config` |
| Unit tests: ~70 tests | Both | Medium | |

---

### 3.5 JavaScript / TypeScript Scanners + Inferrer — 3 weeks

| Task | Owner | Complexity | Key difficulty |
|---|---|---|---|
| `express_ast.js` Node.js companion script (route walker) | Eng B | High | AST traversal of `app.get()`, `router.use()` chains |
| `ExpressScanner`: subprocess management, timeout, JSON parse | Eng B | Medium | Process cleanup, stderr capture |
| `NestJSScanner`: `_node_available()` probe, delegate to Express or regex | Eng B | Medium | Framework relabelling via `dataclasses.replace` |
| NestJS Python regex fallback: `@Controller`, `@Get`, `:param → {param}` | Eng B | Medium | |
| TypeScript inferrer companion script (ts-morph) | Eng B | High | ts-morph setup, interface/class/type alias extraction |
| `TypeScriptASTInferrer`: subprocess, JSON schema extraction | Eng B | Medium | |
| `scanner/__init__.py` framework routing (split nestjs from express) | Eng B | Low | |
| Unit tests: ~40 tests including monkeypatched subprocess | Both | Medium | |

---

### 3.6 Go Scanner + Inferrer — 3.5 weeks

**This requires a separate Go codebase compiled to a binary.**

| Task | Owner | Complexity | Key difficulty |
|---|---|---|---|
| `go_schema_tool` companion binary (Go AST walker) | Eng B | High | Separate Go module, struct tag parsing, compilation |
| Struct tag parsing: `json:"..."`, `validate:"required,min=1,max=100"` | Eng B | High | regex for validate tags, nullable pointer detection |
| Gin scanner: `router.GET()`, `router.Group()`, path param normalisation | Eng B | Medium | |
| Echo scanner: `e.GET()`, `e.Group()`, middleware chains | Eng B | Medium | |
| `GoASTInferrer`: binary path detection, subprocess, regex fallback | Eng B | High | Fallback regex for when binary not compiled |
| Binary caching: reuse compiled binary across runs | Eng B | Low | |
| Unit tests: ~30 tests, `_ast_binary = None` to force regex path | Both | Medium | |

---

### 3.7 Assembler — 2.5 weeks

| Task | Owner | Complexity | Key difficulty |
|---|---|---|---|
| `_detect_api_metadata()`: pom.xml, package.json, CODEOWNERS | Eng A | Low | |
| Full paths object with path deduplication | Eng A | Medium | |
| operationId generation and deduplication | Eng A | Medium | verb + path → camelCase, collision handling |
| Schema components section (`$ref` building) | Eng A | High | Cycle detection, circular ref prevention |
| Standard error responses (400, 401, 403, 404, 500) | Eng A | Low | |
| `x-confidence`, `x-owner`, `x-gateway`, `x-lifecycle` injection | Eng A | Low | |
| ruamel.yaml serialisation preserving key order | Eng A | Low | |
| Unit tests: ~40 tests | Both | Medium | |

---

### 3.8 Validator + Publisher — 2 weeks

| Task | Owner | Complexity | Key difficulty |
|---|---|---|---|
| `Validator`: shell out to `spectral lint` and/or `redocly lint` | Eng B | Low | stdout/stderr capture, exit code mapping |
| `Publisher`: `POST /apis` + `PUT /apis/{id}` with title dedup | Eng A | Medium | httpx, token injection, error handling |
| `publisher._check_existing()`: lookup before create vs update | Eng A | Medium | |
| Dry-run mode throughout | Eng A | Low | |
| Unit tests: ~25 tests with httpx mocking | Both | Medium | |

---

### 3.9 Unit Test Suite Completion — 2 weeks

By this point most tests are already written alongside features. This phase closes gaps:

| Task | Notes |
|---|---|
| Close coverage to 80%+ target | Run `pytest --cov` and identify uncovered paths |
| Edge case tests: empty repos, no routes found, zero-field types | |
| CLI integration tests: full generate pipeline with `tmp_path` | |
| Confidence model tests: MANUAL blocks publish, HIGH auto-publishes | |

---

### 3.10 Batch Tooling & Documentation — 2 weeks

| Task | Owner |
|---|---|
| `batch_loader.py`: CSV loader, `clone_repo()`, `process_row()`, `ProcessPoolExecutor`, report writers | Eng B |
| `batch_pr_creator.py` (voluntary-only tool) | Eng B |
| `set_repo_variables.sh`, `validate_all_specs.sh` | Eng B |
| CI templates: reusable workflow YAML, Required Workflow YAML, Jenkins groovy step | Eng B |
| Developer Guide (~2,000 lines) | Eng A |
| Stakeholder Overview (~1,200 lines) | Both |
| Runbooks: publisher failure, token rotation, MANUAL triage | Eng A |

---

### Engine Build Summary

| Phase | Wall-clock weeks (2 engineers) | Parallel? |
|---|---|---|
| 3.1 Discovery & Architecture | 3 | Fully parallel |
| 3.2 Core Infrastructure | 3 | Split between engineers |
| 3.3 Spring Boot + Java | 3.5 | Eng A leads; Eng B assists on inferrer |
| 3.4 Python Scanners + Inferrer | 3 | Eng A leads; Eng B assists on tests |
| 3.5 JS/TS Scanners + Inferrer | 3 | Eng B leads; Eng A assists on tests |
| 3.6 Go Scanner + Inferrer | 3.5 | Eng B leads; Eng A assists on tests |
| 3.7 Assembler | 2.5 | Eng A leads; Eng B on tests |
| 3.8 Validator + Publisher | 2 | Parallel (A: publisher, B: validator) |
| 3.9 Test suite completion | 2 | Both |
| 3.10 Batch tooling + Docs | 2 | Split |
| **Total** | **~27–30 weeks** | |

> **With 2 engineers working in parallel, the engine build takes approximately 7 months.**
> With 1 engineer, add 60–70% to each phase → ~11–12 months for the engine alone.

---

## 4. Work Breakdown — Deployment Phases

These phases begin after the engine build is complete and unit-tested.
They run sequentially for the batch phases; Platform Engineering engagement
starts in parallel with Phase 1.

---

### Phase 0 — Pilot (2–3 weeks)

**Goal:** Validate the engine against real repos. Fix critical issues before scaling.

| Task | Notes |
|---|---|
| Select 10–15 pilot repos: 2–3 per framework | Include one "messy" repo per framework |
| Run batch loader against pilot repos | Manual review of each generated spec |
| Spec quality review with pilot API teams | Identify confidence breakdowns, missing routes |
| Fix critical engine bugs found in real repos | Budget: 1 week of fixes; likely 3–8 bugs |
| Stakeholder demo: pilot results, confidence breakdown | Go/no-go gate for Phase 1 |

**Expected pilot outcome:** 85–90% of pilot repos produce HIGH or MEDIUM confidence specs on first run.

---

### Phase 1 — Full CSV Batch Load (4–5 weeks)

**Goal:** Generate and publish specs for the entire API inventory.

| Task | Duration | Notes |
|---|---|---|
| CSV validation and cleanup | 1 week | Fix stale URLs, missing framework annotations, dedup rows |
| Credential setup: `GIT_TOKEN`, `EXPLORER_API_TOKEN` | 1–2 days | Service account, secret rotation schedule |
| Full batch run (all repos) | 1–2 days | `batch_loader.py --workers 16 --dry-run` then `--publish` |
| Triage `batch_report.csv`: classify failures | 1 week | git clone failures, unsupported frameworks, MANUAL confidence |
| Re-run failed rows after fixes | 2–3 days | `--retry-failed batch_report.csv` |
| MANUAL confidence triage with API teams | Ongoing | Cap at 10% of total; prioritise by team traffic |
| Publish first catalog coverage metric to leadership | End of Phase 1 | Target: ≥90% of inventory published |

**Expected Phase 1 outcome:** 85–95% success rate. ~5–15% of repos require manual intervention
(wrong framework, unusual patterns, unsupported language).

---

### Phase 2 — Platform CI Enforcement (6–10 weeks)

**Goal:** Every push to main in tagged repos automatically publishes a fresh spec.

**Critical dependency:** Platform Engineering team availability. This phase is
gated on PE bandwidth and runs largely on their schedule.

| Week | SRE Frameworks | Platform Engineering |
|---|---|---|
| W1 | Kickoff: share requirements, reusable workflow YAML, Jenkins groovy step | Confirm scope, assign PE engineer |
| W2–3 | Answer PE questions, test runner image | Install Python + Node.js on runner images; create org secret |
| W4–5 | Test Required Workflow on 3 pilot repos | Configure Required Workflow org policy (or Jenkins Shared Library) |
| W6 | Run `set_repo_variables.sh` to bulk-set repo variables from CSV | Monitor rollout, fix runner issues |
| W7–8 | Monitor success rate, fix engine issues found at CI scale | Adjust runner config if needed |
| W9–10 | Buffer for PE delays, edge cases, and any org policy exceptions | Rollout to remaining repos |

**Risk:** Platform Engineering engagement is the #1 schedule risk.
If PE is unavailable for 4+ weeks, this phase slips. Approach 1 (batch) continues
delivering value independently during any delay.

---

### Phase 3 — Steady State (Month 4+, Ongoing)

**Goal:** Low-maintenance operation with continuous catalog freshness.

| Ongoing task | Cadence | Effort |
|---|---|---|
| Monitor batch run success rate (if re-run monthly) | Monthly | 2 hours |
| Triage MANUAL-confidence cases escalated by teams | Weekly | 2–4 hours |
| Add scanner support for new framework versions | As needed | 1–3 days per version update |
| Add new framework scanner (e.g., Rails, Laravel) | Per roadmap | 2–4 weeks per framework |
| CSV updates: new APIs, deprecated repos removed | Per API governance cycle | 1–2 hours |
| Secret rotation: `GIT_TOKEN`, `EXPLORER_API_TOKEN` | Quarterly | 1 hour |
| Engine dependency updates (Python, Node.js, javalang) | Quarterly | 1–2 days |
| Onboard new framework: requirements → scanner → tests → release | As requested | 3–5 weeks |

**Steady-state maintenance: 0.2–0.3 FTE per engineer** (shared across the SRE Frameworks team).

---

## 5. Consolidated Timeline

```
Month 1       Month 2       Month 3       Month 4       Month 5       Month 6       Month 7
│─────────────┤─────────────┤─────────────┤─────────────┤─────────────┤─────────────┤────
│ Discovery   │
│ & Arch (3w) │
│             │ Core Infra  │
│             │ (3w)        │
│             │             │ Spring+Java │
│             │             │ (3.5w)      │
│             │ FastAPI+DRF │             │
│             │ (3w, A)     │             │
│             │             │ JS/TS       │
│             │             │ (3w, B)     │
│             │             │             │ Go (3.5w,B) │
│             │             │             │             │ Assembler   │
│             │             │             │             │ (2.5w, A)   │
│             │             │             │             │             │ Validator+  │
│             │             │             │             │             │ Publisher   │
│             │             │             │             │             │ Tests + Docs│
│             │             │             │             │             │             │ ← Engine done
```

```
Month 7       Month 8       Month 9       Month 10      Month 11      Month 12+
│─────────────┤─────────────┤─────────────┤─────────────┤─────────────┤────────────
│ Pilot       │
│ (2-3w)      │
│             │ Phase 1:    │
│             │ CSV Batch   │
│             │ (4-5w)      │
│             │─────────────────────────────────────────────────────────────────────
│             │ PE Engagement starts (parallel, PE-paced)
│             │             │             │ Phase 2:    │
│             │             │             │ Platform CI │
│             │             │             │ Rollout     │
│             │             │             │ (6-10w)     │
│             │             │             │             │             │ Phase 3:
│             │             │             │             │             │ Steady State
```

**Total: approximately 12–14 months from kickoff to full production** (2 engineers).

---

## 6. Effort Summary Table

| Work item | Weeks (2 engineers, parallel) | Engineer-weeks | Confidence |
|---|---|---|---|
| Discovery & Architecture | 3 | 6 | High |
| Core Infrastructure | 3 | 5 | High |
| Spring Boot + Java Inferrer | 3.5 | 5 | High |
| Python Scanners + Inferrer | 3 | 5 | High |
| JS/TS Scanners + Inferrer | 3 | 5 | Medium |
| Go Scanner + Inferrer | 3.5 | 5.5 | Medium |
| Assembler | 2.5 | 4 | High |
| Validator + Publisher | 2 | 3.5 | High |
| Test suite completion | 2 | 4 | High |
| Batch tooling + Documentation | 2 | 3.5 | High |
| **Engine Build Total** | **~28 weeks** | **~46 engineer-weeks** | |
| | | | |
| Pilot (Phase 0) | 3 | 4 | High |
| CSV Batch Load (Phase 1) | 5 | 7 | Medium |
| Platform CI Rollout (Phase 2) | 8–10 | 6 (SRE only) | Low (PE-dependent) |
| Ongoing maintenance (Phase 3) | Ongoing | 0.25 FTE/year | High |
| **Total to full production** | **~52–56 weeks** | **~63–65 engineer-weeks** | |

---

## 7. Risk Buffers & Confidence Levels

### Confidence by phase

| Phase | Estimate confidence | Reason |
|---|---|---|
| Engine build (core scanners, Python/Java) | **High** | Known patterns; similar work completed |
| Engine build (Go binary, NestJS subprocess) | **Medium** | External tool dependencies; OS/PATH issues in CI common |
| Engine build (assembler, publisher) | **High** | Well-understood HTTP + YAML work |
| Pilot and Phase 1 batch | **Medium** | Real repo diversity always reveals unexpected patterns |
| Phase 2 (Platform Engineering) | **Low** | Entirely dependent on PE team's roadmap and availability |

### Recommended buffers

| Phase | Base estimate | Buffer | Buffered estimate |
|---|---|---|---|
| Engine Build | 28 weeks | +15% | 32 weeks |
| Pilot | 3 weeks | +33% | 4 weeks |
| Phase 1 CSV Batch | 5 weeks | +40% | 7 weeks |
| Phase 2 Platform CI | 8–10 weeks | +50% | 12–15 weeks |

**Total with buffers: ~55–62 weeks (~13–15 months).**

---

## 8. What Could Accelerate or Delay

### Accelerators

| Factor | Weeks saved |
|---|---|
| Reuse an existing Go AST library instead of custom binary | 2–3 weeks |
| Target only 3 frameworks initially (Spring, FastAPI, Django), add others later | 5–7 weeks |
| Platform Engineering has runner images and org secrets already set up | 3–4 weeks (Phase 2) |
| Teams use standard annotations consistently (no custom wrappers) | 1–2 weeks (fewer scanner edge cases) |
| Pre-validated, clean API inventory CSV from CMDB | 1–2 weeks (Phase 1) |
| 3rd engineer added to engine build team | 4–6 weeks (engine phase) |

### Delayers

| Factor | Weeks added |
|---|---|
| Framework version diversity requiring per-version scanner branches | 3–5 weeks |
| Widespread monorepos in the inventory | 2–3 weeks (scanner rework) |
| Platform Engineering unavailable for 6+ weeks | 6–12 weeks (Phase 2) |
| Explorer catalog API is undocumented or unstable | 2–4 weeks (publisher rework) |
| Security review requires changes to token handling or data residency | 2–4 weeks |
| Unexpected prevalence of dynamic route registration | 3–5 weeks (requires confidence model rework) |
| Java type system edge cases: generics, inner classes, sealed classes | 2–3 weeks |

---

## 9. Milestones & Decision Gates

| # | Milestone | When | Decision / action |
|---|---|---|---|
| M1 | Architecture approved | Week 3 | Proceed to engine build |
| M2 | Spring Boot + FastAPI end-to-end working | Week 10 | Demo to API Governance team; confirm priority framework list |
| M3 | All 6 scanners complete, 80% test coverage | Week 22 | Go/no-go for batch tooling; request pilot repo nominations |
| M4 | Engine complete + documented | Week 28 | Go/no-go for pilot |
| M5 | Pilot complete (10–15 repos) | Week 31 | Leadership demo; approve Phase 1 CSV batch |
| M6 | Phase 1 complete (≥90% inventory published) | Week 38 | Celebrate; initiate PE engagement for Phase 2 |
| M7 | Phase 2 Required Workflow live on pilot repos | Week 46 | PE go/no-go for org-wide rollout |
| M8 | Phase 2 fully rolled out | Week 52–56 | Steady state; hand off to run-and-maintain mode |

---

*Document version: March 2026*
*Status: Draft for planning and executive review*
*Authors: SRE Frameworks Team*
