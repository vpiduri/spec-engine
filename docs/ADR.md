# spec-engine — Architecture Decision Record

| | |
|---|---|
| **Status** | Proposed |
| **Date** | March 2026 |
| **Authors** | SRE Frameworks Team |
| **Reviewers** | Engineering Team |
| **Related docs** | `DEVELOPER_GUIDE.md`, `STAKEHOLDER_OVERVIEW.md`, `PROJECT_ESTIMATES.md` |

> **Purpose of this document:** Engineering-level review of key architectural decisions,
> implementation approach, deployment strategy, budget, and 6-month execution plan.
> Each decision records what we chose, what we rejected, and why.

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [System Overview](#2-system-overview)
3. [ADR-001 — Analysis approach: AST over all alternatives](#adr-001--analysis-approach-ast-over-all-alternatives)
4. [ADR-002 — Multi-language strategy: native parsers + subprocess bridges](#adr-002--multi-language-strategy-native-parsers--subprocess-bridges)
5. [ADR-003 — Confidence-driven publish governance](#adr-003--confidence-driven-publish-governance)
6. [ADR-004 — Deployment: batch CSV load vs platform CI enforcement](#adr-004--deployment-batch-csv-load-vs-platform-ci-enforcement)
7. [ADR-005 — Existing spec reuse with quality gates](#adr-005--existing-spec-reuse-with-quality-gates)
8. [ADR-006 — Zero application code changes](#adr-006--zero-application-code-changes)
9. [ADR-007 — Why not use an AI coding agent (Devin) instead?](#adr-007--why-not-use-an-ai-coding-agent-devin-instead)
10. [Execution Plan — 6 months](#10-execution-plan--6-months)
11. [Budget — $500K](#11-budget--500k)
12. [Engineering FAQs](#12-engineering-faqs)

---

## 1. Problem Statement

85%+ of our API inventory has no entry in the Explorer catalog.
The cause is not intent — it is friction. Writing and maintaining an OpenAPI spec
manually requires developer time that is never prioritised over feature work.
The catalog falls behind; API consumers can't find contracts; onboarding takes weeks.

**Goal:** Automate spec generation for every API in the inventory, keep specs
fresh on every code change, and require zero changes to application code.

**Scope:** Java/Spring Boot, Python/FastAPI, Python/Django REST Framework,
TypeScript/NestJS, JavaScript/Express, Go/Gin, Go/Echo. ~200 API services.
Initial load via CSV batch. Ongoing freshness via CI pipeline enforcement.

---

## 2. System Overview

```
         Source Repository
               │
               ▼
  ┌─────────────────────────┐
  │  Stage 0 — Pre-flight   │  Detect existing committed spec
  │  (detector.py)          │  Fast-path / merge / skip
  └────────────┬────────────┘
               │ (if no fast-path)
               ▼
  ┌─────────────────────────┐
  │  Stage 1 — Scanner      │  Walk source files via AST
  │  (scanner/)             │  Extract: method, path, params, handler name
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

## ADR-001 — Analysis approach: AST over all alternatives

**Decision: Abstract Syntax Tree (AST) parsing. No runtime execution. No LLM.**

### What AST does

Parses source code into a structured tree that represents the grammar of the code,
the same way a compiler does before it runs anything.

```
@GetMapping("/v1/accounts/{id}")               Method Declaration
public Account getAccount(                  →    ├── annotation: GetMapping("/v1/accounts/{id}")
    @PathVariable UUID id) { ... }               ├── return type: Account
                                                 └── param: @PathVariable UUID id
```

spec-engine walks this tree to extract HTTP method, path, parameters, and return types
without starting the application or sending any network traffic.

### Options considered

| Option | How it works | Why rejected |
|---|---|---|
| **Runtime / reflection** | Start the app, intercept HTTP or call reflection APIs | Requires a running service, live database, and test data in CI. Impossible for most services. |
| **Regex on source** | Pattern-match annotation strings | Brittle. Breaks on multi-line annotations, comments inside strings, whitespace variation, generics, and nested annotations. Not production-quality. |
| **LLM inference** | Send code to an AI model, ask it to generate the spec | Non-deterministic — same code can produce different specs on different runs. Sends source code to an external service. $0.01–0.05 per file × 1,000 repos × ongoing = unbounded cost. |
| **Framework built-ins** (SpringDoc, FastAPI `/docs`) | Each framework generates its own spec at runtime | Requires the app to run. One tool per framework — not unified. Requires code changes (SpringDoc dependency). Cannot enforce org-wide x- metadata. |
| **AST parsing** ✅ | Parse source into tree; walk tree to extract facts | Deterministic. In-process. No execution. Same technique used by IntelliJ, VS Code, and all major compilers. |

### Consequences

- Need a language-specific parser per ecosystem (acceptable; listed in ADR-002)
- Dynamic routing (routes registered at runtime from config) is unresolvable by AST → handled via MANUAL confidence (ADR-003)
- Result is fully deterministic: same code always produces the same spec

---

## ADR-002 — Multi-language strategy: native parsers + subprocess bridges

**Decision: In-process parsers for Python and Java; subprocess JSON bridge for TypeScript and Go.**

### The problem

No single parsing library covers all four language ecosystems.
The best AST parser for each language lives in that language's own toolchain.

### What we use per language

| Language | Library | Runs where | Protocol |
|---|---|---|---|
| **Python** | `ast` (stdlib) | In-process (Python) | Direct API call |
| **Java** | `javalang` (pip) | In-process (Python) | Direct API call |
| **TypeScript** | `ts-morph` (npm) | Node.js subprocess | stdout JSON |
| **Go** | `go/ast` (stdlib) | Compiled Go binary subprocess | stdout JSON |

### Subprocess bridge pattern

For TypeScript and Go, spec-engine spawns a subprocess, passes a file path as
an argument, and reads JSON from stdout:

```
Python process                       Node.js / Go binary
─────────────────                    ───────────────────
subprocess.run(                      reads source file
  ["node", "ts_schema.js",           parses AST
   "path/to/dto.ts",         →       extracts fields
   "CreateAccountRequest"]           writes JSON to stdout
)                                          │
result = json.loads(stdout)    ←───────────┘
```

The subprocess has a 10-second timeout. If it fails or times out,
the inferrer falls back to regex (lower confidence) or returns MANUAL.

### Why not a single unified parser

Options like Tree-sitter cover multiple languages but do not understand
type systems, annotation semantics, or generic resolution in any language
at the depth needed for accurate schema inference. Language-native parsers
(ts-morph uses the TypeScript compiler itself; go/ast is the same parser
Go tools use) give correct results for the hard cases: generics, type aliases,
intersection types, struct tag variants.

### Fallback chain when dependencies are unavailable

```
TypeScript inferrer
  ts-morph available? → full AST inference (HIGH confidence)
  ts-morph missing?   → MANUAL confidence (no fallback; returns empty)

Go inferrer / scanner
  go binary compiled? → full AST inference (HIGH confidence)
  go binary missing?  → Python regex on .go files (MEDIUM confidence for simple structs)

NestJS scanner
  node available?     → delegates to Express scanner (full AST)
  node missing?       → Python regex on @Controller / @Get decorators (route paths only)
```

---

## ADR-003 — Confidence-driven publish governance

**Decision: Four confidence levels; HIGH and MEDIUM auto-publish; LOW and MANUAL block.**

### The problem

AST cannot resolve every type. A request body type defined in a shared library
repo (not present in the clone), or a route registered dynamically from a
database config, cannot be statically inferred. We must not silently publish
a wrong schema — but we also must not block an entire spec because one field
is unresolvable.

### Confidence model

| Level | Assigned when | Publish behaviour |
|---|---|---|
| `HIGH` | All fields fully resolved from type annotations | Auto-publish |
| `MEDIUM` | Partial resolution; some fields are `{}` or inferred heuristically | Publish + flag for review |
| `LOW` | Regex fallback used for at least one field; result uncertain | Blocked; human review required |
| `MANUAL` | Type completely unresolvable (dynamic, external library, reflection) | Blocked; human must author that section |

Confidence is per-schema, not per-spec. A spec with 40 HIGH routes and 2 MANUAL
routes publishes successfully — the MANUAL routes are annotated with
`x-confidence: manual` and included as stubs.

### Why not fail-fast (block publish if anything is MANUAL)

In an inventory of 200 services, some percentage will always have dynamic routing
or shared library types. Fail-fast means those services never get any catalog
entry, which is worse than a partial entry. The confidence field in the catalog
makes the limitation visible and actionable.

---

## ADR-004 — Deployment: batch CSV load vs platform CI enforcement

**Decision: Both, in parallel. They solve different problems.**

### The two problems

| Problem | Solution |
|---|---|
| 200 services exist today with no catalog entry | **Batch load** — run once against all repos from CSV |
| New code is merged tomorrow; spec goes stale | **Platform CI** — run on every push to main |

These are complementary, not competing.

### Approach A — CSV Batch Load

```
api_inventory.csv
  (api_name, team, gateway, repo_url, framework, ...)
        │
        ▼
batch_loader.py
  ├── git clone --depth 1 {repo_url}   (parallel, 16 workers)
  ├── spec-engine generate --repo .
  ├── logs to logs/{api_name}.log
  └── result to batch_report.csv
```

**Key implementation decisions:**
- `ProcessPoolExecutor` (not threads) — avoids Python GIL for CPU-bound AST work
- `--depth 1` shallow clone — reduces clone time from ~30s to ~5s for large repos
- Per-row `.spec-engine.yaml` injection for `exclude_paths` from CSV column
- `--retry-failed` mode re-runs only rows that failed in a previous report
- `GIT_TOKEN` injected into HTTPS URL: `https://{token}@github.com/org/repo`

**When to use:**
- Initial load of all existing inventory (Phase 1)
- Monthly re-run to catch repos that haven't pushed to main recently
- Re-running failed rows after fixing scanner bugs

### Approach B — GitHub Actions CI Enforcement

```yaml
# Reusable workflow — maintained by SRE Frameworks
# Called automatically on every push to main

jobs:
  generate-spec:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install spec-engine && npm i -g @redocly/cli
      - run: |
          spec-engine generate \
            --repo . \
            --gateway "${{ vars.API_GATEWAY }}" \
            --owner   "${{ vars.API_OWNER }}" \
            --publish
        env:
          EXPLORER_API_TOKEN: ${{ secrets.EXPLORER_API_TOKEN }}
```

**Two sub-options for enforcement:**

| Sub-option | How | Team impact |
|---|---|---|
| **Required Workflow** (GitHub Enterprise) | Platform Engineering configures org policy; runs on all repos tagged `api-service`. No per-repo changes. | Zero. Teams see the step appear in their workflow runs. |
| **Jenkins Shared Library** | PE adds `specEngine()` step to `standardPipeline()`. Teams already use the shared library. | Zero. Step appears in their Jenkins builds. |

**Per-repo configuration via GitHub variables** (set by `set_repo_variables.sh`, no code commits):
```
API_GATEWAY    = "kong-prod"
API_OWNER      = "@payments-team"
API_FRAMEWORK  = "spring"        # optional override
API_LIFECYCLE  = "production"
```

**When to use:**
- Ongoing freshness after initial batch load
- New services added to inventory automatically (via `api-service` topic)
- Ensures catalog never drifts from code

### Trigger strategy

| Trigger | Publish? | Rationale |
|---|---|---|
| Push to `main` / `master` | ✅ Yes | Stable, reviewed code — the production contract |
| Pull request | ✅ Validate only, no publish | Early feedback without polluting catalog with WIP |
| Feature branch push | ❌ No | WIP code; incomplete routes |
| `workflow_dispatch` | ✅ Yes | Manual re-publish without a code push |

---

## ADR-005 — Existing spec reuse with quality gates

**Decision: Detect committed specs; apply three gates; choose fast-path, hybrid merge, or full AST.**

### The problem

Blindly publishing an existing committed spec is dangerous. A spec written 2 years
ago looks perfectly valid to a format linter yet every schema could be wrong.
Ignoring existing specs wastes human-authored descriptions and examples.

### Quality gates

```
Existing spec found?
│
├── Gate 1: Format valid? (OpenAPI 3.x or Swagger 2.0)
│   └── Fail → run full AST pipeline
│
├── Gate 2: Coverage ≥ 70%?
│   (routes in spec / routes found by AST scanner)
│   └── Fail → run full AST pipeline
│
└── Gate 3: Freshness ≤ 90 days?
    (days since spec committed vs days since last code change)
    └── Fail → flag as STALE, still usable with warning
```

### Three outcomes

| Gates passed | Mode | What publishes |
|---|---|---|
| All three ✅ | **fast-path** | Existing spec + injected x- fields. Done in ~8s. |
| Format ✅, Coverage ❌ | **merge** | AST-generated routes/schemas + existing spec descriptions, examples, security defs |
| Format ❌ | **full AST** | Standard pipeline; existing spec ignored |

### Field ownership in merge mode

```
AST owns (accuracy-critical):          Existing spec contributes (richness):
  - HTTP paths and methods               - operation summary, description
  - path / query parameters              - request / response examples
  - request body field names/types       - securitySchemes
  - response body field names/types      - servers block
  - required / nullable flags            - info.description, externalDocs
  - constraint annotations
```

### Impact

~20–35% of repos in a typical enterprise inventory have a committed spec.
Of those, roughly half pass quality gates → fast-path eligible.
This reduces Phase 1 batch time by ~10–15% and produces richer entries
for repos where engineers already invested in human-authored documentation.

---

## ADR-006 — Zero application code changes

**Decision: spec-engine is strictly read-only. No PRs, no commits, no annotations required.**

The engine clones repos, reads source files, generates a spec, and discards the clone.
Application teams need not change anything — no library imports, no annotations,
no CI file additions.

The one exception: `batch_pr_creator.py` can open PRs to add a GitHub Actions workflow
to repos that want to self-host the CI step. **This tool is voluntary-only and is not
part of the standard rollout.** Platform-level enforcement (ADR-004, Approach B)
achieves the same result without any application repo changes.

---

## ADR-007 — Why not use an AI coding agent (Devin) instead?

**Decision: AI coding agents are the wrong tool for this problem. AST is the right tool.**

This question frequently arises because tools like Devin are capable of generating code
and documentation. The comparison is worth addressing directly.

### What Devin is designed for

Devin is an interactive engineering agent: you give it a task, it explores a codebase,
writes code, and opens a PR. It is purpose-built for **one-time, supervised, creative tasks**.
It is not a CI/CD pipeline component.

### Head-to-head comparison

| Dimension | AI coding agent (Devin) | spec-engine (AST) |
|---|---|---|
| **Deterministic output** | ❌ Different output on each run; LLMs are non-deterministic | ✅ Same code → same spec, always |
| **Source code security** | ❌ Source code sent to an external service | ✅ Runs entirely inside your infrastructure; nothing leaves |
| **CI/CD integration** | ❌ Interactive agent; not designed as an automated pipeline step | ✅ Single CLI command, exit code, artifact output |
| **Cost model** | ❌ Per-session; 200 repos × every push to main = unbounded | ✅ Fixed infrastructure cost; no per-run charge |
| **Schema accuracy** | ❌ Can hallucinate field names, types, or routes that don't exist | ✅ Reads the actual AST; cannot invent code that isn't there |
| **Scale** | ❌ Not designed for bulk processing; session limits, rate limits | ✅ 16-worker parallelism; 200 repos in one batch run |
| **Org metadata enforcement** | ❌ Prompt-dependent; inconsistent x-owner/x-gateway injection | ✅ Config-driven; required fields always present |
| **Audit trail** | ❌ Cannot trace a spec field back to a code change | ✅ Fully reproducible; same commit = same spec |
| **Freshness on every merge** | ❌ Requires a new agent session per push | ✅ Runs automatically in CI in ~90 seconds |
| **Maintenance surface** | ❌ Model version change → spec output changes unpredictably | ✅ Scanner change is a 5-line diff with a test |

### The deeper issue: where the work actually is

A naive analysis says: "spec generation is just reading code and writing YAML — an AI can do that."
That is true for a single repo on a single day. The actual project work breaks down differently:

| Activity | % of effort | AI-substitutable? |
|---|---|---|
| Framework scanner implementation (7 frameworks) | 25% | Partially — but needs expert validation per framework |
| Schema inferrer (type resolution, generics, cycle detection) | 20% | No — requires deep type-system understanding |
| Accuracy validation on real enterprise repos (not synthetic examples) | 15% | No — requires reading actual internal codebases |
| Security review, infra integration, CI enforcement | 15% | No — requires internal access Devin cannot have |
| Explorer catalog API integration, retry logic, confidence governance | 10% | No — internal API; Devin has no credentials |
| Test coverage, regression harness (365+ tests) | 10% | Partially |
| Batch tooling, monitoring, MANUAL triage workflow | 5% | Partially |

**At most 30–35% of the effort is the kind of code generation Devin accelerates.**
The remaining 65–70% is integration, coordination, security, and internal access — work
that cannot be delegated to an external agent.

### The security argument alone is disqualifying

Our source code contains:
- Proprietary business logic
- Internal hostname and endpoint patterns
- Security annotation patterns (auth scopes, roles, permission checks)

Sending this to an external AI service to generate an OpenAPI spec would require
a security review and likely a data handling agreement that itself takes months
to negotiate. spec-engine runs in your VPC; source code never crosses a network boundary.

### What AI tooling can contribute

This is not a blanket rejection of AI. AI tools are valuable for:
- Authoring human-written `description` fields in the spec (supplementing AST output)
- Triage suggestions for MANUAL-confidence routes
- Summarising what an API does for the catalog's `info.description`

These are **additive** use cases — AI enhancing a spec that AST has already generated —
not a replacement for the generation pipeline itself.

### Summary

Devin solves the wrong problem: it writes code once. spec-engine solves the right problem:
it reads code continuously and keeps 200 specs in sync with reality without any human in the loop.
For an automated, security-sensitive, org-scale pipeline that must run reliably on every
git push, AST is the only correct foundation.

---

## 10. Execution Plan — 6 Months

**Team:** 4 Senior Engineers (Eng1–4) + 1 Program Manager (PM) + 1 Platform Engineer (PE)

**Eng1** = Core Engine (config, models, assembler, publisher, CLI)
**Eng2** = Java/Spring
**Eng3** = Python/FastAPI/DRF
**Eng4** = Go/TypeScript/CI templates
**PE** = Batch tooling, runner images, Platform Engineering liaison

```
         Month 1              Month 2              Month 3
         Weeks 1–4            Weeks 5–8            Weeks 9–12
Eng1  ── Core infra ─────── Assembler ─────────── Publisher + CLI ──────►
Eng2  ── Spring scanner ─── Java inferrer ─────── Integration tests ────►
Eng3  ── FastAPI scanner ── DRF scanner ────────── Python inferrer ───────►
Eng4  ── Express/NestJS ─── Go binary + Gin/Echo ─ TS inferrer ──────────►
PE    ── Dev env / CI ────── batch_loader.py ────── PE engagement begins ─►
PM    ── Kickoff / ADRs ─── Framework inventory ─── Risk review / demo prep►
```

```
         Month 4              Month 5              Month 6
         Weeks 13–16          Weeks 17–20          Weeks 21–26
Eng1  ── Pilot + bug fixes ─ Batch triage ──────── Monitoring + docs ────►
Eng2  ── Pilot (Spring) ──── MANUAL triage ─────── Handover ─────────────►
Eng3  ── Pilot (Python) ──── MANUAL triage ─────── Handover ─────────────►
Eng4  ── Pilot (Go/TS) ───── CI templates final ── Handover ─────────────►
PE    ── PE: runner images ─ Full batch load ─────── Req Workflow rollout ►
PM    ── Leadership demo #1─ Phase 1 report ─────── Project close ────────►
```

### Milestones and gates

| Milestone | When | Gate question |
|---|---|---|
| **M1 — Architecture approved** | End of Week 1 | Are all ADRs signed off? |
| **M2 — First end-to-end pipeline** | End of Month 1 | Does `spec-engine generate` work for Spring + FastAPI? |
| **M3 — All scanners + inferrers done** | End of Month 2 | Do all 7 frameworks produce valid `List[RouteInfo]`? |
| **M4 — Engine hardened** | End of Month 3 | 80%+ test coverage? Publisher talking to catalog (staging)? |
| **M5 — Pilot complete** | End of Month 4 | 10–15 real repos in catalog. ≥90% success rate? → **Go/no-go for Phase 1** |
| **M6 — Phase 1 complete** | End of Month 5 | ≥90% of inventory published. batch_report.csv < 5% hard failures? |
| **M7 — Phase 2 launched** | End of Month 6 | Required Workflow running on all `api-service` repos? Project closed? |

### Critical path

The critical path is: **Core infrastructure → Spring Boot scanner → Assembler → Publisher → Pilot**.

Everything else (Go, TypeScript, Django) runs in parallel. If Eng4's Go work
slips 2 weeks, it does not affect the pilot gate. If Eng1's assembler slips,
everything stalls. Eng1 is the dependency — the PM watches this workstream daily.

### What "building from scratch" means for Month 1

Week 1 is not coding — it is verification. Before writing production code:
- Survey 20–30 real repos per framework (Eng2-4 each take their stack)
- Identify annotation patterns that don't match documentation (these are the bugs you'll fix in Month 3)
- Confirm Explorer catalog API endpoints and payload shape (Eng1 + PM)
- Spike the Go binary subprocess bridge (Eng4) and ts-morph subprocess (Eng4)
- Get architecture signed off (this document + ERD of models)

Skipping this costs 4–6 weeks in Month 3 when surprises surface during real-repo testing.

---

## 11. Budget — $500K

### Team cost (6 months, fully loaded)

| Role | Annual cost (fully loaded) | 6-month allocation | Count | Total |
|---|---|---|---|---|
| Senior Engineer | $160,000 | $80,000 | 4 | $320,000 |
| Program Manager | $140,000 | $70,000 | 1 | $70,000 |
| Platform Engineer | $150,000 | $75,000 | 1 | $75,000 |
| **Personnel subtotal** | | | | **$465,000** |

### Non-personnel

| Item | Cost |
|---|---|
| CI/CD compute (GitHub Actions minutes, storage) | $12,000 |
| Tooling (Redocly, Spectral, monitoring) | $8,000 |
| Training and ramp-up | $5,000 |
| Contingency | $10,000 |
| **Non-personnel subtotal** | **$35,000** |

### Total: **$500,000**

### Why not 1 engineer?

The 4 language stacks are genuinely parallel and independent. Serialising them
adds 7 months to the timeline. Here is the math:

```
Serialised (1 engineer):                     Parallel (4 engineers):
  Architecture           3w                   Architecture     3w  ─┐
  Core infrastructure    3w                   Core infra       3w   │ Month 1
  Spring + Java          5.5w                                        │
  FastAPI + DRF          6w   ← sequential    Spring + Java  ─────── Month 2–3  (Eng2)
  Express/NestJS         2.5w                 FastAPI + DRF  ─────── Month 2–3  (Eng3)
  TypeScript             1.5w                 Go/TS + CI     ─────── Month 2–3  (Eng4)
  Go binary + inferrer   5.5w                 Assembler + Pub─────── Month 2–3  (Eng1)
  Assembler              2.5w                                 ─────── Month 4: Pilot
  Validator + Publisher  2w                                   ─────── Month 5: Batch
  Tests + Docs           4w                                   ─────── Month 6: Platform
  Engine total:         ~37.5w (9.4 months)   Engine total:  ~12w (3 months)
  Full delivery:        ~53w  (13 months)      Full delivery: ~26w (6 months)
```

1 engineer costs less per month but delivers the same output 7 months later —
foregoing ~$490K in annual savings from delayed catalog coverage.
On any 18-month horizon, 1 engineer is the more expensive option.

---

## 12. Engineering FAQs

**Q: Why not use SpringDoc, FastAPI's built-in `/docs`, or drf-spectacular?**

These are runtime tools — they require the application to run, which is not
possible in a CI/CD build step that just checks out code. They also generate
per-framework specs with no unified org metadata injection and cannot enforce
`x-owner`, `x-gateway`, or `x-lifecycle` at scale. For repos that have
already used these tools and committed the output file, spec-engine detects
that file and can fast-path publish it (ADR-005).

---

**Q: How does cycle detection work in the inferrer?**

`BaseInferrer` maintains a `_visiting: Set[str]` per inference call.
Before resolving a type, it checks if that type name is already in `_visiting`.
If yes — cycle detected — it returns a `$ref` pointing to the schema name without
recursing. This mirrors how Java/TypeScript compilers handle forward references.

```python
def resolve_type(self, name: str) -> SchemaResult:
    if name in self._visiting:
        return SchemaResult({"$ref": f"#/components/schemas/{name}"}, Confidence.HIGH)
    self._visiting.add(name)
    try:
        return self._extract_fields(name)
    finally:
        self._visiting.discard(name)
```

---

**Q: A request/response type is in a shared library — separate repo, not in the clone. What happens?**

`_find_type_file()` searches the cloned repo and returns `None` if the type file
is not found. The inferrer returns an empty schema with `MANUAL` confidence.
The spec is still published — the route appears with a stub body schema marked
`x-confidence: manual`.

Long-term fix: declare shared library deps in `.spec-engine.yaml`:
```yaml
external_schemas:
  - repo: https://github.com/org/shared-dtos
    path: src/main/java/com/example/dto
```
This is a Phase 3 roadmap item, not in scope for the initial build.

---

**Q: How does the batch handle 500 repos in parallel without blowing up memory?**

`batch_loader.py` uses `concurrent.futures.ProcessPoolExecutor` (not threads —
avoids GIL and gives true CPU parallelism). Each worker runs in a separate
OS process. Each repo is cloned to a `tempfile.TemporaryDirectory` that is
cleaned up when the `with` block exits. Peak memory per worker is bounded by
the largest repo being scanned (~200–400 MB for a large Spring monorepo).
With 16 workers on a machine with 32 GB RAM, this is safe.

---

**Q: What does a MANUAL-confidence entry look like in the catalog? Is it harmful?**

It is visible, not hidden. The published spec contains:

```yaml
paths:
  /v1/accounts:
    post:
      x-confidence: manual
      requestBody:
        content:
          application/json:
            schema:
              x-confidence: manual
              x-confidence-reason: "Type 'CreateAccountRequest' not found in repo"
              description: "Schema not resolved — manual authoring required"
              type: object
```

API consumers see a stub. It is clearly incomplete, not silently wrong.
The MANUAL triage list is exported from `batch_report.csv` and assigned
to API teams in the first week after Phase 1.

---

**Q: What happens when Spring Boot 3 introduces a new annotation pattern?**

Scanners are a thin mapping layer — typically 5–10 lines per new annotation:

```python
# scanner/spring.py
_METHOD_ANNOTATIONS = {
    "GetMapping":     "GET",
    "PostMapping":    "POST",
    "PutMapping":     "PUT",
    "DeleteMapping":  "DELETE",
    "PatchMapping":   "PATCH",
    # Adding Spring Boot 3 @HttpExchange support:
    "GetExchange":    "GET",
    "PostExchange":   "POST",
}
```

New annotation support is a 1–3 day ticket, not a multi-week project.
The architecture is designed for this: add to the map, add a test fixture,
run the suite. The 365-test suite catches regressions immediately.

---

**Q: How do we know the generated spec is accurate enough to trust?**

Three layers:
1. **Structural validation** — Spectral + Redocly lint on every generated spec
2. **Confidence visibility** — every schema field carries `x-confidence`; the catalog surface this to consumers
3. **Coverage cross-check** — for repos with existing specs, Stage 0 compares AST route count vs spec route count; divergence > 30% triggers a warning

Accuracy increases over time as MANUAL cases are resolved by API teams.
The target after Phase 1 is ≥80% of routes with HIGH or MEDIUM confidence.

---

**Q: Can a team opt out?**

Yes. Remove the repo's row from `api_inventory.csv` (Approach 1) or
remove the `api-service` GitHub topic (Approach 2). Teams can also add
`.spec-engine.yaml` at repo root with `skip: true` for a code-level opt-out
that survives CSV updates.

---

*Document version: March 2026 — Engineering review draft*
