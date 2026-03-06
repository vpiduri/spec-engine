# spec-engine — Investment Proposal & Project Estimates

> **Budget ask: $500,000 | Timeline: 6 months | Team: 6 people**
>
> This document provides the justification, detailed estimates, delivery timeline,
> and return-on-investment analysis for building spec-engine from scratch and
> deploying it across the full API inventory.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Budget Breakdown](#2-budget-breakdown)
3. [Team & Roles](#3-team--roles)
4. [6-Month Delivery Plan](#4-6-month-delivery-plan)
5. [Work Breakdown by Engineer](#5-work-breakdown-by-engineer)
6. [What Is Delivered by Month 6](#6-what-is-delivered-by-month-6)
7. [Risk Register & Contingency](#7-risk-register--contingency)
8. [Return on Investment](#8-return-on-investment)
9. [Milestones & Decision Gates](#9-milestones--decision-gates)
10. [Assumptions](#10-assumptions)
11. [Addressing Common Objections](#11-addressing-common-objections)
    - [11.1 Could Devin or an AI agent replace the team?](#111-could-devin-or-an-ai-coding-agent-replace-the-team)
    - [11.2 Why 4 engineers — can't 1 deliver this?](#112-why-4-engineers--cant-1-engineer-deliver-this)

---

## 1. Executive Summary

### The ask

**$500,000 over 6 months** to build, test, and deploy spec-engine: an automated OpenAPI 3.1
spec generator that covers the full API inventory across all supported programming languages
and frameworks, with zero changes required to any application code.

### What is being built

A production-grade pipeline that automatically:
1. Scans API source code (Java, Python, TypeScript, Go)
2. Infers request/response schemas from annotations and type definitions
3. Assembles a validated OpenAPI 3.1 spec per service
4. Publishes to the API Explorer catalog on every merge to main

### What is delivered by end of Month 6

| Deliverable | Status |
|---|---|
| Engine supporting 7 frameworks across 4 languages | Complete |
| Batch orchestrator — full API inventory loaded into catalog | Complete |
| 80%+ automated test coverage | Complete |
| Platform CI enforcement — Required Workflow / Jenkins integration | Launched (ongoing rollout) |
| Developer Guide + Stakeholder documentation | Complete |
| Runbooks and monitoring setup | Complete |

### Why $500K is the right investment

| Alternative | First-year cost | Ongoing/year | Scalable to 1,000+ APIs? |
|---|---|---|---|
| Manual spec writing (current state) | $560,000 | $560,000 | No |
| Commercial tool (Swagger Hub, Stoplight) | $40,000–$100,000 | $40,000–$100,000 | Partial |
| **spec-engine (this proposal)** | **$500,000** | **~$50,000** | **Yes** |

spec-engine pays for itself before the project completes.
Full ROI analysis is in [Section 8](#8-return-on-investment).

---

## 2. Budget Breakdown

All personnel costs reflect fully-loaded 6-month allocations
(base salary + benefits + employer taxes + overhead at market rates).

### Personnel

| Role | Specialisation | 6-Month Cost |
|---|---|---|
| Senior Engineer 1 — Core Engine Lead | Config, models, base framework, assembler, CLI, publisher | $80,000 |
| Senior Engineer 2 — Parsers: Java | Spring Boot scanner, Java AST inferrer, javalang integration | $80,000 |
| Senior Engineer 3 — Parsers: Python | FastAPI, Django/DRF, Python AST inferrer, Pydantic | $80,000 |
| Senior Engineer 4 — Parsers: Go/TS + CI | Express, NestJS, TypeScript inferrer, Gin/Echo, Go binary, CI templates | $80,000 |
| Program Manager (Full-Time) | Delivery, coordination, stakeholder comms, risk tracking | $70,000 |
| Platform Engineer | Batch tooling, runner images, Required Workflow, Jenkins Shared Library | $75,000 |
| **Personnel subtotal** | | **$465,000** |

### Non-Personnel

| Category | Item | Cost |
|---|---|---|
| Infrastructure | CI/CD compute (GitHub Actions), cloud storage, artifact hosting | $12,000 |
| Tooling & Licenses | Redocly, Spectral, monitoring dashboards | $8,000 |
| Training | Framework ramp-up, internal knowledge transfer sessions | $5,000 |
| Contingency | 10% reserve for scope changes, delays, or unexpected complexity | $10,000 |
| **Non-personnel subtotal** | | **$35,000** |

### Total

| | Amount |
|---|---|
| Personnel | $465,000 |
| Non-personnel | $35,000 |
| **Total investment** | **$500,000** |

---

## 3. Team & Roles

```
┌────────────────────────────────────────────────────────────────┐
│                    Program Manager (FT)                        │
│  Sprint ceremonies · Stakeholder updates · Risk tracking       │
│  Dependency management · Phase 1 CSV coordination             │
└────────────────────────┬───────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┬───────────────┐
         ▼               ▼               ▼               ▼
  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐
  │  Eng 1     │  │  Eng 2     │  │  Eng 3     │  │  Eng 4     │
  │ Core Engine│  │ Java Parser│  │Python Parse│  │ Go/TS + CI │
  │            │  │            │  │            │  │            │
  │ Config     │  │ Spring Boot│  │ FastAPI    │  │ Express    │
  │ Base infra │  │ Java AST   │  │ Django/DRF │  │ NestJS     │
  │ Assembler  │  │ inferrer   │  │ Pydantic   │  │ Gin/Echo   │
  │ CLI        │  │            │  │ inferrer   │  │ TS inferrer│
  │ Publisher  │  │            │  │            │  │ Go binary  │
  └────────────┘  └────────────┘  └────────────┘  └────────────┘
                                                         │
                                                  ┌──────▼──────┐
                                                  │  Platform   │
                                                  │  Engineer   │
                                                  │             │
                                                  │ batch_loader│
                                                  │ CI templates│
                                                  │ Runner imgs │
                                                  │ Req Workflow│
                                                  └─────────────┘
```

### Role responsibilities

| Role | Month 1–3 focus | Month 4–6 focus |
|---|---|---|
| **Eng 1 — Core Engine** | Architecture, models, Config, base scanner/inferrer, assembler skeleton | Assembler completion, publisher, CLI, test gap-close, Developer Guide |
| **Eng 2 — Java** | Spring Boot scanner (annotations, path vars, request body), Java AST inferrer (javalang) | Integration tests on real Spring repos, bug fixing, coverage |
| **Eng 3 — Python** | FastAPI scanner + global Pydantic pre-pass, Django/DRF scanner + nested routers, Python inferrer | Integration tests on real Django/FastAPI repos, pilot support |
| **Eng 4 — Go/TS/CI** | Express/NestJS scanner (Node.js subprocess + regex), TS inferrer, Gin/Echo, Go binary companion | Go inferrer regex fallback, integration tests, CI workflow templates |
| **PM** | Kickoff, framework inventory, sprint 0, stakeholder alignment | Pilot coordination, Phase 1 CSV validation, PE engagement tracking, comms |
| **Platform Engineer** | Dev environment, spec-engine CI, batch_loader.py | Runner images, set_repo_variables.sh, Required Workflow / Jenkins Shared Library, Phase 2 launch |

### Why 4 engineers (not 2)

With 2 engineers, the same project takes **12–14 months** — the scanner and inferrer work
for each language stack is largely independent and parallelises cleanly.
Adding engineers 2 and 3 (Java + Python specialists) removes the biggest bottleneck:
Spring Boot and FastAPI together represent ~60–70% of the typical enterprise API inventory.
Engineer 4 covers the remaining Go and TypeScript stacks concurrently.

The coordination overhead of 4 engineers is manageable because the engine is designed with
clear interfaces: each scanner produces `List[RouteInfo]` and each inferrer consumes type
names and produces `SchemaResult`. Engineers can develop and test their components in isolation.

---

## 4. 6-Month Delivery Plan

### Sprint cadence

- 2-week sprints (13 sprints total)
- Sprint ceremonies: planning (1h), daily standup (15m), retrospective (45m)
- PM owns ceremony facilitation and stakeholder status updates
- Every sprint ends with a working, runnable build

---

### Month 1 — Foundation (Weeks 1–4)

**Goal:** Core infrastructure running; first two scanners functional end-to-end.

| Week | Eng 1 | Eng 2 | Eng 3 | Eng 4 | PE | PM |
|---|---|---|---|---|---|---|
| 1 | Architecture, ADRs, framework inventory spike | Spring annotation survey, javalang spike | FastAPI/DRF annotation survey | Node.js subprocess spike, Go AST spike | Dev environment, GitHub Actions CI for spec-engine | Kickoff, stakeholder alignment, pilot repo nomination |
| 2–3 | Models, Config (YAML + layering), BaseScanner, BaseInferrer + cycle detection | Spring Boot scanner: `@RestController`, `@GetMapping`, path vars | FastAPI scanner + global BaseModel pre-pass | Express scanner + express_ast.js companion | batch_loader.py skeleton, CSV format spec | Sprint ceremonies, ADR sign-off, framework inventory report |
| 4 | Assembler skeleton (operationId, x- fields, $ref structure) | Java AST inferrer start (javalang field traversal) | Django scanner: URL routing two-pass AST | NestJS scanner: Python regex + Node.js delegation | CI workflow template skeleton | Risk register update, Month 1 progress report to leadership |

**Month 1 exit criteria:** `spec-engine generate` works end-to-end for at least one Spring Boot repo and one FastAPI repo. Unit tests running in CI with >50% coverage on completed modules.

---

### Month 2 — Full Scanner Coverage (Weeks 5–8)

**Goal:** All 7 framework scanners complete and unit-tested.

| Week | Eng 1 | Eng 2 | Eng 3 | Eng 4 | PE | PM |
|---|---|---|---|---|---|---|
| 5 | Assembler: paths object, error responses, deduplication | Java inferrer: Jackson annotations, Bean Validation | Django: mixin ViewSets, nested routers | Go binary companion (`go_schema_tool`) build | batch_loader.py: clone, process_row, report writers | Sprint planning, dependency tracking |
| 6 | Assembler: schema components, ruamel.yaml serialisation | Java inferrer: generic types, `@Valid` recursion | DRF nested routers (NestedSimpleRouter pre-pass) | Gin/Echo scanner: route groups, path normalisation | set_repo_variables.sh, validate_all_specs.sh | Mid-month stakeholder update |
| 7 | Assembler: confidence rollup, MANUAL block logic | Java inferrer complete; Spring unit tests (~50 tests) | Python inferrer: Pydantic v1/v2, dataclasses, TypedDict | TypeScript inferrer: ts-morph subprocess | CI workflow templates (GitHub + Jenkins) | Phase 1 CSV template shared with API Governance |
| 8 | Validator: Spectral + Redocly integration, exit codes | Java unit tests complete | Python unit tests complete (~70 tests) | Go inferrer: struct tags, nullable pointers, regex fallback; TS unit tests | PE engages Platform Engineering team (Approach 2 kickoff) | Sprint retro, risk review, Phase 2 engagement letter |

**Month 2 exit criteria:** All scanners and inferrers unit-tested. Full pipeline runnable on synthetic repos. 70%+ coverage on scanner modules.

---

### Month 3 — Integration Testing & Hardening (Weeks 9–12)

**Goal:** Engine validated on real (internal) repos. 80%+ test coverage achieved.

| Week | Eng 1 | Eng 2 | Eng 3 | Eng 4 | PE | PM |
|---|---|---|---|---|---|---|
| 9 | Publisher: POST/PUT to Explorer catalog, dry-run | Integration test: 3 real Spring Boot repos | Integration test: 3 real FastAPI repos | Integration test: 2 real NestJS/Express repos | Runner image setup with Python + Node.js (PE-facing) | Pilot repo selection (10–15 repos, 2–3 per framework) |
| 10 | CLI: all subcommands polished, `--framework` flag, `--prefer-file` | Bug fixes from Spring repo testing | Bug fixes from Python repo testing | Integration test: 2 real Gin/Go repos + bug fixes | Required Workflow design review with PE team | Phase 1 CSV collection from API Governance |
| 11 | `_rank_candidates()`, conflict resolution, test gap-close | Spring test suite complete; ~80% coverage on Java path | Python test suite complete; ~80% coverage on Python path | Go + TS test suite complete; ~80% coverage | PE: org secret creation, pilot Required Workflow configuration | CSV validation run — identify stale URLs, missing framework |
| 12 | End-to-end integration test: `generate` pipeline on 5 diverse repos | Code review pass, PR reviews | Code review pass, PR reviews | Code review pass, PR reviews | PE: test Required Workflow on 2 internal pilot repos | Month 3 progress report; demo prep for leadership |

**Month 3 exit criteria:** 80%+ overall test coverage (365+ tests). End-to-end pipeline green on 5 real repos across different frameworks. Publisher talking to Explorer catalog (staging).

---

### Month 4 — Pilot & Documentation (Weeks 13–16)

**Goal:** 10–15 pilot repos generating specs. First stakeholder demo. Docs complete.

| Week | Eng 1 | Eng 2 | Eng 3 | Eng 4 | PE | PM |
|---|---|---|---|---|---|---|
| 13 | Developer Guide (architecture, extending, testing, batch) | Pilot: Spring Boot repos — review generated specs manually | Pilot: FastAPI + Django repos — review generated specs | Pilot: Go + NestJS repos — review generated specs | PE: Required Workflow on 5 pilot repos; monitor success rate | Pilot coordination, issue triage log |
| 14 | Bug fixes from pilot — assembler, confidence levels | Fix critical Spring scanner issues from pilot | Fix critical Python scanner issues from pilot | Fix critical Go/TS issues from pilot; CI template refinements | Batch run on pilot repos: `batch_loader.py --dry-run` | Leadership demo #1: pilot results, confidence breakdown |
| 15 | Stakeholder Overview document | Cross-framework issue review + regression tests | Regression tests after fixes | Regression tests after fixes | PE: `set_repo_variables.sh` on pilot repos | Phase 1 CSV finalized (all inventory rows validated) |
| 16 | Runbooks: publisher failure, token rotation, MANUAL triage | Documentation review pass | Documentation review pass | Documentation review pass | PE: Jenkins Shared Library `specEngine()` step | Month 4 progress report; go/no-go for Phase 1 |

**Month 4 exit criteria:** 10–15 pilot repos producing specs in Explorer catalog (staging). 90%+ pilot success rate. All documentation complete. Leadership demo delivered.

---

### Month 5 — Phase 1: Full CSV Batch Load (Weeks 17–20)

**Goal:** Full API inventory published to Explorer catalog (production).

| Week | Eng 1 | Eng 2 | Eng 3 | Eng 4 | PE | PM |
|---|---|---|---|---|---|---|
| 17 | Final credential setup: GIT_TOKEN, EXPLORER_API_TOKEN production | Batch run support: Java-framework failures | Batch run support: Python-framework failures | Batch run support: Go/TS failures | Full batch run: `batch_loader.py --workers 16 --dry-run` | Stakeholder notification: batch starting |
| 18 | `batch_report.csv` triage: classify failure types | Fix engine bugs from batch failures (Java) | Fix engine bugs from batch failures (Python) | Fix engine bugs from batch failures (Go/TS) | Full batch run (production): `--publish` | Triage report to leadership: how many published, how many failed, why |
| 19 | `--retry-failed` re-run on fixed repos | MANUAL confidence triage: Java services | MANUAL confidence triage: Python services | MANUAL confidence triage: TS/Go services | PE: Required Workflow rollout to `api-service` tagged repos | Phase 2 status update: PE rollout plan |
| 20 | Catalog coverage dashboard | Final regression pass | Final regression pass | Final regression pass | PE: Monitor Required Workflow success rate | Phase 1 complete report: % published, confidence breakdown, MANUAL backlog |

**Month 5 exit criteria:** ≥90% of API inventory published to Explorer catalog. `batch_report.csv` shows <5% hard failures. Required Workflow running on 20+ repos.

---

### Month 6 — Phase 2 Launch & Handover (Weeks 21–26)

**Goal:** Platform CI enforcement live. Project handed to run-and-maintain mode.

| Week | Eng 1 | Eng 2 | Eng 3 | Eng 4 | PE | PM |
|---|---|---|---|---|---|---|
| 21–22 | Monitoring setup: dashboard, alert rules for publish failures | Handover: Java scanner extension guide | Handover: Python scanner extension guide | Handover: Go/TS scanner extension guide | PE: Complete org-wide Required Workflow rollout; monitor | Leadership demo #2: full catalog coverage, CI live |
| 23–24 | Address MANUAL-confidence backlog cases (top 10) | Bug fixing: production issues week 1 | Bug fixing: production issues week 1 | Bug fixing: production issues week 1 | PE: Jenkins Shared Library in production | CSV ownership handover to API Governance team |
| 25 | Final documentation updates based on production learnings | Knowledge transfer sessions with future maintainers | Knowledge transfer sessions | Knowledge transfer sessions | PE: runbook for Required Workflow issues | Project closure report, lessons learned |
| 26 | Final code review + release tag `v1.0.0` | — | — | — | PE: steady state handover | Executive presentation: delivered scope, ROI realised, Phase 3 roadmap |

**Month 6 exit criteria:** Required Workflow running on all `api-service`-tagged repos. Project formally closed. Maintenance responsibility transferred. `v1.0.0` release tagged.

---

## 5. Work Breakdown by Engineer

### Eng 1 — Core Engine Lead

The backbone of the system — every other component depends on these.

| Component | Weeks | Complexity |
|---|---|---|
| Data models: `RouteInfo`, `SchemaResult`, `ParamInfo`, `Confidence` | 1 | Low |
| `Config` system: YAML loading, CLI override layering, `framework`/`prefer_file` fields | 1 | Medium |
| `BaseScanner` + `_iter_files()` with SKIP_DIRS | 0.5 | Low |
| `BaseInferrer` with cycle detection, `_rank_candidates()` | 1 | Medium |
| CLI (Click): generate, scan, schema, assemble, validate, publish subcommands | 1 | Low |
| `Assembler`: operationId generation, schema $ref building, error responses, x- fields, ruamel.yaml | 3 | High |
| `Validator`: Spectral + Redocly subprocess integration | 1 | Low |
| `Publisher`: POST/PUT to Explorer catalog, title dedup, dry-run | 1.5 | Medium |
| Unit tests: models, config, assembler, publisher (~90 tests) | 2 | Medium |
| Developer Guide | 1.5 | Low |
| Stakeholder Overview + runbooks | 1 | Low |

**Total: ~15 weeks of work delivered in 6 months (includes reviews and integration support)**

---

### Eng 2 — Java/Spring Boot

Spring Boot is the highest-complexity scanner due to annotation semantics.

| Component | Weeks | Key difficulty |
|---|---|---|
| `SpringScanner`: `@RestController`, `@Controller`, `@RequestMapping`, `@GetMapping` etc. | 2 | Class-level vs method-level path join |
| Path variable extraction, `produces/consumes`, compound annotations | 1 | Nested annotation arrays |
| `@RequestBody`, `@RequestParam`, `@PathVariable` extraction | 1.5 | `required`, `defaultValue`, annotation element parsing; javalang `element` vs `elements` list bug |
| `JavaASTInferrer`: field traversal, generic type resolution | 2 | Type hierarchy, `List<T>`, `Optional<T>` |
| Jackson: `@JsonProperty`, `@JsonIgnore`, `@JsonAlias` | 1 | |
| Bean Validation: `@NotNull`, `@Size`, `@Min`, `@Max` → JSON Schema constraints | 1 | |
| Unit tests: ~50 tests; integration tests: 5 real Spring repos | 2 | |

**Total: ~10.5 weeks**

---

### Eng 3 — Python Frameworks

Python stack covers two major frameworks with distinct URL routing models.

| Component | Weeks | Key difficulty |
|---|---|---|
| `FastAPIScanner`: decorator detection, path params, `Depends()` filtering | 1 | |
| FastAPI global BaseModel pre-pass (models imported from other files) | 1 | Repo-wide scan before per-file analysis |
| `DjangoScanner`: two-pass URL routing AST + views resolution | 1.5 | `include()` chains, namespace handling |
| DRF: `router.register()`, `ModelViewSet`, `ReadOnlyModelViewSet`, mixin combos | 1.5 | `_MIXIN_ROUTE_MAP`, `_compute_allowed_actions()` |
| DRF nested routers: `NestedSimpleRouter` pre-pass, compound path rewrite | 1 | AST pre-pass for router var classification |
| `PythonASTInferrer`: Pydantic v1/v2 fields, dataclasses, TypedDict | 2 | `Field(...)` parsing, `model_config` in v2 |
| Unit tests: ~70 tests; integration tests: 5 real Python repos | 2 | |

**Total: ~10 weeks**

---

### Eng 4 — Go/TypeScript/CI

Most technologically diverse role — requires Go, Node.js, and Python expertise.

| Component | Weeks | Key difficulty |
|---|---|---|
| `express_ast.js` Node.js companion (AST walker for Express routes) | 1.5 | `app.get()`, `router.use()` chain traversal |
| `ExpressScanner`: subprocess management, JSON output, timeout handling | 1 | |
| `NestJSScanner`: `_node_available()` probe, delegate to Express, Python regex fallback | 1 | `dataclasses.replace()` for framework relabelling |
| `go_schema_tool` Go binary companion: Go AST struct walker | 2 | Separate Go module, struct tag parsing, binary caching |
| `GinScanner` + `EchoScanner`: route groups, path normalisation | 1.5 | `engine.Group()` nesting |
| `GoASTInferrer`: binary subprocess, regex fallback, struct tags, nullable pointer, slice types | 1.5 | `validate:"required,min=1,max=100"` parsing |
| `TypeScriptASTInferrer`: ts-morph subprocess, interface/class/type alias extraction | 1 | |
| CI workflow templates: GitHub Actions reusable workflow, Required Workflow YAML, Jenkins groovy step | 1 | |
| Unit tests: ~80 tests; integration tests: 4 real Go/TS repos | 2 | |

**Total: ~12.5 weeks**

---

### Platform Engineer

Focused on operationalisation: batch tooling, CI infrastructure, Platform Engineering liaison.

| Component | Weeks |
|---|---|
| Dev environment setup, spec-engine CI (GitHub Actions, pytest, coverage) | 1 |
| `batch_loader.py`: CSV loader, clone, process, parallel executor, report writers | 2.5 |
| `set_repo_variables.sh`, `validate_all_specs.sh` | 0.5 |
| GitHub Actions workflow templates (reusable + Required Workflow + per-repo) | 1 |
| Jenkins Shared Library `specEngine()` groovy step | 1 |
| Platform Engineering engagement: runner image update, org secret, Required Workflow policy | 3 |
| Phase 1 batch execution and monitoring | 2 |
| Phase 2 rollout monitoring and incident response | 2 |
| Runbooks: token rotation, Required Workflow failures, batch re-run SOP | 1 |

**Total: ~14 weeks**

---

## 6. What Is Delivered by Month 6

| # | Deliverable | Owner | Done by |
|---|---|---|---|
| 1 | Engine: all 6 framework scanners (Spring, FastAPI, Django, Express, NestJS, Gin/Echo) | Eng 1–4 | Month 3 |
| 2 | Engine: all 4 schema inferrers (Java, Python, TypeScript, Go) | Eng 1–4 | Month 3 |
| 3 | Assembler: full OpenAPI 3.1 spec generation with x- extensions | Eng 1 | Month 2 |
| 4 | Validator: Spectral + Redocly integration | Eng 1 | Month 3 |
| 5 | Publisher: Explorer catalog POST/PUT with confidence gating | Eng 1 | Month 3 |
| 6 | CLI: all subcommands + `--framework` override + `--prefer-file` | Eng 1 | Month 3 |
| 7 | 80%+ automated test coverage (365+ tests) | All engineers | Month 3 |
| 8 | batch_loader.py: parallel CSV-driven batch orchestrator | PE | Month 2 |
| 9 | CI templates: GitHub Actions reusable workflow, Jenkins Shared Library | Eng 4 + PE | Month 3 |
| 10 | Platform Engineering engagement complete (runner images, secrets, Required Workflow) | PE | Month 5–6 |
| 11 | Pilot: 10–15 repos generating live specs in Explorer catalog | All | Month 4 |
| 12 | Phase 1: full API inventory published to Explorer catalog (≥90%) | PM + PE | Month 5 |
| 13 | Phase 2: Required Workflow / Jenkins step live on all `api-service` repos | PE | Month 6 |
| 14 | Developer Guide + Stakeholder Overview + runbooks | Eng 1 + PM | Month 4–5 |

---

## 7. Risk Register & Contingency

### Top 5 risks to the 6-month timeline

| Risk | Likelihood | Schedule impact | Mitigation |
|---|---|---|---|
| **Platform Engineering unavailable** — PE engagement is the #1 external dependency; if PE team is backlogged, Required Workflow rollout slips | High | +4–8 weeks (Phase 2 only; Phase 1 unaffected) | Start PE engagement in Month 2; Phase 1 CSV batch delivers value independently. Phase 2 slippage does not block the $500K deliverables. |
| **Framework version diversity** — Spring Boot 3.x annotation changes, FastAPI 0.110+ `model_config` syntax, DRF 3.15 differences | Medium | +2–3 weeks (absorbed in Month 3 hardening) | Month 3 integration tests on real repos surface these early; 1-week hardening buffer built in. |
| **Cross-repo type dependencies** — shared DTO libraries not in scanned repo; inferrer returns MANUAL confidence | Medium | None to schedule; increases MANUAL backlog | Confidence model handles this gracefully; MANUAL cases flagged, not blocked. |
| **Explorer catalog API instability** — undocumented endpoint changes break publisher | Low | +1–2 weeks | Publisher logs all HTTP errors; catalog team contacted in Month 1 to agree on API stability SLA. |
| **Team ramp-up slower than expected** — engineers unfamiliar with javalang quirks, ts-morph, or Go AST | Low–Medium | +1–2 weeks | Technology spikes in Week 1 surface unknowns early; pairing between engineers during Month 2. |

### Contingency budget

The $10,000 contingency reserve (2% of $500K) covers:
- Additional compute costs if batch runs require more GitHub Actions minutes
- Emergency contractor help if one engineer is unavailable for >2 weeks
- Any tooling or licensing costs not anticipated at proposal time

> **Note:** The 10% contingency on non-personnel costs ($35K total non-personnel) provides
> meaningful buffer; personnel costs are fixed at salary allocation rates.

---

## 8. Return on Investment

### Cost of the status quo

Based on an inventory of 200 API services (typical enterprise scale):

| Activity | Calculation | Annual cost |
|---|---|---|
| **Initial spec authoring** — senior dev writes each spec manually | 200 APIs × 4 days × $700/day | $560,000 (one-time) |
| **Ongoing spec maintenance** — update spec when API changes | 200 APIs × 1 day/quarter × 4 quarters × $700/day | $560,000/year |
| **Consumer onboarding friction** — teams spend extra time finding/requesting docs | 200 APIs × avg 2 days/year × $700/day | $280,000/year |
| **Integration incidents from stale docs** — debugging time from outdated specs | Conservative: 20 incidents/year × 2 days each × $700/day | $28,000/year |
| **Total first-year cost (manual approach)** | | **$1,428,000** |

### Cost with spec-engine

| Activity | Cost |
|---|---|
| Build spec-engine (this proposal) | $500,000 (one-time) |
| Ongoing maintenance — 0.25 FTE + infrastructure | ~$50,000/year |
| **Total first-year cost (spec-engine)** | **$550,000** |

### ROI summary

| Metric | Value |
|---|---|
| First-year savings vs. manual | $1,428,000 − $550,000 = **$878,000** |
| Payback period | **< 5 months** (before project completes) |
| 3-year net savings | $878,000 + 2 × ($1,378,000 − $50,000) = **~$3.5M** |
| Break-even point | Mid-project (Month 4–5, once batch load runs) |

> These numbers are conservative. They do not count: governance/audit risk reduction,
> faster consumer team onboarding, or the compounding value of a live,
> accurate catalog for API discoverability.

### Scaling argument

The cost of manual spec authoring scales linearly with inventory size.
spec-engine's cost does **not**:

| Inventory size | Manual first-year cost | spec-engine year 1 | spec-engine year 2+ |
|---|---|---|---|
| 100 APIs | $700,000 | $500,000 | $50,000 |
| 200 APIs | $1,400,000 | $500,000 | $50,000 |
| 500 APIs | $3,500,000 | $500,000 | $70,000 |
| 1,000 APIs | $7,000,000 | $500,000 | $90,000 |

---

## 9. Milestones & Decision Gates

| # | Milestone | Target date | Go/no-go criteria | Decision owner |
|---|---|---|---|---|
| **M1** | Architecture approved | End of Week 1 | ADRs reviewed; framework inventory complete; team aligned | SRE Frameworks Lead |
| **M2** | First end-to-end pipeline | End of Month 1 | `spec-engine generate` works for Spring Boot + FastAPI; CI passing | Engineering Lead |
| **M3** | All scanners complete | End of Month 2 | All 7 framework scanners unit-tested; 70%+ coverage | Engineering Lead |
| **M4** | Engine hardened on real repos | End of Month 3 | 80%+ test coverage; 5 real repos produce valid specs; Publisher talking to catalog (staging) | Engineering Lead |
| **M5** | Pilot complete | End of Month 4 | 10–15 repos live in Explorer catalog; ≥90% pilot success rate | **Leadership go/no-go for Phase 1** |
| **M6** | Phase 1 complete | End of Month 5 | ≥90% of inventory published; `batch_report.csv` < 5% hard failures | **Leadership + API Governance sign-off** |
| **M7** | Phase 2 launched | End of Month 6 | Required Workflow running on all `api-service`-tagged repos; project closed | **Platform Engineering + SRE Frameworks** |
| **M8** | Steady state | Month 9 (post-project) | Zero open P1 issues; maintenance SOP in place; 0.25 FTE ongoing | SRE Frameworks Team |

### What happens if a milestone slips

| Milestone at risk | Impact | Response |
|---|---|---|
| M3 (all scanners) slips 2 weeks | Phase 1 batch delayed by 2 weeks | PM activates contingency; Eng 1 assists slowest scanner |
| M5 (pilot) slips 2 weeks | Phase 1 delayed by 2 weeks; Phase 2 start shifts | Acceptable; leadership informed; budget unaffected |
| M7 (Phase 2) slips 4–8 weeks | Required Workflow rollout extends into Month 7–8 | Phase 1 value already delivered; PE dependency managed separately |

---

## 10. Assumptions

| # | Assumption | If false → impact |
|---|---|---|
| A1 | 4 senior engineers are fully dedicated (no split responsibilities) | Each 20% allocation drag adds ~1 month to timeline |
| A2 | Platform Engineering engages in Month 2 | Phase 2 slips proportionally; Phase 1 unaffected |
| A3 | Explorer catalog API is documented and stable | Publisher rework adds 2–3 weeks |
| A4 | API inventory CSV exists and is reasonably accurate (>80% valid rows) | Additional 2–3 weeks for CSV remediation |
| A5 | Target repos use standard framework annotations (no custom forks or unusual patterns in >30% of repos) | Additional hardening cycle in Month 4; pilot may need extending |
| A6 | Python 3.11+ and Node.js 20 can be installed on CI runners | PE scope increases by 1–2 weeks for custom runner image build |
| A7 | No major framework version changes released during the 6-month build period that invalidate scanner patterns | Unlikely; if it occurs, 1-week hotfix |

---

## 11. Addressing Common Objections

This section directly responds to two objections that typically arise during
budget review for projects of this type:

1. *"Could we use Devin or an AI coding agent instead of a full team?"*
2. *"This seems straightforward — why can't 1 engineer deliver it?"*

Both are reasonable questions that deserve honest, data-driven answers.

---

### 11.1 Could Devin or an AI coding agent replace the team?

**No. The bottleneck of this project is not writing code.**

Devin and similar autonomous AI agents are valuable for isolated, well-specified
software tasks. This project does not fit that profile. Here is a breakdown of
where time is actually spent — and whether AI can substitute for it.

#### Where the 46 engineer-weeks actually go

```
Activity category                  Weeks    AI-substitutable?
────────────────────────────────── ─────    ─────────────────
Writing initial scanner/inferrer     12     Partially — AI accelerates first-pass code
  code for 4 language ecosystems           but can't test against real internal repos

Integration testing on real repos     8     No — requires access to internal GitHub org
  (30+ real repos, 6 frameworks)           and knowledge of internal annotation patterns

Debugging real-repo edge cases        7     No — requires language-ecosystem expertise
  discovered during testing                and access to the failing repos

Platform Engineering engagement       4     No — requires human coordination, meetings,
  (runner images, Required Workflow)       architecture review, org policy setup

Assembler, validator, publisher       4     Partially — standard HTTP/YAML work;
  integration with Explorer catalog        but requires access to internal catalog API

Batch tooling, CSV validation,        3     Partially — scripting work; AI useful
  production batch run coordination

Documentation, runbooks               4     Partially — AI can draft; humans must
                                           validate accuracy against real behaviour

Code review, cross-team QA,           4     No — requires human judgment and context
  knowledge transfer
                                    ───
Total                                46
```

**Conclusion:** roughly 30–35% of the work is code generation where AI assistance
meaningfully accelerates delivery. The remaining 65–70% is integration, judgment,
and coordination work that requires humans with enterprise access.

#### The security argument

The entire justification for building spec-engine in-house — rather than
using a SaaS documentation tool — is that **source code never leaves the
enterprise environment.** Using an autonomous AI agent to build this tool
requires granting that agent read access to internal source repositories
for testing. This is a larger and more sensitive access grant than any
commercial documentation tool requires. It directly contradicts the
privacy rationale that makes spec-engine preferable to commercial
alternatives in the first place.

#### The cost argument

Devin and comparable agents charge per task-hour. This project involves
dozens of iterative integration test cycles, each revealing new edge
cases requiring research and design decisions. The $500K proposal has
a fixed budget and a defined scope. AI agent costs for equivalent
iterative, exploratory work are unpredictable and in comparable
industry projects have typically **exceeded** the cost of an equivalent
human team for the same timeline.

#### The right role for AI tools

AI coding assistants (Copilot, Claude Code) ARE used by the engineers
on this team, running locally, against internal repos they already have
access to. This is not an either-or question. The proposal assumes AI
assistance throughout — it is part of why 4 engineers can deliver
in 6 months what historically took 12+. AI accelerates individual
engineers; it does not replace the team for a project of this
integration and coordination complexity.

---

### 11.2 Why 4 engineers — can't 1 engineer deliver this?

**Not in 6 months. The math doesn't work, and the skill set doesn't consolidate.**

This is the most important objection to address directly, so the
analysis below is thorough.

#### The sequential timeline for 1 engineer

Every component in the engine has a dependency structure.
Core infrastructure must exist before scanners can be built.
The assembler cannot be fully tested until at least one scanner works.
Integration testing cannot start until scanners produce output.

Given those constraints, here is the realistic sequential timeline
for a single senior engineer — one who is strong in Python but also
capable in Java, Go, and TypeScript:

```
Phase                                    Weeks   Notes
──────────────────────────────────────── ─────   ──────────────────────────────────────
Architecture, discovery, tech spikes       3     Same as 4-engineer plan
Core infrastructure                        3     Same; not parallelizable
Spring Boot scanner                        3     Eng 2's 3-week workstream
Java AST inferrer                          2.5   Eng 2's remaining work
FastAPI scanner + Pydantic inferrer        3     Eng 3's workstream
Django/DRF scanner + nested routers        3     Eng 3's remaining work
Express + NestJS scanners                  2.5   Half of Eng 4's workstream
TypeScript inferrer                        1.5   Eng 4
Go binary companion + Gin/Echo scanner     3.5   Eng 4 — Go requires separate module
Go AST inferrer + regex fallback           2     Eng 4
Assembler (full)                           2.5   Eng 1's later workstream
Validator + Publisher                      2     Eng 1
Test suite completion                      2     Was split across all 4; now serial
Batch tooling                              2     PE's workstream
Documentation                             2     Eng 1
──────────────────────────────────────── ─────
Engine total                              37.5 weeks  ≈ 9.4 months

Pilot (cannot start until engine done)    3
Phase 1 CSV batch                         5
Phase 2 PE engagement (still external)    8+
──────────────────────────────────────── ─────
Total to full production                  53+ weeks   ≈ 13 months
```

**With 1 engineer, the project delivers in 13 months, not 6.**
The 6-month target requires parallel execution of independent
workstreams. There is no other way to achieve it.

#### The skill set does not consolidate in one person

The four language ecosystems in this project each require deep,
current expertise:

| Ecosystem | Required knowledge | Ramp time for non-specialist |
|---|---|---|
| Java / Spring Boot | `javalang` internals, annotation element parsing, Java type system, generic resolution | 3–5 weeks to reach production-quality output |
| Python / FastAPI / DRF | `ast` module, Pydantic v1 vs v2 differences, DRF router internals, nested router AST pre-pass | 1–2 weeks (if Python-native) |
| Go | `go/ast` package, struct tag parsing, Go module system, cross-compiling a companion binary | 4–6 weeks for a Python engineer |
| TypeScript / Node.js | `ts-morph` API, TypeScript compiler types, Node.js subprocess management | 3–4 weeks |

A single engineer who is strong in one ecosystem will spend 10–18 weeks
ramping up on the other three — time that appears nowhere in an optimistic
estimate but is always paid in the schedule.

#### What gets cut when the team shrinks

If the project is forced to 1 engineer + 1 PM, something must give.
The realistic trade-offs are:

| Option | What you give up | Consequence |
|---|---|---|
| **Drop 2 language stacks** (e.g., Go + TypeScript) | Gin, Echo, NestJS, Express not covered | ~30–40% of API inventory not covered in Phase 1 |
| **Keep all stacks, extend timeline to 12+ months** | 6-month target missed | Platform Engineering engagement delayed; business value delayed by 6 months |
| **Use low-quality regex instead of AST** for some stacks | Confidence falls to MEDIUM/MANUAL for Go and TS services | Catalog is incomplete; trust deficit with API teams |
| **Skip integration testing** | Edge cases hit production | First batch run has 40–60% failure rate; MANUAL backlog overwhelms teams |

None of these trade-offs are acceptable for a project meant to establish
the API catalog as the authoritative source of truth for the organization.

#### The staffing risk argument

With 1 engineer on a 13-month project:
- If the engineer is unavailable for 4 weeks (illness, leave, departure),
  the project slips by 4 weeks with no recovery path
- No peer review means bugs in the scanner reach production and undermine
  trust in the catalog
- All institutional knowledge about annotation edge cases lives in one person
- The Platform Engineering engagement has no technical partner when the
  engineer is debugging scanner issues

With 4 engineers:
- Any one engineer's 4-week absence is absorbed by the team; schedule
  impact is 0–1 weeks
- Every scanner and inferrer is reviewed by at least one other engineer
- Knowledge is distributed; the project survives personnel changes

#### The "simple" framing

The pipeline does look simple at the conceptual level:
*read code → extract routes → write YAML.* This is accurate.

What is not visible from that summary:
- 365 tests covering edge cases across 4 languages and 7 frameworks
- A separate Go binary codebase required for Go AST traversal
- A Node.js companion script for TypeScript inference
- Annotation-parsing bugs that only appear against real internal repos
- DRF mixin ViewSet filtering logic requiring 3 passes over the class hierarchy
- Cycle detection in the inferrer to handle recursive type definitions

These are not surprises or scope creep. They are the expected complexity of
building a multi-language static analysis tool. They were discovered and
resolved because the team has the time and expertise to handle them properly.
A single engineer on a compressed timeline would either skip them (producing
a low-quality tool) or spend 13 months solving them (missing the target).

#### Summary: 1 engineer vs 4 engineers

| Dimension | 1 Engineer + 1 PM | 4 Engineers + 1 PM + 1 PE |
|---|---|---|
| Timeline to full production | 13+ months | 6 months |
| Language stack coverage | Risk of dropping 1–2 stacks | All 4 stacks covered in parallel |
| Integration test quality | Limited (single perspective) | Peer-reviewed; real repo validated |
| Staffing risk | Single point of failure | Distributed; resilient |
| Knowledge retention | All in one person | Distributed across team |
| Platform Engineering capacity | Engineer splits time | Dedicated PE handles operationalisation |
| Budget | ~$155K (1 SE + 1 PM × 13mo) | $500K × 6mo |
| Value delivered at Month 6 | ~50% of engine, no deployment | Full engine, pilot, Phase 1 complete |
| Cost per month of delay | $840K/year opportunity cost forgone | Fully delivered on schedule |

The 1-engineer option costs less per month but delivers the same
final output 7 months later, foregoing **$490,000 in annual savings**
from the delayed catalog coverage (based on the ROI model in Section 8).
It is the more expensive option over any 18-month horizon.

---

*Document version: March 2026*
*Status: Investment proposal — ready for executive review and budget approval*
*Authors: SRE Frameworks Team*
