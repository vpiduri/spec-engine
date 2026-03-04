# Design Proposal: Automated OpenAPI Spec Generation Platform
# spec-engine

| | |
|---|---|
| **Status** | Proposed |
| **Date** | March 2026 |
| **Authors** | Digital Experience SRE Team |
| **Audience** | Engineering Leadership, API Owners, Platform Engineering |
| **Related docs** | `ADR.md`, `DEVELOPER_GUIDE.md`, `PROJECT_ESTIMATES.md` |

---

## Overview

This proposal describes **spec-engine** — a platform that automatically generates
OpenAPI 3.1 specifications for every API service in our organization directly from
source code, and keeps those specifications up to date without requiring any changes
to application code or developer workflows.

The platform uses **Abstract Syntax Tree (AST) parsing** — the same technique used
by compilers and IDEs — to read route definitions and type schemas from Java, Python,
TypeScript, and Go services and convert them into published, governed API specifications
in the Explorer catalog.

Deployment uses two complementary strategies:
1. **CSV batch onboarding** — generate baseline specs for all existing services at once
2. **Platform CI enforcement** — keep specs fresh automatically on every merge to main

**Investment:** $500,000 over 6 months with a payback period under 5 months.

---

## Background

The Explorer API catalog is the organization's single source of truth for API contracts.
It enables consumer teams to discover APIs, understand request/response shapes, and
integrate without chasing down API owners for documentation.

Today, **85%+ of API services have no catalog entry**. The cause is not intent — it is
friction. Writing an OpenAPI spec manually for a non-trivial Spring Boot or FastAPI service
takes 3–8 hours. Keeping it accurate across releases is an ongoing tax that is consistently
deprioritised against feature delivery.

The result:
- Consumer teams spend weeks on integration that should take days
- Governance cannot be audited — ownership, lifecycle, and gateway metadata are missing
- API quality is invisible to leadership
- Explorer ROI is undermined by low catalog adoption

This is a **platform problem**, not a team behaviour problem. The solution must remove
the friction structurally, not ask teams to do more work.

### Scope

| Dimension | In scope |
|---|---|
| Frameworks | Java/Spring Boot, Python/FastAPI, Python/Django REST, TypeScript/NestJS, JavaScript/Express, Go/Gin, Go/Echo |
| Services | ~200 API services in current inventory |
| Deployment | CSV batch (initial load) + GitHub Actions / Jenkins (ongoing) |
| Application code changes | None required |
| Explorer catalog | Existing API; spec-engine calls its publish endpoint |

---

## Objective

**Primary objective:** Achieve ≥ 90% API catalog coverage with accurate, governed
OpenAPI specifications within one quarter, and maintain that coverage automatically
going forward.

### Success Criteria

| Metric | Target |
|---|---|
| Inventory coverage | ≥ 90% of services in Explorer |
| Spec freshness | < 24 hours post-merge (target: < 5 minutes) |
| HIGH + MEDIUM confidence schemas | ≥ 90% of all generated schemas |
| CI pipeline success rate | ≥ 98% |
| MANUAL review backlog | < 10% of inventory |
| Manual documentation burden on teams | Zero |

### Non-objectives

- Application testing or code quality analysis
- API gateway configuration or traffic management
- LLM-based spec generation (see ADR-007)
- Spec versioning per commit (Phase 3 roadmap)

---

## Design Details

### Current State

#### Problem: Documentation does not scale manually

```
Today's workflow:
  API team ships a route
        │
        ▼
  PM asks for OpenAPI spec
        │
        ▼
  Developer manually writes YAML  (3–8 hrs)
        │
        ▼
  Spec committed — immediately starts drifting
        │
        ▼
  Next release: spec is wrong, no one updates it
        │
        ▼
  Explorer entry is stale or missing
```

#### Operational consequences

| Issue | Impact |
|---|---|
| Spec drift | Consumer integration defects; late discovery of breaking changes |
| Manual YAML authoring | 3–8 hours per service; never reprioritised |
| No enforcement | Governance gaps survive indefinitely |
| Inconsistent metadata | Audit risk; ownership unclear |
| No batch onboarding path | Legacy services remain undocumented |

#### Current catalog state

- **~15% of services** have an accurate, published spec
- **~85% have no entry** in Explorer
- Governance metadata (`x-owner`, `x-gateway`, `x-lifecycle`) is inconsistently applied
- No automated freshness mechanism exists for any service

