# OpenAPI Spec Generation — Approach Comparison

> Reference doc for engineering partner discussions.
> Covers all known approaches, trade-offs, and recommended hybrid strategies.

---

## Quick Reference — All Approaches

| # | Approach | Schema Accuracy | No Source Access | CI-Native | Governance Metadata | Unified Across Frameworks |
|---|---|---|---|---|---|---|
| 1 | **AST (spec-engine)** | ✅ High | ❌ Needs repos | ✅ Yes | ✅ Yes | ✅ Yes |
| 2 | **Framework-native** (SpringDoc, FastAPI) | ✅ High | ❌ Needs running app | ⚠️ Partial | ❌ No | ❌ One per framework |
| 3 | **Gateway introspection** (Kong, Apigee) | ❌ Routes only, no schemas | ✅ Yes | ⚠️ Partial | ❌ No | ✅ Yes |
| 4 | **eBPF / Traceable** | ⚠️ Traffic-only | ✅ Yes | ❌ No | ❌ No | ✅ Yes |
| 5 | **Service mesh / sidecar** (Istio, Envoy) | ⚠️ Traffic-only | ✅ Yes | ❌ No | ❌ No | ✅ Yes |
| 6 | **Network proxy** (mitmproxy, Charles) | ⚠️ Traffic-only | ✅ Yes | ❌ No | ❌ No | ✅ Yes |
| 7 | **Test suite observation** (Pact, Dredd) | ⚠️ Test-coverage dependent | ❌ Needs test run | ✅ Yes | ❌ No | ⚠️ Partial |
| 8 | **AI / LLM** (GPT-4, Devin) | ❌ Hallucination risk | ❌ Code sent externally | ❌ No | ❌ No | ✅ Yes |
| 9 | **Postman / collection conversion** | ⚠️ Example-driven only | ✅ Yes | ❌ No | ❌ No | ✅ Yes |

---

## Approach Details

---

### 1. AST — Abstract Syntax Tree (spec-engine)

**How it works:**
Parses source code into a structured tree — the same way a compiler reads code —
and walks the tree to extract routes, parameters, and type schemas without running
the application.

```
Source code  →  AST parser  →  RouteInfo + SchemaResult  →  OpenAPI 3.1  →  Explorer
```

**Supported frameworks:** Spring Boot, FastAPI, Django REST, NestJS, Express, Gin, Echo

| Dimension | Detail |
|---|---|
| Schema accuracy | Full — all declared fields, types, constraints, optional fields, error responses |
| Source access required | Yes — read-only shallow clone (~5 seconds, discarded immediately) |
| Application must run | No |
| CI/CD integration | Yes — single CLI command, exit code, artifact output |
| Governance metadata | Yes — x-owner, x-gateway, x-lifecycle config-driven and always enforced |
| Deterministic | Yes — same code always produces the same spec |
| Cost model | Fixed infrastructure; no per-run charge |
| PII risk | None — reads field names and types only, never actual data |

**Best for:** Complete, accurate, governed specs generated automatically on every code push.

**Main concern raised:** Requires read-only source code access (repo cloning).

---

### 2. Framework-Native Spec Generation

**Tools:** SpringDoc (Java), FastAPI `/docs` (Python), drf-spectacular (Django),
tsoa (TypeScript), swaggo (Go)

**How it works:**
A library is added to each application. It generates an OpenAPI spec at runtime
by inspecting annotations, decorators, or docstrings while the app is running.

| Dimension | Detail |
|---|---|
| Schema accuracy | High — annotations are source of truth for that framework |
| Source access required | No — but app must be running |
| Application must run | Yes — cannot generate without a live process |
| CI/CD integration | Partial — needs a running app in CI (test environment, Docker Compose) |
| Governance metadata | No — each tool generates its own format; no unified x-fields |
| Deterministic | Yes |
| Code changes required | Yes — must add library dependency to every repo |
| Unified across frameworks | No — SpringDoc for Java, drf-spectacular for Django, etc. |

