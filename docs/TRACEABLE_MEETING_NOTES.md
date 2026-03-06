# Traceable vs AST — Meeting Reference Notes

> Quick reference for the discussion on whether eBPF-based runtime observation
> (Traceable) can replace AST-based source scanning for OpenAPI spec generation.

---

## The Engineering Partner's Concern

**"We don't want to scan source code."**

Before the meeting, clarify which objection this actually is:

| Real objection | What they might say | Your response |
|---|---|---|
| **Security** — tool reads proprietary code | "Our IP shouldn't be parsed by a tool" | spec-engine is read-only, runs inside your infra, nothing leaves the VPC |
| **Operational** — cloning repos feels invasive | "We can't clone 200 repos" | Shallow clone (depth=1), read-only, discarded after 90 seconds |
| **Complexity** — AST parsers per language | "It's too much to build and maintain" | Already built and tested (365 tests, 7 frameworks) |
| **They think Traceable replaces this** | "Traceable already does this" | It partially does — see below |

Ask directly: **"What specifically concerns you about source scanning?"**
The answer changes which response you lead with.

---

## What Traceable (eBPF) Actually Does

Traceable deploys an eBPF agent at the kernel level that passively observes
real HTTP traffic without modifying application code. From that traffic it:

- Discovers which API paths exist (from observed requests)
- Infers request/response schemas (from observed payloads)
- Builds an API inventory over time

This is a **runtime traffic observation** approach, not a static analysis approach.

---

## Current State of Traceable in Your Environment

Based on what you've described:

| Issue | What this means |
|---|---|
| Most apps have **no entry** in Traceable | Traffic-based discovery hasn't covered full inventory |
| Some apps show **an entry but no spec** | Traceable sees the service exists but hasn't captured enough traffic to build a spec |
| **No API access** to extract specs | Even where specs exist, you can't pull them programmatically into Explorer |
| **No UI visibility** into the specs | You can't manually review what Traceable has generated |

**Bottom line:** Traceable is not a viable primary path today even if you wanted it to be.
You don't have the access or coverage needed to use it as a spec source.

---

## Head-to-Head: Traceable vs AST

| Dimension | Traceable (eBPF / runtime) | spec-engine (AST / static) |
|---|---|---|
| **How it works** | Observes actual HTTP traffic | Reads source code structure |
| **API discovery** | ✅ Discovers APIs automatically from traffic | ⚠️ Needs CSV inventory as starting point |
| **Schema accuracy** | ⚠️ Only fields that appear in observed requests | ✅ All declared fields in source code |
| **Optional fields** | ❌ Never seen if never sent | ✅ Always captured from type definitions |
| **Error responses** | ❌ Only captured if errors occur in traffic | ✅ Always captured from return types |
| **Rare endpoints** | ❌ Low-traffic routes may never be observed | ✅ All routes captured regardless of traffic |
| **Requires live traffic** | ❌ Cold apps, dev environments invisible | ✅ Works on any branch at any time |
| **No source access needed** | ✅ Works without repos | ❌ Needs repo access |
| **Governance metadata** | ❌ Cannot inject x-owner, x-gateway, x-lifecycle | ✅ Config-driven, always enforced |
| **PII risk** | ⚠️ Sees actual request/response data in traffic | ✅ Sees field names and types only, no data |
| **CI/CD integration** | ❌ Not designed as a pipeline step | ✅ Single CLI command |
| **Spec freshness** | ⚠️ Requires new traffic after each change | ✅ Triggered on every code push |
| **Spec extractable today** | ❌ No API access; limited visibility | ✅ Generated directly; published programmatically |
| **Deterministic** | ❌ Output varies by traffic at observation time | ✅ Same code = same spec always |

---

## The Fundamental Limitation of Traffic-Based Specs

A spec built from traffic is a **description of what happened**, not a
**declaration of what the API guarantees**.

```
Traffic-based spec:                    AST-based spec:
  "I saw these fields in 1,000 calls"    "The code declares these fields"
  Missing: optional fields               Includes: every declared field
  Missing: rare error responses          Includes: every return type
  Missing: undocumented constraints      Includes: validation annotations
  Accuracy: depends on traffic volume    Accuracy: deterministic from code
```

An API consumer needs the declared contract, not a sample of past traffic.

---

## The Right Way to Think About Both Together

Traceable and AST solve **different parts of the problem**.
They are complementary, not competing.

```
TRACEABLE                                AST (spec-engine)
─────────                                ─────────────────
Good at:                                 Good at:
  ✅ Discovering what APIs exist           ✅ Generating accurate schemas
  ✅ Finding undocumented shadow APIs      ✅ Capturing all fields + constraints
  ✅ No source access needed              ✅ CI/CD integration
  ✅ Cross-cutting traffic visibility     ✅ Governance metadata injection

Weak at:                                 Weak at:
  ❌ Complete schema accuracy             ❌ Discovering APIs with no repo
  ❌ Governance metadata                  ❌ Dynamic runtime-only routes
  ❌ CI/CD pipeline integration          ❌ APIs outside the CSV inventory
```

**The ideal architecture uses both:**

```
Traceable  →  API discovery / inventory  →  feeds CSV input for spec-engine
                                                   │
                                                   ▼
spec-engine  →  accurate spec generation  →  Explorer catalog

Traceable also  →  validates coverage   →  did AST miss any live endpoints?
```