---

### Target State

```
Every API service ships code
        │
        ▼
  Git push to main
        │
        ▼
  spec-engine runs in CI (< 90 seconds)
        │
        ▼
  OpenAPI 3.1 spec generated from source
        │
        ▼
  Validated (Spectral + Redocly)
        │
        ▼
  Published to Explorer catalog automatically
        │
        ▼
  Explorer shows accurate, governed, fresh spec
```

**Target state in numbers:**

| Dimension | Today | Target (6 months) |
|---|---|---|
| Catalog coverage | ~15% | ≥ 90% |
| Spec freshness | Weeks to years | < 5 minutes post-merge |
| Manual authoring hours | 3–8 hrs per service | 0 |
| Governance enforcement | Manual / spot-check | Automated in CI |
| Frameworks supported | Varies by team tool | 7 unified |

---

### Core Pipeline

```
         Source Repository
               │
               ▼
  ┌─────────────────────────┐
  │  Stage 0 — Pre-flight   │  Detect existing committed spec
  │  (detector.py)          │  Fast-path publish / merge / skip
  └────────────┬────────────┘
               │ (if no fast-path)
               ▼
  ┌─────────────────────────┐
  │  Stage 1 — Scanner      │  Walk source via AST
  │  (scanner/)             │  Extract: method, path, params, handler
  └────────────┬────────────┘
               │  List[RouteInfo]
               ▼
  ┌─────────────────────────┐
  │  Stage 3 — Inferrer     │  Resolve request/response types via AST
  │  (inferrer/)            │  Output: JSON Schema + Confidence level
  └────────────┬────────────┘
               │  Dict[str, SchemaResult]
               ▼
  ┌─────────────────────────┐
  │  Stage 4 — Assembler    │  Build OpenAPI 3.1 YAML
  │  (assembler.py)         │  Inject x-owner, x-gateway, x-lifecycle
  └────────────┬────────────┘
               │  openapi.yaml
               ▼
  ┌─────────────────────────┐
  │  Stage 5 — Validator    │  Spectral + Redocly lint
  │  (validator.py)         │  Fail on HIGH violations
  └────────────┬────────────┘
               ▼
  ┌─────────────────────────┐
  │  Stage 6 — Publisher    │  POST/PUT to Explorer catalog API
  │  (publisher.py)         │  Gated on confidence level
  └─────────────────────────┘
```

Single command: `spec-engine generate --repo . --gateway kong-prod --publish`

---

### Key Features

#### Feature 1: AST-based source analysis (ADR-001)

**What it does:** Parses source code into a structured tree — the same technique used
by compilers and IDEs — and walks the tree to extract route definitions and type schemas
without running the application.

```
@GetMapping("/v1/accounts/{id}")               Method Declaration
public Account getAccount(                  →    ├── annotation: GetMapping("/v1/accounts/{id}")
    @PathVariable UUID id) { ... }               ├── return type: Account
                                                 └── param: @PathVariable UUID id
```

**Why it matters:**
- No running application required — works in a CI build that has only source code
- Deterministic — same code always produces the same spec
- Secure — source code never leaves your infrastructure

**Alternatives rejected:**

| Option | Why rejected |
|---|---|
| Runtime / reflection | Requires live application, database, test data in CI — impossible for most services |
| Regex on source | Breaks on multi-line annotations, nested generics, whitespace variation — not production quality |
| LLM / AI inference | Non-deterministic, external data exposure, unbounded cost, can hallucinate schemas (see ADR-007) |
| Framework built-ins (SpringDoc, FastAPI /docs) | Runtime-only, one tool per framework, no unified governance, cannot enforce org x- metadata |

---

#### Feature 2: Multi-language support via native parsers (ADR-002)

**What it does:** Uses the best AST parser available in each language's own toolchain,
connected via a subprocess JSON bridge for languages that cannot be called directly from Python.

| Language | Framework | Parser | Runs where |
|---|---|---|---|
| Python | FastAPI, Django REST | `ast` (stdlib) | In-process |
| Java | Spring Boot | `javalang` (pip) | In-process |
| TypeScript | NestJS, Express | `ts-morph` (npm) | Node.js subprocess |
| Go | Gin, Echo | `go/ast` (stdlib) | Compiled Go subprocess |

**Subprocess bridge:** TypeScript and Go parsers run as subprocesses, emit JSON to stdout,
and Python reads the result. Timeout: 10 seconds. If unavailable: regex fallback or MANUAL confidence.