**Best for:** Individual teams who want rich annotations in their own stack.

**Why not for org-wide rollout:**
- Requires adding a library dependency to every repo — 200 teams to coordinate
- Each tool produces a different format; no unified governance metadata
- Requires the app to run in CI — adds infrastructure complexity per service
- Coordinating 200 teams to adopt different tools is the same manual problem we started with

---

### 3. Gateway Introspection

**Tools:** Kong Admin API, Apigee Management API, AWS API Gateway, Azure APIM

**How it works:**
Queries the API gateway's management API to extract the list of registered routes,
methods, and basic configuration.

```
Gateway Admin API  →  route list (path + method)  →  skeleton OpenAPI spec
```

| Dimension | Detail |
|---|---|
| Schema accuracy | ❌ Routes and methods only — no request/response body schemas |
| Source access required | No |
| Application must run | No |
| CI/CD integration | Partial — can query on schedule; not triggered by code changes |
| Governance metadata | No |
| Deterministic | Yes |
| What you get | Path + HTTP method only — no parameters, no schemas, no descriptions |

**Best for:** Initial API discovery and inventory population — finding out what APIs exist.

**Why not as primary spec generator:**
Publishing a spec with paths and methods but no schema information is arguably
worse than no spec — it looks complete but provides no useful contract for consumers.

**Best hybrid use:** Gateway introspection → populate `api_inventory.csv` → spec-engine
generates accurate spec from source.

---

### 4. eBPF / Runtime Traffic Observation (Traceable)

**Tools:** Traceable AI, Akita, Speedscale

**How it works:**
An eBPF agent hooks into the Linux kernel and passively observes real HTTP traffic
without modifying the application. Builds API inventory and schemas from observed
requests and responses over time.

| Dimension | Detail |
|---|---|
| Schema accuracy | ⚠️ Traffic-dependent — only fields that appear in observed calls |
| Source access required | No |
| Application must run | Yes — needs live traffic to build schemas |
| CI/CD integration | No — not triggered by code changes |
| Governance metadata | No |
| Optional fields coverage | ❌ Never captured if never sent in traffic |
| Error response coverage | ❌ Only captured if errors actually occur |
| Low-traffic endpoints | ❌ May never be observed |
| PII risk | ⚠️ Observes actual request/response payloads including sensitive data |
| Current state in your environment | No API access to extract specs; most apps have no entry; some have entry but no actual spec |

**Best for:** Shadow API discovery — finding APIs with no known source repo.

**Why not as primary spec generator:**
A spec built from traffic is a description of what happened, not a declaration of
what the API guarantees. Missing optional fields, error responses, and rare endpoints
produces a partial contract that misleads consumers.

**Current blocker:** No API access to extract Traceable specs programmatically.
Cannot use as input source until access is granted.

---

### 5. Service Mesh / Sidecar Proxy Observation

**Tools:** Istio + Envoy, Linkerd, Consul Connect

**How it works:**
All inter-service traffic is routed through a sidecar proxy. The proxy logs
requests and responses, which are aggregated to build API inventory and schemas.

| Dimension | Detail |
|---|---|
| Schema accuracy | ⚠️ Same limitations as eBPF/Traceable — traffic-based |
| Source access required | No |
| Infrastructure required | Yes — full service mesh deployment required |
| CI/CD integration | No |
| Governance metadata | No |

**Best for:** Organisations that already have a service mesh and want traffic
visibility built in.

**Why not here:** Same traffic-based schema gaps as Traceable, plus requires
service mesh infrastructure that is not currently deployed across all services.

**Verdict:** Operationally heavier version of Traceable with the same fundamental limitations.

---

### 6. Network Proxy / Traffic Capture

**Tools:** mitmproxy, Charles Proxy, Burp Suite, dedicated capture proxy

**How it works:**
API traffic is routed through a proxy that records every request and response.
Captured traffic is converted to an OpenAPI spec.