---

## If You Get Full Traceable Access — What Changes in the Design

Assuming Traceable grants: (a) API access to extract specs, (b) full inventory visibility.

### What Traceable replaces

| Current design | With Traceable access |
|---|---|
| Manual CSV population | Traceable API → auto-populate inventory CSV |
| Stage 0 only checks committed specs | Stage 0 also pulls Traceable spec as baseline |
| Discovery gap for shadow APIs | Traceable catches routes with no source repo |

### What stays the same

| Component | Why it doesn't change |
|---|---|
| AST-based scanner + inferrer | Traceable schemas are traffic-derived; AST schemas are declaration-derived. AST is more accurate for full contract coverage. |
| Confidence model | Still needed — Traceable specs have their own gaps (optional fields, rare responses) |
| Governance metadata injection | Traceable has no concept of x-owner, x-gateway, x-lifecycle |
| Validator + Publisher | Normalization and catalog publish are unchanged |
| CI/CD enforcement | Traceable doesn't replace ongoing freshness on every code push |

### Revised pipeline with Traceable access

```
Phase 0 — Discovery
  Traceable API  →  full API inventory list  →  api_inventory.csv (auto-populated)

Phase 0 — Pre-flight (per repo)
  Check committed spec (existing)
  Check Traceable spec (new)           ← new input source
  Apply quality gates (coverage ≥ 70%, freshness ≤ 90 days)
  Choose: fast-path / merge / full AST

Phase 1–6 — Core pipeline (unchanged)
  AST Scanner → Inferrer → Assembler → Validator → Publisher

Phase X — Coverage validation (new)
  Compare AST-generated routes vs Traceable-observed routes
  Flag routes in Traceable not found by AST scanner (shadow APIs)
```

### What you gain with Traceable access

- **Auto-populated inventory** — no manual CSV, no missed services
- **Shadow API detection** — APIs with no repo that only Traceable sees
- **Coverage cross-check** — Traceable observed N routes, AST found M; if M < N, flag the gap
- **Richer baseline for merge mode** — Traceable spec provides observed examples to enrich AST output

### What you don't gain

- Schema completeness (still need AST for all declared fields)
- Governance metadata enforcement
- CI/CD freshness on code changes
- Deterministic, reproducible specs

---

## How to Handle This in the Meeting

### If the partner says "use Traceable instead of AST"

> "Traceable is great for discovery — it tells us what APIs exist.
> But it can only describe what it has observed in traffic. It will miss optional
> fields, error responses, and low-traffic endpoints. It also can't inject the
> governance metadata we need (owner, gateway, lifecycle). We use Traceable to
> find what APIs exist, and AST to generate the accurate, governed contract.
> Right now we don't have API access to Traceable, so we need the CSV path anyway
> to get started."

### If the partner says "I don't want to clone source repos"

> "spec-engine does a read-only shallow clone — it takes about 5 seconds,
> reads the source files, and immediately deletes the clone. Nothing is written
> to the repo. It's the same read access a developer's IDE uses every day.
> If there's a specific security concern about the cloning mechanism, we can
> address that — is it the token scope, the clone destination, or something else?"

### If the partner says "Traceable already generates specs, just use those"

> "We looked at this. Right now we don't have API access to extract Traceable specs,
> and most of our services don't have specs there — some have entries but no actual
> spec. Even if we had full access, Traceable specs would still need normalization,
> governance metadata, and validation before publishing to Explorer.
> That's exactly what spec-engine's publish pipeline does — we can plug Traceable
> in as an additional input source if access is granted. It doesn't replace the pipeline."

### If the partner says "let's wait for Traceable access before building"

> "Traceable access would give us better discovery, but it doesn't change the
> core generation and publishing pipeline. That pipeline is needed whether the
> input is a CSV or a Traceable inventory. If we wait for Traceable access before
> starting, we delay the catalog coverage we've committed to deliver.
> We recommend starting with the CSV path now — it's ready — and plugging
> Traceable in as an enhanced discovery source when access is available."

---

## Decision Framework for the Meeting

```
Does the partner have a specific objection?
│
├── "Don't read source code" → Ask: what's the specific concern?
│   ├── Security concern   → spec-engine is read-only, in-VPC, no external calls
│   ├── Complexity concern → already built and tested
│   └── "Use Traceable"   → see below
│
└── "Use Traceable instead"
    ├── Do we have Traceable API access? → NO today
    │   └── Must use CSV + AST path to start; revisit when access granted
    │
    └── If access is granted:
        ├── Use Traceable for inventory discovery (replaces CSV population)
        ├── Use Traceable spec as additional Stage 0 input
        └── Keep AST pipeline for accurate spec generation
            (Traceable is input to discovery, not replacement of generation)
```

---

## Key Points to Leave the Meeting With

1. **These are complementary, not competing.** Traceable finds what APIs exist; AST generates accurate specs.
2. **Traceable access is not available today.** We can't block the project on it.
3. **Even with Traceable, the spec pipeline is required.** Someone has to normalize, validate, add governance metadata, and publish.
4. **If access is granted, we plug it in.** The pipeline design already has a Stage 0 that accepts external spec inputs.
5. **The source scanning concern is addressable.** Shallow clone, read-only, in-VPC, discarded immediately. Ask what specifically they need addressed.

---

*Reference doc — March 2026 — Pre-meeting notes*