**Why language-native parsers:** Generic multi-language tools (e.g. Tree-sitter) do not
understand type systems, annotation semantics, or generic resolution at the depth required
for accurate schema inference. `ts-morph` uses the TypeScript compiler itself; `go/ast` is
the same parser used by the Go toolchain.

---

#### Feature 3: Confidence-driven governance (ADR-003)

**What it does:** Assigns a confidence level to every generated schema based on how
completely it was resolved. Confidence gates publish behaviour — we never publish a
silently wrong schema.

| Level | Assigned when | Publish behaviour |
|---|---|---|
| `HIGH` | All fields fully resolved from type annotations | Auto-publish |
| `MEDIUM` | Partial resolution; some fields inferred heuristically | Publish + flag for review |
| `LOW` | Regex fallback used; result uncertain | Block publish; human review required |
| `MANUAL` | Type unresolvable (dynamic, external library, reflection) | Block; publish as stub with `x-confidence: manual` |

**Key design choice:** Confidence is per-schema, not per-spec. A spec with 40 HIGH routes
and 2 MANUAL routes publishes successfully. MANUAL routes appear as visible stubs, not
silent gaps. This is better than blocking the entire spec because one type lives in a
shared library.

---

#### Feature 4: Dual deployment — batch onboarding + CI enforcement (ADR-004)

Two complementary approaches that solve different problems.

**Approach A — CSV Batch Onboarding**

Purpose: Generate baseline specs for all existing services immediately.

```
api_inventory.csv
  (api_name, team, gateway, repo_url, framework, ...)
        │
        ▼
batch_loader.py
  ├── git clone --depth 1 {repo_url}   (parallel, 16 workers)
  ├── spec-engine generate --repo .
  ├── logs to logs/{api_name}.log
  └── results to batch_report.csv + batch_summary.json
```

- `ProcessPoolExecutor` (16 workers) — true CPU parallelism, avoids Python GIL
- `--depth 1` shallow clone reduces clone time from ~30s to ~5s per repo
- `--retry-failed` mode re-runs only failed rows
- Produces `batch_report.csv` with confidence distribution and failure classification

**Approach B — Platform CI Enforcement**

Purpose: Keep specs fresh automatically on every merge. No team action required.

```yaml
# Reusable workflow — maintained centrally by SRE Frameworks
jobs:
  generate-spec:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install spec-engine
      - run: |
          spec-engine generate \
            --repo . \
            --gateway "${{ vars.API_GATEWAY }}" \
            --owner   "${{ vars.API_OWNER }}" \
            --publish
        env:
          EXPLORER_API_TOKEN: ${{ secrets.EXPLORER_API_TOKEN }}
```

| Enforcement mechanism | How | Team impact |
|---|---|---|
| **GitHub Required Workflow** | Org-level policy; runs on all repos tagged `api-service` | Zero — step appears automatically |
| **Jenkins Shared Library** | `specEngine()` step added to `standardPipeline()` | Zero — teams already use the shared library |

**Trigger strategy:**

| Trigger | Action | Rationale |
|---|---|---|
| Push to `main` / `master` | Generate + publish | Stable, reviewed code |
| Pull request | Validate only | Early feedback; no WIP in catalog |
| Feature branch | Skip | Incomplete routes |
| `workflow_dispatch` | Generate + publish | Manual re-publish without a code push |

---

#### Feature 5: Existing spec detection and reuse (ADR-005)

**What it does:** Before running the full pipeline, spec-engine detects any committed
OpenAPI spec in the repo and evaluates it against three quality gates.

```
Existing spec found?
│
├── Gate 1: Format valid? (OpenAPI 3.x or Swagger 2.0)
│   └── Fail → full AST pipeline
│
├── Gate 2: Route coverage ≥ 70%?
│   (routes in spec / routes found by AST scanner)
│   └── Fail → merge mode
│
└── Gate 3: Freshness ≤ 90 days?
    └── Fail → flag as STALE, usable with warning
```

| Gates passed | Mode | What publishes |
|---|---|---|
| All three | **Fast-path** | Existing spec + injected x- fields (~8s total) |
| Format ✅, Coverage ❌ | **Merge** | AST routes/schemas + existing descriptions/examples |
| Format ❌ | **Full AST** | Standard pipeline; existing spec ignored |