| Dimension | Detail |
|---|---|
| Schema accuracy | ⚠️ Traffic-based — same gaps as Traceable |
| Source access required | No |
| Infrastructure change required | Yes — traffic routing must be modified |
| CI/CD integration | No |
| PII risk | ⚠️ High — proxy sees all payloads |
| Governance metadata | No |

**Best for:** One-off discovery on a specific service where no other option is available.

**Why not for org-wide rollout:** Requires routing production traffic through a new
proxy — a significant infrastructure and security change. Same schema gaps as Traceable.

---

### 7. Test Suite / Contract Observation

**Tools:** Pact (consumer-driven contracts), Spring Cloud Contract, Dredd

**How it works:**
Existing integration or contract tests are run; HTTP requests and responses are
recorded and converted to an OpenAPI spec. Pact specifically formalises this as
consumer-driven contract testing.

| Dimension | Detail |
|---|---|
| Schema accuracy | ⚠️ Only as good as test coverage |
| Source access required | No — but needs runnable test suite |
| Application must run | Yes — for integration tests |
| CI/CD integration | Yes — runs in CI alongside tests |
| Governance metadata | No |
| Coverage gap | Any untested endpoint or response code is missing from the spec |

**Best for:** Teams with mature, comprehensive integration test suites.

**Why not for org-wide rollout:**
85% of services don't have consistently maintained integration test suites.
The services that need specs most urgently are also the ones least likely to
have good test coverage.

---

### 8. AI / LLM Inference

**Tools:** GPT-4, GitHub Copilot, Devin, custom prompts

**How it works:**
Source code files are sent to an AI model with a prompt asking it to generate
an OpenAPI spec.

| Dimension | Detail |
|---|---|
| Schema accuracy | ❌ Can hallucinate field names, types, and endpoints |
| Source access required | Yes — code sent to external service |
| Deterministic | ❌ No — different output on every run |
| CI/CD integration | ❌ Not designed as an automated pipeline step |
| Cost model | ❌ Per-token; 200 repos × every push = unbounded |
| Security | ❌ Proprietary source code leaves your infrastructure |
| Governance metadata | ❌ Prompt-dependent; inconsistent |

**Best for:** Drafting a first-pass spec for a single service where a human
reviews the output before publishing.

**Why not for org-wide automation:** See ADR-007. Non-deterministic output,
external data exposure, unbounded cost, and no reliable CI integration make
this unsuitable as an automated platform capability.

---

### 9. Postman / Collection Conversion

**Tools:** postman-to-openapi, openapi-generator, Insomnia export

**How it works:**
Teams export their existing Postman or Insomnia collections. A converter
tool transforms the collection format into OpenAPI YAML.

| Dimension | Detail |
|---|---|
| Schema accuracy | ⚠️ Example-driven — fields present in saved requests only |
| Source access required | No |
| Requires team action | Yes — teams must maintain and export collections |
| CI/CD integration | Partial — if collections are version-controlled |
| Governance metadata | No |
| Coverage | Depends entirely on how thoroughly the team maintains their Postman workspace |

**Best for:** Services where the team already maintains a thorough Postman collection
and has no accessible source repo.

**Why not for org-wide rollout:** Most services don't maintain comprehensive Postman
collections. This has the same root problem as manual spec writing — it relies on
individual team discipline to keep collections up to date.

---

## Hybrid Strategies — Realistic Combinations

### Hybrid A — Gateway discovery + AST generation (Recommended starting point)

```
Kong / Apigee Admin API
        │
        ▼
Auto-populate api_inventory.csv       ← replaces manual CSV population
        │
        ▼
spec-engine (AST)
        │
        ▼
Explorer catalog
```

**What this solves:** The main gap in our current design — the CSV has to be populated
manually. Gateway introspection automates that step.
**What it doesn't change:** Everything after inventory population stays identical.

---