Impact: ~20–35% of enterprise repos have a committed spec. Roughly half pass quality
gates → fast-path eligible, reducing Phase 1 batch time by ~10–15%.

---

#### Feature 6: Zero application code changes (ADR-006)

spec-engine is strictly read-only. It clones repos, reads files, generates specs,
and discards the clone. Application teams need not change anything — no library
imports, no annotations, no CI additions, no PR approvals.

Platform-level enforcement (GitHub Required Workflow / Jenkins Shared Library)
achieves catalog coverage without any coordination with application teams.

---

#### Feature 7: Drift detection (ADR-008)

**What it does:** Optionally flags catalog entries that have gone stale due to CI
misconfiguration or repos that have not pushed to main in an extended period.

```
if days_since_last_publish > 7:
    flag service as STALE in catalog

if newly_generated_spec != last_published_spec:
    alert owning team via configured channel
```

Drift detection runs as a nightly scheduled job independent of the CI pipeline.
It catches the gap that CI enforcement cannot: repos that simply have not had
any code changes but whose CI configuration may have broken silently.

---

#### Feature 8: Monorepo support (ADR-009)

**What it does:** Supports multiple specs from a single repository by allowing
multiple CSV rows per repo, each targeting a different service subdirectory.

```
api_name,repo_url,subdir,exclude_paths
accounts-api,https://github.com/org/platform,services/accounts,
payments-api,https://github.com/org/platform,services/payments,services/payments/test
```

Each row is scanned independently. Future CLI enhancement: `--subdir` flag for
direct invocation without a CSV.

---

#### Feature 9: Why not an AI coding agent such as Devin? (ADR-007)

This question arises frequently and deserves a direct, substantive answer.

**Head-to-head comparison:**

| Dimension | AI coding agent (Devin) | spec-engine (AST) |
|---|---|---|
| **Deterministic output** | ❌ Different output on each run | ✅ Same code → same spec, always |
| **Source code security** | ❌ Code sent to external service | ✅ Runs inside your infrastructure |
| **CI/CD integration** | ❌ Interactive agent; not a pipeline command | ✅ Single CLI command with exit code |
| **Cost model** | ❌ Per-session; 200 repos × every push = unbounded | ✅ Fixed infrastructure cost |
| **Schema accuracy** | ❌ Can hallucinate field names, types, routes | ✅ Reads actual code; cannot invent |
| **Scale** | ❌ Session limits, rate limits, not bulk-capable | ✅ 16-worker parallelism; 200 repos per batch |
| **Org metadata enforcement** | ❌ Prompt-dependent; inconsistent | ✅ Config-driven; always present |
| **Audit trail** | ❌ Cannot trace output to a code commit | ✅ Same commit = same spec; fully reproducible |
| **Freshness on every merge** | ❌ Requires a new agent session per push | ✅ Runs automatically in CI in < 90 seconds |
| **Maintenance** | ❌ Model update → spec output changes unpredictably | ✅ Scanner change is a 5-line diff + test |

**Where the actual work is:**

Only 30–35% of this project's effort is code generation — the part where an AI
agent provides leverage. The rest is work that requires internal access and cannot
be delegated externally:

| Activity | % of effort | AI-substitutable? |
|---|---|---|
| Framework scanner implementation (7 frameworks) | 25% | Partially — requires expert validation |
| Schema inferrer (type resolution, generics, cycles) | 20% | No — deep type-system knowledge required |
| Accuracy validation on real enterprise repos | 15% | No — requires internal repo access |
| Security review, infra integration, CI enforcement | 15% | No — internal access required |
| Explorer catalog API integration, confidence governance | 10% | No — internal API, no external credentials |
| Test coverage (365+ tests), regression harness | 10% | Partially |
| Batch tooling, monitoring, MANUAL triage workflow | 5% | Partially |

**The security argument is independently disqualifying.** Our source code contains
proprietary business logic, internal endpoint patterns, and security annotation
structures. Sending this to an external AI service requires a data handling agreement
that takes months to negotiate. spec-engine runs in your VPC; nothing crosses a
network boundary.

**What AI can contribute (additive, not replacement):** AI tools are useful for
authoring human-written `description` fields and triage suggestions on top of what
AST has already generated. This is a Phase 3 enhancement, not an alternative to the
generation pipeline.

---

### Performance Benchmarks

| Repo size | Framework | Routes | Pipeline runtime |
|---|---|---|---|
| Small | FastAPI | ~40 routes | 2–3 seconds |
| Medium | Spring Boot | ~80 routes | 5–8 seconds |
| Large | NestJS | ~100 routes | 12–20 seconds |

**CI impact:** 45–80 seconds total per build, including checkout and dependency install.
This is below the 90-second threshold for developer experience impact.

**Batch throughput (16 workers):** ~200 repos processed in under 3 hours, including
shallow clone time. Monthly re-runs complete in under 2 hours (depth-1 clones cached).

---

### Failure Modes and Safeguards

| Scenario | Behaviour |
|---|---|
| Parser crash on a file | Skip file, log error, continue scanning repo |
| Subprocess timeout (TypeScript/Go) | MANUAL confidence; spec still published as stub |
| Explorer catalog unreachable | Publish fails; spec artifact saved locally; pipeline retries 3× |
| Authentication token expired | 401 → pipeline fails with clear error |
| Dynamic routing (runtime-registered routes) | Stub schema + MANUAL confidence |
| Type defined in shared library (external repo) | Empty schema + MANUAL; stub published |

No silent failures. Every failure is logged, classified in `batch_report.csv`,
and surfaced via CI exit code.

---

## Recommendations

### Architecture recommendations

1. **Build on AST — do not prototype with regex or LLM.** The fragility cost of
   regex emerges in Month 3 against real enterprise repos. Starting with AST avoids
   rebuilding the scanner layer mid-project.

2. **Implement confidence levels from Day 1.** Retrofitting governance onto a
   "generate everything" model is harder than building it into the confidence model
   from the start. The confidence level gates in ADR-003 prevent the catalog from
   filling with inaccurate data during the pilot.

3. **Adopt the subprocess bridge pattern for TypeScript and Go.** The in-process
   alternative (binding TypeScript/Go parsers to Python) has no reliable production-
   grade library. The subprocess bridge is used by major tools (ESLint, Prettier) and
   is well-understood operationally.

4. **Deploy drift detection (ADR-008) by Month 5.** Without it, a CI misconfiguration
   silently breaks freshness guarantees. Drift detection is the insurance policy for
   the "set and forget" promise we are making to leadership.

5. **Prioritise monorepo support (ADR-009) in the CSV batch design.** At least 20–30%
   of enterprise repos at this scale are monorepos. Supporting multiple CSV rows per
   repo costs almost nothing in the batch design but avoids a painful retrofit later.

### Deployment recommendations

6. **Run batch onboarding in Month 5, not earlier.** A premature batch run against
   200 repos before the scanner is hardened on real code generates a MANUAL triage
   backlog that teams will not trust. The pilot in Month 4 (10–15 real services)
   is the gate before full batch.

7. **Start with GitHub Required Workflow for platform enforcement.** Jenkins Shared
   Library is the right path for teams on Jenkins, but the GitHub enforcement path
   requires zero coordination with application teams and demonstrates coverage faster.

8. **Set repo variables via `set_repo_variables.sh` before batch run.** `API_GATEWAY`
   and `API_OWNER` must be set per repo before CI enforcement goes live, or specs
   publish with `gateway=unknown` and fail validation. This is a PE task in Week 3.

### Team recommendations

9. **Assign Eng1 to core infrastructure exclusively for Month 1.** The assembler,
   models, and publisher are the dependency for every other engineer. Any slip here
   stalls all four workstreams. The PM watches Eng1 daily.

10. **Survey 20–30 real repos per framework before writing scanner code.** Week 1 is
    verification, not implementation. Annotation patterns discovered in real repos in
    Week 1 take 1 day to handle in the scanner design. Discovered in Month 3 during
    pilot, they take a week and break the milestone gate.

---

## Execution Plan

### Team

| Role | Count | Focus |
|---|---|---|
| Senior Engineer — Core | 1 (Eng1) | Config, models, assembler, publisher, CLI |
| Senior Engineer — Java | 1 (Eng2) | Spring Boot scanner + Java AST inferrer |
| Senior Engineer — Python | 1 (Eng3) | FastAPI + Django REST scanner + Python inferrer |
| Senior Engineer — Go/TS | 1 (Eng4) | Go binary, Gin/Echo, Express, NestJS, TypeScript |
| Program Manager | 1 (PM) | Coordination, stakeholder demos, risk tracking |
| Platform Engineer | 1 (PE) | Batch tooling, runner images, CI enforcement rollout |

### 6-Month Gantt