### Hybrid B — Traceable discovery + AST generation (Best long-term if access is granted)

```
Traceable (eBPF)
  ├── Full API inventory          ← replaces CSV population
  ├── Shadow API detection        ← catches APIs with no repo
  └── Baseline schemas            ← Stage 0 input alongside committed specs
        │
        ▼
spec-engine Stage 0 quality gates
  ├── Traceable spec passes gates → merge mode (Traceable descriptions + AST schemas)
  └── Traceable spec fails gates  → full AST pipeline
        │
        ▼
AST pipeline (scanner → inferrer → assembler → validator → publisher)
        │
        ▼
Explorer catalog + coverage cross-check
  (Traceable observed N routes, AST found M — flag gap if M < N)
```

**What this adds:**
- No manual CSV work
- Shadow API detection
- Richer baseline for merge mode
- Coverage validation (catch endpoints AST missed)

**What stays the same:** The entire AST generation pipeline — Traceable is an
additional discovery and validation input, not a replacement for spec generation.

**Current blocker:** No API access to extract Traceable specs. Start with Hybrid A;
switch to Hybrid B when access is granted.

---

### Hybrid C — Framework-native where it exists + AST for the rest

```
For services using SpringDoc / drf-spectacular / FastAPI:
  Detect committed spec (Stage 0)
  Apply quality gates
  Fast-path publish OR merge with AST output

For all other services:
  Full AST pipeline
```

**What this adds:** Services that have already invested in SpringDoc or drf-spectacular
get fast-path publishing without re-scanning their source.

**What stays the same:** AST pipeline covers everything not already documented.
This is already designed in Stage 0 (existing spec detection — ADR-005).

---

## Decision Guide — Matching Objection to Response

| If the partner suggests | The real trade-off | Your response |
|---|---|---|
| **"Just use SpringDoc / FastAPI built-ins"** | High accuracy but requires code changes in every repo and a running app per service | Works for individual teams; doesn't scale to 200 services without coordinating repo changes across all of them |
| **"Query the gateway"** | Gets you inventory but zero schema information | Good idea for the discovery step — replace manual CSV population. Still need AST for the actual spec content. |
| **"Use Traceable / eBPF"** | Great for discovery; traffic-based schemas are incomplete | We want this — blocked on getting API access. Even with access, it's an input to the pipeline, not a replacement. |
| **"Use a service mesh"** | Same limitations as Traceable, requires mesh infrastructure | Heavier version of Traceable with the same schema gaps. |
| **"Use AI / LLM"** | Fast to prototype, non-deterministic and insecure at scale | See ADR-007. Cannot be a CI/CD step — same code produces different specs on different runs. |
| **"I don't want to clone repos"** | Security / operational concern about source access | Read-only, shallow clone, in-VPC, discarded in 90 seconds. Same access a developer's IDE uses. What specifically is the concern? |

---

## The One-Slide Summary

```
                SCHEMA ACCURACY
                      │
            High ─────┼─────
                      │    AST ✅
                      │    Framework-native ✅
                      │
          Medium ─────┼─────
                      │    Traceable / eBPF ⚠️
                      │    Service mesh ⚠️
                      │    Test suite ⚠️
                      │    Postman ⚠️
                      │
             Low ─────┼─────
                      │    Gateway ❌ (routes only)
                      │    AI / LLM ❌ (hallucination)
                      │
                      └───────────────────────────
                     Needs app   Needs source   Neither
                     to run      code access

AST is the only approach in the top-right quadrant:
  high schema accuracy + no running app required + source stays in your infra.
```

---

## Recommended Position

**Start:** AST (spec-engine) + Gateway introspection for inventory population

**Add when available:** Traceable as discovery and coverage cross-check layer

**Do not replace AST with:** Any traffic-based approach (Traceable, service mesh, proxy)
— traffic-based schemas are permanently incomplete for optional fields, error
responses, and low-traffic endpoints.

---

*Reference doc — March 2026*