```
         Month 1              Month 2              Month 3
         Weeks 1–4            Weeks 5–8            Weeks 9–12
Eng1  ── Core infra ─────── Assembler ─────────── Publisher + CLI ──────►
Eng2  ── Spring scanner ─── Java inferrer ─────── Integration tests ────►
Eng3  ── FastAPI scanner ── DRF scanner ────────── Python inferrer ───────►
Eng4  ── Express/NestJS ─── Go binary + Gin/Echo ─ TS inferrer ──────────►
PE    ── Dev env / CI ────── batch_loader.py ────── PE engagement begins ─►
PM    ── Kickoff / ADRs ─── Framework inventory ─── Risk review / demo prep►

         Month 4              Month 5              Month 6
         Weeks 13–16          Weeks 17–20          Weeks 21–26
Eng1  ── Pilot + bug fixes ─ Batch triage ──────── Monitoring + docs ────►
Eng2  ── Pilot (Spring) ──── MANUAL triage ─────── Handover ─────────────►
Eng3  ── Pilot (Python) ──── MANUAL triage ─────── Handover ─────────────►
Eng4  ── Pilot (Go/TS) ───── CI templates final ── Handover ─────────────►
PE    ── Runner images ────── Full batch load ────── Req Workflow rollout ►
PM    ── Leadership demo #1─ Phase 1 report ─────── Project close ────────►
```

### Milestone Gates

| Milestone | When | Gate question | Go/No-go consequence |
|---|---|---|---|
| **M1 — Architecture approved** | End Week 1 | ADRs signed off? | No: delay start until resolved |
| **M2 — First end-to-end pipeline** | End Month 1 | `spec-engine generate` works for Spring + FastAPI? | No: Eng1 gets dedicated support |
| **M3 — All scanners done** | End Month 2 | All 7 frameworks produce valid `List[RouteInfo]`? | No: cut one framework to Phase 2 |
| **M4 — Engine hardened** | End Month 3 | ≥ 80% test coverage? Publisher talking to catalog (staging)? | No: Month 4 pilot delayed |
| **M5 — Pilot go/no-go** | End Month 4 | 10–15 real repos in catalog. ≥ 90% success rate? | No: fix before full batch |
| **M6 — Phase 1 complete** | End Month 5 | ≥ 90% inventory published. < 5% hard failures? | No: extend batch run into Month 6 |
| **M7 — Platform CI live** | End Month 6 | Required Workflow running on all `api-service` repos? | No: PE extends engagement |

### Critical Path

```
Core infra (Eng1) → Assembler (Eng1) → Publisher (Eng1) → Pilot (all) → Batch
```

All other workstreams (Go, TypeScript, Django) are parallel and do not block the
critical path. If Eng4's Go work slips 2 weeks, the pilot is unaffected. If Eng1's
assembler slips, all four teams stall. PM monitors Eng1 daily.

### Phase Summary

| Phase | Months | Deliverable |
|---|---|---|
| **Phase 1 — Build** | 1–3 | Engine complete, all 7 frameworks, 80%+ test coverage |
| **Phase 2 — Pilot + Batch** | 4–5 | 10–15 service pilot → full 200-service batch onboarding |
| **Phase 3 — Platform** | 6 | Required Workflow rollout; all new pushes auto-publish |

---

## Budget

### Investment breakdown

| Role | Annual cost (fully loaded) | 6-month cost | Count | Total |
|---|---|---|---|---|
| Senior Engineer | $160,000 | $80,000 | 4 | $320,000 |
| Program Manager | $140,000 | $70,000 | 1 | $70,000 |
| Platform Engineer | $150,000 | $75,000 | 1 | $75,000 |
| **Personnel subtotal** | | | | **$465,000** |

| Non-personnel item | Cost |
|---|---|
| CI/CD compute (GitHub Actions minutes, storage) | $12,000 |
| Tooling (Redocly, Spectral, monitoring) | $8,000 |
| Training and ramp-up | $5,000 |
| Contingency (10%) | $10,000 |
| **Non-personnel subtotal** | **$35,000** |

**Total: $500,000**

### ROI Analysis

| | Annual cost |
|---|---|
| **Manual alternative** (3 hrs/spec × 200 services × $100/hr + annual updates) | ~$1,400,000/yr |
| **spec-engine** (Year 1: $500K build + $50K ops) | $550,000 |
| **Year 1 savings** | **$850,000** |
| **Payback period** | **< 5 months** |
| **3-year savings** (Year 2–3: $50K/yr ops vs $1.4M/yr manual) | **~$3.5M** |

### Why not 1 engineer?

The 4 language stacks are independent and genuinely parallel. Serialising them
adds 7 months to the timeline:

```
Serial (1 engineer):                    Parallel (4 engineers):
  Architecture           3w              Architecture    3w  ─┐
  Core infrastructure    3w              Core infra      3w   │ Month 1
  Spring + Java inferrer 5.5w                                  │
  FastAPI + DRF          6w    →         Spring + Java  ────── Month 2–3  (Eng2)
  Express + NestJS       2.5w            FastAPI + DRF  ────── Month 2–3  (Eng3)
  TypeScript inferrer    1.5w            Go/TS + CI     ────── Month 2–3  (Eng4)
  Go binary + inferrer   5.5w            Assembler+Pub  ────── Month 2–3  (Eng1)
  Assembler              2.5w                            ────── Month 4: Pilot
  Validator + Publisher  2w                              ────── Month 5: Batch
  Tests + Documentation  4w                              ────── Month 6: Platform

  Engine total:  ~37.5w (9.4 months)    Engine total:  ~12w (3 months)
  Full delivery: ~53w  (13 months)       Full delivery: ~26w (6 months)
```

On an 18-month cost horizon, 1 engineer is the more expensive option:
1 engineer delivers 7 months later, foregoing ~$820K in savings during the delay.

### Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Annotation pattern not covered by scanner | High | Medium | Week 1 real-repo survey; 365-test suite catches regressions |
| Shared library types unresolvable | High | Low | MANUAL confidence stubs; Phase 3 roadmap for external schema resolution |
| Explorer catalog API changes | Medium | High | Publisher has retry logic; version-pin the catalog API client |
| PE engagement delayed | Medium | Medium | PE joins Month 1; batch design is independent of platform enforcement |
| Real-repo pilot reveals >10% hard failures | Low | High | Month 4 pilot gate exists specifically to catch this before full batch |
| Key engineer attrition | Low | High | 365-test suite and full documentation reduce bus-factor risk |

---

## Conclusion

spec-engine transforms API documentation from a manual, perpetually-deprioritised
team task into an automated platform capability. The case for this investment
rests on three pillars:

**1. The problem is structural, not behavioural.**
85% catalog coverage gap is not caused by teams ignoring their obligations —
it is caused by a process that takes 3–8 hours per service and provides no
automated enforcement. Asking teams to do more will not close this gap.
Removing the friction structurally will.

**2. The technical approach is the only correct one for this context.**
AST parsing is deterministic, secure, CI-native, and horizontally scalable.
Runtime alternatives require live applications. AI alternatives are
non-deterministic, expose source code to external services, and cannot be
reliably invoked as a CI pipeline step. AST is the approach used by every
major IDE and compiler for the same reason we are using it here: it works.

**3. The investment pays back in under 5 months.**
At current manual authoring rates, the organisation spends approximately
$1.4M per year on API documentation that remains inaccurate and incomplete.
spec-engine costs $500K to build and $50K per year to operate — returning
$850K in Year 1 savings and approximately $3.5M over three years.

The 6-month timeline, milestone-gated delivery plan, and pilot-before-batch
strategy are designed to surface risks early and give leadership clear
go/no-go decision points before committing to each subsequent phase.

---

## Appendix A — Route Extraction Model

Each framework scanner produces a structured `RouteInfo` object:

```python
RouteInfo(
    method="GET",
    path="/v1/accounts/{id}",
    handler="AccountController.getAccount",
    file="src/main/java/.../AccountController.java",
    line=42,
    request_body_type="CreateAccountRequest",
    response_type="AccountResponse",
    framework="spring"
)
```

### Framework route detection strategies

| Framework | Route detection strategy |
|---|---|
| Spring Boot | `@GetMapping`, `@PostMapping`, `@RequestMapping(method=...)` via javalang AST |
| FastAPI | `@router.get()`, `@app.post()` decorators via Python ast module |
| Django REST | `ViewSet`, `@action`, `router.register()` via Python ast module |
| Express | `app.get()`, `router.post()` via Babel AST (Node.js subprocess) |
| NestJS | `@Controller` + `@Get`/`@Post` decorators via ts-morph or regex fallback |
| Gin / Echo | `router.GET()`, `e.POST()` via go/ast compiled binary subprocess |

---

## Appendix B — Schema Inference Algorithm

```
resolve_type(type_name):
  1. Unwrap outer generic wrapper  (List<T> → resolve T as array items)
  2. Handle array / map containers recursively
  3. Check primitive map           (String → {"type": "string"})
  4. Cycle detection               (if name in visiting_set → return $ref)
  5. Check schema registry cache
  6. Locate source file (_find_type_file)
  7. Extract fields    (_extract_fields)
  8. Store in registry and return SchemaResult
```

### Cycle detection

Prevents infinite recursion on bidirectional relationships, self-referencing types,
and recursive DTOs:

```python
if name in self._visiting:
    return SchemaResult(
        json_schema={"$ref": f"#/components/schemas/{name}"},
        confidence=Confidence.HIGH
    )
```

---

## Appendix C — Confidence Scoring

Confidence is computed per schema and propagates upward through nested types:

| Condition | Confidence |
|---|---|
| Full AST resolution of all fields | HIGH |
| Missing nested type; one or more fields empty | MEDIUM |
| Regex fallback used for field extraction | LOW |
| Source file not found in repo | MANUAL |

If a nested type is MANUAL, the parent schema is at minimum MEDIUM.
Confidence is surfaced in the published spec via `x-confidence` extension fields.

---

## Appendix D — Subprocess Bridge

**TypeScript bridge:**
```
Python process                       Node.js (ts-morph)
─────────────────                    ───────────────────
subprocess.run(                      reads .ts source
  ["node", "ts_schema.js",           parses AST via tsc
   "path/to/dto.ts",         →       extracts interface/class fields
   "CreateAccountRequest"]           writes JSON to stdout
)                                          │
result = json.loads(stdout)    ←───────────┘
```

**Go bridge:**
```
Python process                       Compiled Go binary
─────────────────                    ──────────────────
subprocess.run(                      reads .go source
  ["go_schema_tool",                 parses struct via go/ast
   "path/to/models.go",     →        resolves struct tags
   "CreateOrderRequest"]             writes JSON to stdout
)                                          │
result = json.loads(stdout)    ←───────────┘
```

Timeout: 10 seconds. Failure → MANUAL confidence (never a silent wrong schema).

---

## Appendix E — Batch Architecture

```
ProcessPoolExecutor (16 workers)
    for each CSV row:
        git clone --depth 1 {repo_url}     (~5s per repo)
        inject .spec-engine.yaml if needed
        run spec-engine generate            (~8–20s per repo)
        write log to logs/{api_name}.log
        cleanup tempfile.TemporaryDirectory
        write result row to batch_report.csv
```

Peak memory: ~300MB per large Spring Boot repo.
16 workers safe on a 32GB runner.
200 repos estimated batch time: under 3 hours.

---

## Appendix F — Explorer Catalog Integration

**Publish logic:**
1. Parse `info.title` from generated spec
2. `GET /apis?name={title}` — check if entry exists
3. If exists → `PUT /apis/{id}` with updated spec
4. If not → `POST /apis` to create new entry

**Retry policy:** 3 attempts with exponential backoff (2s, 4s, 8s).
If publish fails on `main` branch push, pipeline fails with exit code 1
and spec artifact is saved locally for manual re-publish.

---

## Appendix G — Validation Toolchain

| Stage | Tool | What it checks |
|---|---|---|
| 1 | Redocly lint | OpenAPI 3.1 structural validity |
| 2 | Spectral (org ruleset) | Custom org governance rules |
| 3 | Custom validator | `x-owner`, `x-gateway`, `x-lifecycle` presence |

Example enforced metadata:

```yaml
info:
  x-owner: payments-team
  x-gateway: kong-prod
  x-lifecycle: production
```

Validation failure blocks publish on `main`. Pull requests get a non-blocking
warning in the CI summary.

---

## Appendix H — Future Enhancements (Phase 3+)

| Enhancement | Value | Effort |
|---|---|---|
| Shared library type resolution (external repo deps) | Eliminates most MANUAL cases | High |
| OpenAPI versioning per commit | Full spec history in catalog | Medium |
| AI-assisted description enrichment | Richer human-readable summaries | Low |
| Drift detection dashboard UI | Leadership visibility into staleness | Medium |
| Metrics export (Prometheus/Grafana) | Operational observability | Low |
| `--subdir` CLI flag for monorepos | Direct invocation without CSV | Low |

---

*Document version: March 2026 — Engineering review draft*
