# spec-engine — Architecture & Business Review

> Pre-launch review document for application teams and technical leadership.

---

## Executive Summary

spec-engine is an internal developer platform tool that automatically produces validated OpenAPI 3.1 specifications from API source code — without requiring developers to write or maintain documentation manually.

**The problem it solves:** In large engineering organizations, API documentation is almost always out of date. Developers write code; documentation lags. The gap causes integration delays, support incidents, and compliance risk. Traditional approaches — requiring teams to write YAML by hand, or running annotation processors — fail because they depend on developer discipline that doesn't scale.

**The solution:** spec-engine reads source code directly, extracts route and type information through AST analysis, and produces machine-validated specs that can be automatically published to a central API catalog (Explorer). Documentation becomes a byproduct of code, not a separate artifact.

**Current state:** The engine is production-ready. It supports seven API frameworks across four programming languages, passes 365 automated tests at 83% code coverage, and runs as a single CLI command that can be embedded in any CI/CD pipeline.

**Two deployment approaches are presented in this document:**
- **Approach 1 — CSV-Driven Batch Load + Repo-Level CI:** Use the existing API inventory CSV to generate baseline specs for all repos at once, then update each repo's CI pipeline to keep specs current going forward.
- **Approach 2 — Platform-Level CI Enforcement:** Embed spec-engine as a mandatory step directly in the CI/CD platform, requiring no per-repo action from application teams. Requires engagement with the GitHub/CICD Platform Engineering team.

---

## Table of Contents

1. [Business Case & Problem Statement](#1-business-case--problem-statement)
2. [Solution Architecture — Two Deployment Approaches](#2-solution-architecture--two-deployment-approaches)
3. [Platform Engineering Engagement](#3-platform-engineering-engagement)
4. [Supported Frameworks & Language Coverage](#4-supported-frameworks--language-coverage)
5. [Design Principles](#5-design-principles)
6. [Scalability & Performance](#6-scalability--performance)
7. [Cost Model](#7-cost-model)
8. [Security & Compliance](#8-security--compliance)
9. [Reliability & Maintenance](#9-reliability--maintenance)
10. [Integration Points](#10-integration-points)
11. [Rollout Strategy](#11-rollout-strategy)
12. [Risk Register](#12-risk-register)
13. [Decision Points for Leadership](#13-decision-points-for-leadership)
14. [Comparison: Build vs Buy vs Manual](#14-comparison-build-vs-buy-vs-manual)
15. [Success Metrics](#15-success-metrics)
16. [FAQ](#16-faq)
17. [Assumptions & Constraints](#17-assumptions--constraints)

---

## 1. Business Case & Problem Statement

### The API documentation gap

Across a typical large enterprise engineering organization:

- API teams spend **3–8 hours per service** writing initial OpenAPI specs manually
- **60–80% of existing specs are out of sync** with actual code within 6 months of last update
- Onboarding a new consuming team takes **1–2 weeks longer** when spec accuracy cannot be trusted
- Consumer teams report "inaccurate API documentation" in the top 3 causes of integration incidents

### What we're solving

| Problem | Impact | spec-engine approach |
|---|---|---|
| Manual spec writing is slow | 3–8 hours per service | Automated — spec generated in seconds |
| Specs drift from code | API consumers hit undocumented behavior | Spec regenerated from code on every commit |
| Inconsistent field naming, formats | Consumer integration bugs | Structural lint + business-rule validation enforced programmatically |
| No catalog governance | Teams can't discover or reuse APIs | Every generated spec is published to Explorer with required metadata |
| Hard to scale across 500+ services | Manual process doesn't scale | CSV-driven batch load covers all existing repos at once |

### Value delivered

1. **Developer time saved:** Eliminate spec-writing burden from feature teams (~4 hours/service × number of services)
2. **Incident reduction:** Fewer integration incidents from stale docs
3. **Catalog adoption:** API Explorer adoption accelerates when specs are trustworthy and current
4. **Compliance:** Required `x-owner`, `x-gateway`, `x-lifecycle` metadata enforced at generation time — not as a manual checklist
5. **Onboarding velocity:** Consuming teams can integrate faster when specs are accurate
6. **Immediate coverage:** CSV batch load creates baseline specs for the entire inventory on day one, without waiting for teams to update their pipelines

---

## 2. Solution Architecture — Two Deployment Approaches

Two approaches are designed to work together, not in competition. Approach 1 delivers **immediate coverage** of the existing API inventory. Approach 2 delivers **sustained, zero-touch freshness** as code evolves. The recommended path is to execute both in parallel.

---

### Approach 1 — CSV-Driven Batch Load + Repo-Level CI Pipeline Update

This approach has two sequential phases:

**Phase A:** Use the existing API inventory CSV to generate baseline specs for every repo in the catalog on day one.

**Phase B:** Update each repo's existing CI pipeline to include a spec-engine step, so specs stay current on every code commit.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  APPROACH 1 — OVERVIEW                                                       ║
║                                                                              ║
║  PHASE A: Initial Batch Load  (one-time, run by SRE Frameworks team)         ║
║  PHASE B: CI Pipeline Update  (per-repo, self-service or assisted)           ║
╚══════════════════════════════════════════════════════════════════════════════╝


  ┌─────────────────────────────────────┐
  │         API Inventory CSV           │
  │                                     │
  │  api_name, team, gateway,           │
  │  repo_url, framework, lifecycle,    │
  │  owner, env                         │
  └──────────────────┬──────────────────┘
                     │
                     ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │              Batch Orchestrator  (batch_loader.py)              │
  │                                                                 │
  │  1. Read & validate CSV rows                                    │
  │  2. Enrich rows with defaults from org config                   │
  │  3. For each row (parallel workers):                            │
  │       a. git clone --depth 1 <repo_url>  →  /tmp/<repo>        │
  │       b. spec-engine generate                                   │
  │            --repo      /tmp/<repo>                              │
  │            --gateway   <gateway>                                │
  │            --owner     <team>                                   │
  │            --framework <framework>    (if specified in CSV)     │
  │            --out       ./specs/<api_name>.yaml                  │
  │            --publish                                            │
  │       c. Record result (success/fail/confidence) in report      │
  │       d. Clean up /tmp/<repo>                                   │
  │  4. Write batch_report.csv  +  batch_summary.json              │
  └────────────────────────────┬────────────────────────────────────┘
                               │
            ┌──────────────────┼───────────────────┐
            │                  │                   │
            ▼                  ▼                   ▼
    HIGH confidence      MEDIUM confidence    FAILED / MANUAL
    Auto-published       Published +          Flagged in report
    to catalog           review ticket        Team notified
            │                  │
            └──────────────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │  API Explorer Catalog │
          │                      │
          │  Baseline specs for  │
          │  entire inventory    │
          │  live within hours   │
          └──────────────────────┘


  ─────────────────────────────────────────────────────────────────────────────
  PHASE B: CI Pipeline Update  (sustained freshness after initial load)
  ─────────────────────────────────────────────────────────────────────────────

  Option B1: Self-service (team adds step to their existing pipeline)
  ─────────────────────────────────────────────────────────────────────────────

  ┌─────────────────────────────────┐
  │      API Repo Pipeline          │
  │   (GitHub Actions / Jenkins)   │
  │                                 │
  │  existing steps ...             │
  │     build                       │
  │     unit-test                   │
  │     docker-build                │
  │     ─────────────────────────  │
  │  + spec-engine step  (NEW)      │
  │     spec-engine generate \      │
  │       --repo .                  │
  │       --gateway $GATEWAY        │
  │       --publish                 │
  │     ─────────────────────────  │
  │     deploy                      │
  └────────────────┬────────────────┘
                   │ on: push to main
                   ▼
          ┌──────────────────────┐
          │  API Explorer Catalog │
          │  Spec updated within  │
          │  minutes of every     │
          │  merge to main        │
          └──────────────────────┘

  Option B2: Assisted (SRE Frameworks team sends PR to each repo)
  ─────────────────────────────────────────────────────────────────────────────

  batch_pr_creator.py reads CSV  →  for each repo:
    git clone → add workflow file → git commit → gh pr create
  Teams approve PRs at their own pace; CI step active on merge
```

#### CSV file format

The existing API inventory CSV drives the entire batch. The batch orchestrator reads these columns:

```
api_name,team,gateway,repo_url,framework,lifecycle,owner,env,exclude_paths
payments-api,payments-team,kong-prod,https://github.com/org/payments-api,spring,production,@payments-team,,
accounts-api,accounts-team,kong-us,https://github.com/org/accounts-api,fastapi,production,@accounts-team,,**/legacy/**
fraud-service,fraud-team,kong-prod,https://github.com/org/fraud-service,,,@fraud-team,,
risk-api,risk-team,kong-eu,https://github.com/org/risk-api,django,beta,@risk-team,,**/test/**
rewards-ts,rewards-team,kong-prod,https://github.com/org/rewards-ts,nestjs,production,@rewards-team,,
```

| Column | Required | Description |
|---|---|---|
| `api_name` | Yes | Unique API identifier; used for output spec filename |
| `team` | Yes | Owning team name; used as `--owner` |
| `gateway` | Yes | API gateway name; used as `--gateway` |
| `repo_url` | Yes | Full Git clone URL (HTTPS or SSH) |
| `framework` | No | Framework override; auto-detected if blank |
| `lifecycle` | No | `production`, `beta`, `deprecated`; defaults to `production` |
| `owner` | No | `x-owner` override; defaults to `team` |
| `env` | No | Environment tag; defaults to `production` |
| `exclude_paths` | No | Glob patterns to skip (semicolon-separated if multiple) |

#### Batch output

The orchestrator writes two artifacts:

**`batch_report.csv`** — row-per-repo status:
```
api_name,success,routes_found,confidence_high,confidence_medium,confidence_manual,spec_path,error
payments-api,true,84,76,8,0,specs/payments-api.yaml,
accounts-api,true,42,38,4,0,specs/accounts-api.yaml,
fraud-service,false,0,0,0,0,,No routes found — verify --framework
risk-api,true,31,20,9,2,specs/risk-api.yaml,
rewards-ts,true,55,50,5,0,specs/rewards-ts.yaml,
```

**`batch_summary.json`** — aggregate metrics:
```json
{
  "run_date": "2026-03-01T14:00:00Z",
  "total_repos": 150,
  "succeeded": 142,
  "failed": 8,
  "published": 139,
  "review_required": 3,
  "duration_minutes": 28,
  "confidence_breakdown": {
    "all_high": 95,
    "has_medium": 44,
    "has_manual": 3
  }
}
```

---

### Approach 2 — Platform-Level CI Enforcement

In this approach, spec-engine runs automatically on every API repo **without any action required from application teams**. This is achieved by embedding the spec-engine step at the CI/CD platform layer rather than in individual repo pipelines.

This requires a one-time engagement with the **GitHub/CICD Platform Engineering team** to implement the enforcement mechanism at the organization level.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  APPROACH 2 — OVERVIEW                                                       ║
║                                                                              ║
║  spec-engine is enforced at the CI/CD PLATFORM layer.                        ║
║  Application teams do not need to modify their pipelines.                    ║
╚══════════════════════════════════════════════════════════════════════════════╝


  ACTORS & RESPONSIBILITIES:
  ──────────────────────────────────────────────────────────────────────────────

  ┌─────────────────────────┐    Engagement     ┌──────────────────────────────┐
  │  SRE Frameworks Team    │ ◀────────────────▶ │  GitHub / CICD Platform      │
  │                         │                    │  Engineering Team            │
  │  • Owns spec-engine     │                    │                              │
  │  • Publishes            │                    │  • Owns GitHub org settings  │
  │    reusable workflow    │                    │  • Owns Jenkins shared libs  │
  │  • Maintains config     │                    │  • Configures Required       │
  │  • Monitors catalog     │                    │    Workflows or Shared Lib   │
  │    health               │                    │  • Manages runner/agent      │
  └─────────────────────────┘                    │    dependencies              │
                                                 └──────────────────────────────┘
                                                              │
                                                              │ One-time platform setup
                                                              ▼

  ──────────────────────────────────────────────────────────────────────────────
  GitHub Actions: Required Workflow (GitHub Enterprise)
  ──────────────────────────────────────────────────────────────────────────────

  ┌────────────────────────────────────────────────────────────────────────────┐
  │  GitHub Org Settings  (managed by Platform Engineering)                    │
  │                                                                            │
  │  Required Workflows:                                                       │
  │    Repo:    platform-workflows/.github/workflows/spec-engine-required.yml  │
  │    Applies: All repos matching topic "api-service"                         │
  └────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       │  Automatically injected on every
                                       │  push to main / PR merge
                                       ▼
  ┌────────────────────────────────────────────────────────────────────────────┐
  │  spec-engine-required.yml  (maintained by SRE Frameworks in               │
  │                             platform-workflows repo)                       │
  │                                                                            │
  │  jobs:                                                                     │
  │    generate-spec:                                                          │
  │      uses: org/platform-workflows/.github/workflows/spec-engine.yml@main  │
  │      with:                                                                 │
  │        gateway:   ${{ vars.API_GATEWAY }}     # repo-level variable       │
  │        owner:     ${{ vars.API_OWNER }}        # repo-level variable       │
  │        framework: ${{ vars.API_FRAMEWORK }}    # optional override         │
  │      secrets:                                                              │
  │        explorer-token: ${{ secrets.EXPLORER_API_TOKEN }}  # org secret    │
  └────────────────────────────────────┬───────────────────────────────────────┘
                                       │  runs on every API repo automatically
                                       ▼

  ┌────────────────────────────────────────────────────────────────────────────┐
  │  Any API Repo (no pipeline changes needed by the team)                     │
  │                                                                            │
  │  Team's existing pipeline:                                                 │
  │    build → test → docker-build → deploy                                   │
  │                                                                            │
  │  Platform-injected step (runs automatically, in parallel):                 │
  │    spec-engine generate --repo . --gateway ... --publish                   │
  └────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │  Explorer Catalog│
                              │  Updated on      │
                              │  every merge     │
                              └─────────────────┘

  ──────────────────────────────────────────────────────────────────────────────
  Jenkins: Shared Library Mandatory Stage
  ──────────────────────────────────────────────────────────────────────────────

  ┌────────────────────────────────────────────────────────────────────────────┐
  │  Jenkins Shared Library  (managed by Platform Engineering)                 │
  │  Repo: platform-jenkins-lib                                                │
  │                                                                            │
  │  vars/standardPipeline.groovy:                                             │
  │    def call(Map config) {                                                  │
  │      pipeline {                                                            │
  │        stages {                                                            │
  │          stage('Build')     { steps { ... } }                             │
  │          stage('Test')      { steps { ... } }                             │
  │          stage('Generate Spec') {                 // INJECTED              │
  │            steps {                                                         │
  │              specEngine(                                                   │
  │                gateway: config.gateway ?: 'kong-prod',                    │
  │                owner:   config.owner   ?: env.TEAM_NAME,                  │
  │              )                                                             │
  │            }                                                               │
  │          }                                                                 │
  │          stage('Deploy')    { steps { ... } }                             │
  │        }                                                                   │
  │      }                                                                     │
  │    }                                                                       │
  └────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       │  Teams call standardPipeline()
                                       │  in their Jenkinsfile (one line)
                                       ▼

  Team's Jenkinsfile:
  ┌────────────────────────────────────────────────────────────────────────────┐
  │  @Library('platform-jenkins-lib') _                                        │
  │                                                                            │
  │  standardPipeline(                                                         │
  │    gateway: 'kong-prod',                                                   │
  │    owner:   'payments-team',                                               │
  │  )                                                                         │
  └────────────────────────────────────────────────────────────────────────────┘
  spec-engine runs automatically — team has no additional configuration needed
```

#### Per-repo configuration without pipeline changes

Teams provide configuration via GitHub repository variables (not pipeline YAML), so the platform step picks up per-repo settings without code changes:

```
GitHub Repo Settings → Variables:
  API_GATEWAY   = kong-prod
  API_OWNER     = payments-team
  API_FRAMEWORK = spring          (optional; auto-detected if absent)
  API_LIFECYCLE = production
```

For repos in the existing CSV, the Platform Engineering team can bulk-set these variables programmatically via the GitHub API using the inventory data — no manual team action needed.

---

### Approach comparison

| Dimension | Approach 1: CSV Batch + Repo CI | Approach 2: Platform Enforcement |
|---|---|---|
| **Time to first spec** | Hours (batch runs same day) | Days–weeks (platform setup required) |
| **Coverage of existing repos** | Immediate — driven by CSV inventory | Gradual — only repos that push to main |
| **Team involvement** | Low for Phase A; medium for Phase B (add CI step) | Zero — platform injects step automatically |
| **Platform Engineering needed** | No | Yes — one-time setup |
| **Spec freshness model** | On-demand batch + commit-triggered CI | Commit-triggered (always current) |
| **Per-repo customization** | Via `.spec-engine.yaml` or CSV columns | Via GitHub repo variables |
| **Governance enforcement** | Must track who added CI step | Enforced for all repos at platform level |
| **Change management overhead** | Moderate — teams add CI step | Low — transparent to teams |

**Recommendation:** Run both in parallel.
- Start Approach 1 (CSV batch) immediately to populate the catalog.
- Engage Platform Engineering to implement Approach 2 in parallel.
- As Approach 2 rolls out repo by repo, the CI step from Phase B becomes redundant and can be removed from individual pipelines if desired.

---

### End-state architecture (both approaches running)

```
  API Inventory CSV               GitHub Org / Jenkins Platform
        │                                      │
        │  Initial load (one-time)             │  Required Workflow / Shared Lib
        ▼                                      ▼
  Batch Orchestrator ──────────────────────────────────────────────────────────
        │                                                                      │
        │  git clone + spec-engine generate --publish (150 repos in parallel) │
        │                                                                      │
        └──────────────────────────────────────────────────────────────────────┘
                                       │
                                       │  On-going: every repo push triggers
                                       ▼  spec-engine automatically
  ┌────────────────────────────────────────────────────────────────────────────┐
  │                         API Explorer Catalog                               │
  │                                                                            │
  │  payments-api      v2.1   ████████████████ HIGH      updated 2 min ago    │
  │  accounts-api      v1.4   ████████████░░░░ MEDIUM    updated 15 min ago   │
  │  fraud-service     v3.0   ████████████████ HIGH      updated 1 hour ago   │
  │  risk-api          v1.0   ████████░░░░░░░░ MEDIUM    updated 3 hours ago  │
  │  rewards-ts        v2.0   ████████████████ HIGH      updated 22 min ago   │
  │  ... (142 more)                                                            │
  └────────────────────────────────────────────────────────────────────────────┘
                                       │
                        ┌──────────────┴───────────────┐
                        ▼                              ▼
              Consumer Teams                   Platform Dashboard
              API Catalog browsing             Spec freshness metrics
              Integration / SDK gen            Confidence distribution
                                               Coverage %
```

---

## 3. Platform Engineering Engagement

Approach 2 requires a structured engagement with the GitHub/CICD Platform Engineering team. This section defines the scope, asks, and timeline for that engagement.

### What we need from Platform Engineering

| Ask | GitHub Actions | Jenkins | Owner |
|---|---|---|---|
| Publish `spec-engine` reusable workflow in `platform-workflows` repo | Yes | — | SRE Frameworks + Platform Eng |
| Enable "Required Workflows" org policy targeting API repos | Yes (GH Enterprise) | — | Platform Engineering |
| Add `specEngine()` step to `standardPipeline` shared library | — | Yes | Platform Engineering |
| Install Python 3.11 + Node.js 20 on all CI runners/agents | Yes | Yes | Platform Engineering |
| Create org-level secret `EXPLORER_API_TOKEN` | Yes | Yes | Platform Engineering + Security |
| Create org-level variables `API_GATEWAY`, `API_OWNER` defaults | Yes | — | Platform Engineering |
| Bulk-set per-repo variables from the API inventory CSV | Yes | — | SRE Frameworks (scripted) |
| Define repo topic / label scheme to scope which repos get the step | Yes | Yes | Platform Engineering |

### Engagement timeline

```
Week 1–2:   Kickoff with Platform Engineering
            ├── Share spec-engine architecture and requirements
            ├── Agree on runner dependency installation approach
            ├── Agree on org secret and variable naming conventions
            └── Agree on repo scoping strategy (topics, labels, or all-repos)

Week 3–4:   Platform Engineering implements
            ├── Install Python + Node on runner images (or Docker action)
            ├── SRE Frameworks publishes spec-engine reusable workflow
            ├── Platform Engineering wires Required Workflow org policy
            └── Test on 3 pilot repos end-to-end

Week 5–6:   Validation + gradual rollout
            ├── Monitor pipeline run success rate across pilot repos
            ├── Fix runner or token issues
            ├── SRE Frameworks runs CSV batch for existing inventory (Approach 1)
            └── Expand Required Workflow to all API repos

Week 7+:    Steady state
            ├── Platform Engineering monitors runner capacity
            ├── SRE Frameworks monitors catalog coverage and confidence metrics
            └── Quarterly: update spec-engine version in platform-workflows
```

### Reusable workflow design (GitHub Actions)

The SRE Frameworks team publishes and maintains this file in the central platform-workflows repository:

```
org/platform-workflows/.github/workflows/spec-engine.yml
```

```yaml
# Reusable workflow — maintained by SRE Frameworks Team
# Called by Required Workflow policy or by teams directly
name: Generate OpenAPI Spec

on:
  workflow_call:
    inputs:
      gateway:
        description: "API gateway name (e.g. kong-prod)"
        required: false
        type: string
        default: "unknown"
      owner:
        description: "Owning team name"
        required: false
        type: string
        default: "unknown"
      framework:
        description: "Framework override (spring, fastapi, django, express, nestjs, gin, echo)"
        required: false
        type: string
        default: ""
      lifecycle:
        description: "API lifecycle (production, beta, deprecated)"
        required: false
        type: string
        default: "production"
      publish:
        description: "Publish spec to Explorer catalog"
        required: false
        type: boolean
        default: true
      spec-engine-version:
        description: "spec-engine version to use"
        required: false
        type: string
        default: "latest"
    secrets:
      explorer-token:
        description: "Bearer token for Explorer catalog API"
        required: true

jobs:
  generate-spec:
    name: Generate OpenAPI Spec
    runs-on: ubuntu-latest        # or org-managed runner label
    permissions:
      contents: read              # read-only checkout
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 1          # shallow clone is enough

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Install spec-engine
        run: pip install spec-engine==${{ inputs.spec-engine-version }}

      - name: Install validation tools
        run: npm install -g @redocly/cli @stoplight/spectral-cli

      - name: Generate and publish spec
        env:
          EXPLORER_API_TOKEN: ${{ secrets.explorer-token }}
        run: |
          FRAMEWORK_FLAG=""
          if [ -n "${{ inputs.framework }}" ]; then
            FRAMEWORK_FLAG="--framework ${{ inputs.framework }}"
          fi

          spec-engine generate \
            --repo . \
            --gateway "${{ inputs.gateway }}" \
            --owner   "${{ inputs.owner }}" \
            --env     "${{ inputs.lifecycle }}" \
            $FRAMEWORK_FLAG \
            --out     openapi.yaml \
            ${{ inputs.publish && '--publish' || '' }} \
            --verbose

      - name: Upload spec as artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: openapi-spec
          path: openapi.yaml
          retention-days: 30
          if-no-files-found: warn
```

### Required Workflow policy (GitHub Enterprise)

Platform Engineering configures this once at the organization level. It applies to every repo that has the topic `api-service` (or all repos, by policy):

```yaml
# org/platform-workflows/.github/workflows/spec-engine-required.yml
# This file is the Required Workflow — it calls the reusable workflow
# and resolves per-repo variables from GitHub repo variables.
name: Spec Engine (Required)

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  spec:
    uses: org/platform-workflows/.github/workflows/spec-engine.yml@main
    with:
      gateway:   ${{ vars.API_GATEWAY   || 'kong-prod' }}
      owner:     ${{ vars.API_OWNER     || github.repository_owner }}
      framework: ${{ vars.API_FRAMEWORK || '' }}
      lifecycle: ${{ vars.API_LIFECYCLE || 'production' }}
      publish:   ${{ github.ref == 'refs/heads/main' }}
    secrets:
      explorer-token: ${{ secrets.EXPLORER_API_TOKEN }}
```

### Jenkins shared library step

Platform Engineering adds this to the standard Jenkins shared library. Teams get it automatically the next time `standardPipeline` is updated — no Jenkinsfile changes needed:

```groovy
// platform-jenkins-lib/vars/specEngine.groovy
def call(Map config = [:]) {
    withCredentials([string(credentialsId: 'EXPLORER_API_TOKEN', variable: 'EXPLORER_API_TOKEN')]) {
        sh """
            pip install spec-engine --quiet
            npm install -g @redocly/cli @stoplight/spectral-cli --silent

            FRAMEWORK_ARG=""
            if [ -n "${config.framework ?: ''}" ]; then
                FRAMEWORK_ARG="--framework ${config.framework}"
            fi

            spec-engine generate \\
                --repo . \\
                --gateway "${config.gateway ?: env.API_GATEWAY ?: 'kong-prod'}" \\
                --owner   "${config.owner   ?: env.API_OWNER   ?: 'unknown'}"   \\
                \$FRAMEWORK_ARG \\
                --out openapi.yaml \\
                --publish \\
                --verbose
        """
        archiveArtifacts artifacts: 'openapi.yaml', allowEmptyArchive: true
    }
}
```

---

## 4. Supported Frameworks & Language Coverage

| Language | Framework | Scanner approach | Inferrer approach |
|---|---|---|---|
| Java | Spring Boot / Spring MVC | javalang AST; reads `@GetMapping`, `@RequestBody`, etc. | javalang AST; reads `@NotNull`, `@Size`, `@JsonProperty` |
| Python | FastAPI | Python `ast` module; reads `@router.get()` decorators | Python `ast` module; reads Pydantic `BaseModel` class fields |
| Python | Django REST Framework | Python `ast` module; reads ViewSets, `@api_view`, nested routers | Python `ast` module; reads Pydantic / DRF serializers |
| TypeScript | NestJS | Node.js subprocess; `@babel/parser` for decorators | Node.js subprocess; `ts-morph` for interface/class resolution |
| JavaScript | Express | Node.js subprocess; `@babel/parser` for route patterns | Node.js subprocess; `ts-morph` |
| Go | Gin | Go binary or regex fallback | Go binary or regex fallback |
| Go | Echo | Go binary or regex fallback | Go binary or regex fallback |

### Coverage completeness

| Pattern | Handled? | Notes |
|---|---|---|
| Standard CRUD routes | ✓ Full | All methods |
| Path parameters | ✓ Full | `{id}`, `:id`, `<int:pk>` |
| Query parameters | ✓ Full | All frameworks |
| Request body types | ✓ Full | Pydantic, POJOs, interfaces |
| Response types | ✓ Full | Return type annotations |
| Nested/prefixed routes | ✓ Full | `include_router`, `Group()`, DRF nested |
| Enum types | ✓ Full | Java enums, Python Enum |
| Generic types | ✓ Full | `List<T>`, `Optional<T>`, `Map<K,V>` |
| Reflection / dynamic proxies | ✗ Partial | MANUAL confidence; flagged for human review |
| GraphQL | ✗ Not supported | Out of scope |
| gRPC/Protobuf | ✗ Not supported | Out of scope |
| Legacy XML/SOAP | ✗ Not supported | Out of scope |

---

## 5. Design Principles

### 5.1 Static analysis only — no LLM, no runtime

The engine performs **purely static analysis**. There is no LLM inference, application execution, network traffic interception, or reflection-based discovery.

**Why this matters:**
- No data privacy risk (no code sent to external AI services)
- Works in air-gapped build environments
- Fully deterministic — same code produces the same spec every time
- No per-call API costs

#### 5.1.1 What "reads source code" actually means — AST explained

When we say spec-engine "reads source code to generate a spec," a natural question is:
*how does software read code? Doesn't reading code require running it?*

The answer is **Abstract Syntax Tree (AST) parsing** — the same technique compilers
use to understand code before they execute it.

**The analogy: grammar of a sentence**

Consider the English sentence: *"The quick brown fox jumps over the lazy dog."*

A grammar parser breaks this into a tree:

```
Sentence
  ├── Subject:   "The quick brown fox"   (noun phrase)
  ├── Verb:      "jumps"                 (verb)
  └── Object:    "over the lazy dog"     (prepositional phrase)
```

You understand the *structure* of the sentence — who does what — without needing to
watch a real fox jump over a real dog.

An AST does exactly the same thing for source code. Given:

```java
@GetMapping("/v1/accounts")
public List<Account> listAccounts(@RequestParam int page) { ... }
```

The AST parser produces a tree like:

```
Method Declaration
  ├── Annotation:  @GetMapping → path = "/v1/accounts"
  ├── Return type: List<Account>
  ├── Name:        listAccounts
  └── Parameter:
        ├── Annotation: @RequestParam
        ├── Type:       int
        └── Name:       page
```

spec-engine reads this tree and directly answers:
- *"What is the HTTP method?"* → GET (from `@GetMapping`)
- *"What is the path?"* → `/v1/accounts` (from the annotation value)
- *"Are there query parameters?"* → yes, `page` (integer, from `@RequestParam`)
- *"What does it return?"* → a list of `Account` objects

**No code ever runs.** spec-engine never starts the application, never makes a network
call, never connects to a database. It reads the source file the same way a compiler
does — as structured text.

#### 5.1.2 How this works for each language

The AST technique is universal, but each language has its own parser library:

| Language | How spec-engine reads it | What it looks for |
|---|---|---|
| **Java** | `javalang` library parses `.java` files in memory | `@GetMapping`, `@PostMapping`, `@RequestBody`, `@NotNull`, `@Size`, etc. |
| **Python** | Python's built-in `ast` module parses `.py` files | `@router.get()`, `class MyModel(BaseModel)`, `Field(min_length=1)` |
| **TypeScript** | TypeScript compiler (via `ts-morph`) reads `.ts` files | `@Controller()`, `@Get()`, `interface CreateRequest { name: string }` |
| **Go** | Standard `go/ast` library reads `.go` files | `r.GET("/path", handler)`, `type Request struct { Name string \`json:"name"\` }` |

In every case: the source file is parsed into a tree, the tree is walked to find
route declarations and type definitions, and the results are assembled into a spec.

#### 5.1.3 Why AST is better than the alternatives

Three common alternatives exist for automated spec generation, and each has
significant drawbacks compared to AST:

| Approach | How it works | Drawback |
|---|---|---|
| **Runtime / reflection** | Run the app; intercept HTTP traffic or call reflection APIs | Requires a running app, live database, test data; impossible in CI for most services |
| **Regex on source** | Pattern-match annotation strings with regular expressions | Brittle; breaks on multi-line annotations, whitespace variations, comments, generics |
| **LLM (AI) inference** | Send code to a large language model; ask it to infer the spec | Non-deterministic; sends source code to external services; expensive per call; hallucinations |
| **AST parsing (spec-engine)** | Parse source into a structured tree; extract facts from the tree | Requires language-specific parser; some dynamic patterns require manual review |

AST parsing is the same approach used by IDEs (IntelliJ, VS Code), linters, code
formatters, and compilers. It is the most reliable way to understand code structure
without executing it.

#### 5.1.4 What AST parsing cannot do — and how spec-engine handles it

AST parsing works on **what is written in the source file**. It cannot infer:

- Routes registered dynamically at runtime (`routes.push({ path: computePath() })`)
- Types loaded from a database or configuration file at startup
- Behaviour driven by runtime feature flags

When spec-engine encounters these patterns, it does not silently produce a wrong answer.
Instead it sets the **confidence level** to `MANUAL` for that specific route or field,
blocks it from automatic publishing, and flags it in the report. The API team then
either adds a static annotation the engine can read, or authors that section of the
spec manually.

This is the foundation of the confidence-driven governance model described in the
next section.

### 5.2 Confidence-driven governance

Every inferred schema carries a confidence level that controls publish behavior:

```
HIGH confidence   → Auto-published to Explorer catalog
MEDIUM confidence → Published + review ticket created
LOW confidence    → Blocked from publish; human must review
MANUAL confidence → Blocked; human must author that section
```

The system **never silently publishes wrong information**.

### 5.3 Configuration layering

```
CLI flags / Platform Workflow inputs   (highest priority)
    ↓
.spec-engine.yaml                      (repo-level override, checked in to repo)
    ↓
org config.yaml                        (org-wide defaults from config repo)
    ↓
Dataclass defaults                     (safe baseline)
```

In Approach 2, the platform injects the top layer. Teams can still override via `.spec-engine.yaml` in their repo without touching pipeline YAML.

### 5.4 Graceful degradation

Every external tool dependency (Node.js, Go, Redocly, Spectral) is optional. Scanners fall back gracefully when tools are absent. This means the initial batch run succeeds even if some target repos use frameworks where optional tools aren't installed.

### 5.5 Intelligent reuse of existing specs

Some API teams have already written an OpenAPI spec and committed it to their
repository, but never connected it to the Explorer catalog. spec-engine detects
this and can take the fastest, highest-quality path automatically.

#### The problem with "just publish what's there"

A committed spec file that passes format validation looks correct — but may have
been written 18 months ago and never updated since. Publishing a stale spec as
authoritative is worse than publishing no spec, because API consumers trust and
act on the wrong information.

spec-engine therefore never blindly publishes an existing spec. It applies
three quality gates before deciding what to do:

| Gate | Check | If failed |
|---|---|---|
| **Format** | Is the file valid OpenAPI 3.x or Swagger 2.0? | Skip it; generate from AST |
| **Coverage** | Does it cover ≥70% of the routes that AST scanning finds in the current code? | Generate from AST (existing spec is incomplete) |
| **Freshness** | Is the spec newer than 90 days relative to the last code change? | Flag as potentially stale; still publishable with a warning |

#### Three outcomes

```
Existing spec passes all quality gates → Fast-path publish
    Inject required org metadata (x-owner, x-gateway, x-lifecycle)
    Publish in 5–10 seconds instead of 30–90 seconds
    No AST scanning needed

Existing spec passes format + freshness but fails coverage → Hybrid merge
    Run AST generation for structure and schemas (accurate, current code)
    Pull descriptions, examples, servers from existing spec (human-written)
    Publish the best of both: AST accuracy + human richness

No existing spec, or spec fails format/coverage → Full AST pipeline
    Current behaviour; deterministic generation from source code
```

#### Why the hybrid merge is often the best result

The merged spec combines what each source does well:

| | Existing spec | AST-generated | Merged (best) |
|---|---|---|---|
| Route accuracy vs current code | May be stale | Always current | ✓ Current |
| Schema field correctness | May be wrong | ✓ From type annotations | ✓ From annotations |
| Operation descriptions/summaries | ✓ Human-written | None (AST can't infer prose) | ✓ Human-written |
| Request/response examples | ✓ Hand-crafted | None | ✓ Hand-crafted |
| Security scheme definitions | ✓ Often present | Partial | ✓ From existing spec |

#### Impact on the initial batch load

In typical enterprise inventories, 20–35% of repos have a committed spec file.
Of those, roughly half pass the quality gates. Fast-pathing those repos
reduces total Phase 1 batch time by 10–15%, and produces richer catalog
entries for the repos where human descriptions already exist.

### 5.6 Zero application code changes

spec-engine is **read-only**. It never modifies application code, adds annotations or imports, changes build scripts, or requires library dependencies in the target repo. A team can be fully onboarded with zero changes to their application code.

---

## 6. Scalability & Performance

### Single-repo performance

| Framework | Routes | Typical runtime | Primary bottleneck |
|---|---|---|---|
| Spring Boot | 100 routes, 20 types | 3–6 seconds | javalang AST parsing |
| FastAPI | 50 routes, 15 types | 1–3 seconds | Python AST (very fast) |
| Django REST | 80 routes, 12 types | 2–5 seconds | Two-pass URL+views scan |
| NestJS | 60 routes, 10 types | 8–20 seconds | Node.js startup + ts-morph |
| Express | 40 routes, 8 types | 5–12 seconds | Node.js startup per file |
| Gin (regex fallback) | 30 routes, 6 types | 1–3 seconds | Regex scan (fast) |

### Batch load performance (Approach 1)

| Scale | Workers | Include git clone | Estimated time |
|---|---|---|---|
| 50 repos | 8 | Yes (~10s/clone) | 10–20 minutes |
| 150 repos | 16 | Yes | 20–40 minutes |
| 500 repos | 32 | Yes | 45–90 minutes |
| 1,000 repos | 64 (Kubernetes) | Yes | 60–120 minutes |
| 1,000 repos | 64 (pre-cloned) | No | 15–30 minutes |

Git clone time dominates at scale. For large batches, pre-clone repos to a shared volume before running spec-engine.

### Approach 2 CI performance (per-repo, per-push)

Adding the spec-engine step to a typical CI pipeline adds:
- 30–60 seconds for tool installation (Python + Node.js setup, pip install, npm install)
- 3–20 seconds for spec generation (framework-dependent)
- **Total added pipeline time: 45–80 seconds** (runs in parallel with other steps where possible)

Installation time can be reduced to near-zero by using pre-built runner images with spec-engine pre-installed.

---

## 7. Cost Model

### Approach 1 — CSV Batch Load

| Item | Cost |
|---|---|
| Initial batch run (150 repos, 16 workers, 30 min on existing CI) | ~$0 incremental on existing infra |
| Initial batch run on cloud compute (dedicated 8-core runner) | ~$1–3 one-time |
| Nightly re-scan for drift detection (optional) | ~$0.50–1.00/night |
| Developer time: build and run batch orchestrator | Already built (see Developer Guide) |

### Approach 2 — Platform Enforcement

| Item | Cost | Who pays |
|---|---|---|
| Platform Engineering engagement | 2–4 weeks of 1–2 engineers | Platform Engineering team |
| Runner image update (Python + Node.js) | 1–2 days; done once | Platform Engineering |
| Incremental CI runner cost per repo push | 45–80 seconds per push; ~$0.01/push | API team's CI budget |
| Ongoing maintenance of reusable workflow | 1–2 hours/quarter | SRE Frameworks |

### Cost avoided (both approaches combined)

| Manual process replaced | Per service | At 500 services |
|---|---|---|
| Writing initial OpenAPI spec | 4–8 hours | 2,000–4,000 hours |
| Quarterly spec maintenance | 1–2 hours/quarter | 2,000–4,000 hours/year |
| Integration incidents from stale docs | 2–4 hours per incident (reduced 60–80%) | Variable |

At a $75/hour fully-loaded developer rate: **$150K–300K avoided annually** at 500 services.

---

## 8. Security & Compliance

### What the engine accesses

| Resource | Access | Scope |
|---|---|---|
| Source code files | Read-only (local disk / checked-out commit) | Only the repo directory |
| `EXPLORER_API_TOKEN` | Read from environment variable | Used only for catalog HTTPS calls |
| Explorer catalog API | HTTPS POST/PUT | Only the endpoint in `config.catalog_url` |
| Node.js/Go subprocesses | Local subprocess | Reads source files; no network |
| Redocly/Spectral | Local subprocess | Reads generated YAML only |

### What the engine does NOT access

- No outbound calls to AI/LLM services
- Does not write to the source repository
- Does not execute application code
- Does not access databases or runtime credentials
- Does not read environment variables other than `EXPLORER_API_TOKEN`

### Token security model

| Approach | Token storage | Who manages |
|---|---|---|
| Approach 1 (batch) | CI environment variable / Vault-injected | SRE Frameworks team |
| Approach 2 (GitHub Required Workflow) | Org-level GitHub Actions secret `EXPLORER_API_TOKEN` | Platform Engineering + Security |
| Approach 2 (Jenkins) | Jenkins credential store `EXPLORER_API_TOKEN` | Platform Engineering + Security |

The token is never written to logs, config files, or the generated spec. Existence is checked; value is never printed.

### Compliance notes

- **SOX:** Required metadata (`x-owner`, `x-gateway`, `x-lifecycle`) enforced at generation time; non-compliant specs fail the pipeline — no manual checklist
- **GDPR:** Engine reads source annotations, not user data; no PII in generated output
- **Audit trail:** Every spec update is driven by a git commit; full history in SCM
- **Access control:** Publishing requires `EXPLORER_API_TOKEN`; access to this secret controls who can publish to the catalog

---

## 9. Reliability & Maintenance

### Failure modes and mitigations

| Scenario | Impact | Mitigation |
|---|---|---|
| Source file has syntax error | One file skipped; rest of repo processed | Per-file try/except; logged as DEBUG |
| Framework not detected (batch) | Row fails; written to batch_report.csv | `framework` column in CSV; `--framework` override |
| Framework not detected (CI) | Pipeline step fails with clear error | Repo variable `API_FRAMEWORK` override |
| Type not resolvable (dynamic code) | Schema marked MANUAL; spec blocked | Human review flow; ticket created |
| Node.js not installed on runner | Express/NestJS uses Python regex fallback | Platform Engineering installs Node.js on runners |
| Explorer catalog unreachable | `publish` fails; spec written to disk | Retry separately; artifact uploaded from CI |
| `EXPLORER_API_TOKEN` expired | Publish fails with 401 | Alert; secret rotation procedure |
| Config file malformed | Silent fallback to defaults | Designed for resilience |

### Test coverage

365 automated tests covering all scanners, inferrers, CLI commands, and error paths. Coverage gate prevents untested code from merging.

### Version management

| Component | Managed by | Update frequency |
|---|---|---|
| spec-engine Python package | SRE Frameworks | Monthly or as needed |
| Platform reusable workflow version pin | Platform Engineering | Quarterly or on breaking changes |
| Node.js/Go on CI runners | Platform Engineering | Annually (LTS cycle) |
| Redocly / Spectral | SRE Frameworks (npm pin) | As new rules are adopted |

Semantic versioning on spec-engine lets the platform workflow pin to a minor version (`>=1.2,<2.0`) for stability while receiving patches automatically.

---

## 10. Integration Points

### API Explorer catalog

```
spec-engine  →  HTTPS POST/PUT  →  Explorer catalog API
```

- Auth: Bearer token (`EXPLORER_API_TOKEN`)
- Operations: Create (POST) or Update (PUT) based on API title match
- Configuration: `catalog_url` in `org/config.yaml` (committed to platform-workflows repo)

### Source control — read-only

spec-engine reads from local disk (the checked-out commit in CI, or a git-cloned temp directory in batch mode). No SCM API integration is needed for reading.

For the CSV batch (Approach 1), the orchestrator calls `git clone --depth 1 <repo_url>` per row. This requires read access to each repo from the machine running the batch.

### CI/CD systems

| System | Approach 1 | Approach 2 |
|---|---|---|
| GitHub Actions | Orchestrator workflow triggers batch | Required Workflow + Reusable Workflow |
| Jenkins | Orchestrator pipeline script | Shared Library mandatory stage |
| GitLab CI | Shell script in scheduled pipeline | `.gitlab-ci.yml` include from central config |
| Azure DevOps | YAML pipeline with matrix | Pipeline template from central repo |

### Secret management

| System | Approach |
|---|---|
| GitHub Secrets (org-level) | `EXPLORER_API_TOKEN` as org secret; available to all repos via Required Workflow |
| HashiCorp Vault | Inject into CI agent environment at job start |
| AWS Secrets Manager | Fetch at pipeline start; export as environment variable |
| Jenkins Credentials | `withCredentials([string(credentialsId: 'EXPLORER_API_TOKEN', ...)])` |

---

## 11. Rollout Strategy

The two approaches are executed in parallel, not sequentially. Approach 1 delivers immediate value while Approach 2 is being set up by Platform Engineering.

```
  Week 1    Week 2    Week 3    Week 4    Week 5    Week 6    Week 7    Week 8+
  ───────────────────────────────────────────────────────────────────────────────

  APPROACH 1 — CSV BATCH LOAD
  ────────────────────────────
  [Pilot: run CSV batch against 10 repos]
            [Fix issues, tune config]
                      [Full batch: all repos in CSV]
                                [Monitor, fix MANUAL-confidence cases]
                                          [Phase B: assist teams adding CI step]
                                                    ──────────── ongoing ───────▶

  APPROACH 2 — PLATFORM ENFORCEMENT
  ────────────────────────────────────
  [Platform Eng kickoff + dependency install planning]
            [Reusable workflow built + tested]
                      [Required Workflow enabled on pilot repos]
                                [Expand to all API repos]
                                          ──────────── ongoing ───────────────▶

  CATALOG COVERAGE
  ────────────────
  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 10%    (before start)
            ██████████████░░░░░░░░ 65%   (after full batch run)
                      ████████████ 80%   (teams adding CI steps)
                                ██ 90%+  (Required Workflow enforced)
```

### Phase 0 — Pilot (Weeks 1–2)

**Goal:** Validate both approaches against real repos before broad rollout.

Actions:
- Select 10 representative repos from the CSV (mix of Spring, FastAPI, NestJS, Gin)
- Run batch orchestrator against those 10 rows
- Review `batch_report.csv` — check route counts, confidence breakdown, any failures
- In parallel: Platform Engineering installs Python/Node on one runner pool and tests reusable workflow on the same 10 repos

Success criteria:
- ≥ 80% of routes correctly discovered per pilot repo
- ≥ 70% of schemas at HIGH or MEDIUM confidence
- Batch completes in under 5 minutes for 10 repos
- Platform workflow runs end-to-end on at least one pilot repo

---

### Phase 1 — Full CSV Batch Load (Weeks 3–4)

**Goal:** Populate the Explorer catalog with baseline specs for the entire API inventory.

Actions:
- Run batch orchestrator against all rows in the CSV
- Review `batch_summary.json`:
  - Failed rows → add `framework` column or `exclude_paths` and re-run
  - MANUAL-confidence rows → create tickets for owning teams to review
- Publish batch results dashboard to leadership
- Begin assisted Phase B outreach: send PR to top-20 high-traffic API repos adding spec-engine CI step

Success criteria:
- ≥ 90% of CSV rows produce a published spec
- ≤ 5% of specs blocked by MANUAL confidence
- All published specs pass Redocly + Spectral validation

---

### Phase 2 — Platform Enforcement Rollout (Weeks 4–8)

**Goal:** Enable Approach 2 Required Workflow for all API repos.

Actions:
- Platform Engineering enables Required Workflow org policy (scoped to repos with topic `api-service`)
- SRE Frameworks bulk-sets `API_GATEWAY`, `API_OWNER`, `API_LIFECYCLE` repo variables from the CSV for all repos (scripted via GitHub API)
- Monitor spec freshness in Explorer catalog — every repo push should trigger an update

Success criteria:
- 100% of repos with topic `api-service` have Required Workflow enabled
- Spec freshness: every repo's spec updated within 24 hours of the last main branch push
- No new manual CI step additions needed by teams

---

### Phase 3 — Steady State (Month 3+)

- Monthly: review catalog coverage report and confidence trends
- Quarterly: update spec-engine version in platform reusable workflow
- As new frameworks are added to spec-engine: update CSV `framework` column for relevant repos
- Decommission repos from CSV when services are retired (spec marked `lifecycle: deprecated`)

### Adoption enablement

| Activity | Audience | Owner | Timing |
|---|---|---|---|
| Platform Engineering kickoff meeting | Platform Eng team | SRE Frameworks | Week 1 |
| Batch run results dashboard | Leadership | SRE Frameworks | After Phase 1 |
| Self-service CI guide (for Phase B teams) | API team leads | SRE Frameworks | Week 3 |
| Slack channel `#spec-engine-support` | All teams | SRE Frameworks | Week 1 |
| Office hours (bi-weekly) | All teams | SRE Frameworks | Ongoing |
| Pilot team case study | Leadership, all teams | SRE Frameworks | After Phase 0 |

---

## 12. Risk Register

### Technical Risks

| Risk | Likelihood | Impact | Approach | Mitigation |
|---|---|---|---|---|
| Framework version diversity — Spring Boot 2.x vs 3.x, FastAPI 0.95 vs 0.110+, DRF 3.13 vs 3.15 use subtly different annotation patterns | High | Medium | Both | Scanner tested against version ranges; `--framework` flag lets batch override auto-detection; version-specific edge cases logged in `batch_report.csv` |
| Programmatic / dynamic route registration — routes registered in loops, conditionals, or loaded from config files at runtime are invisible to static scanning | Medium | High | Both | Confidence falls to LOW or MANUAL; routes flagged in spec with `x-confidence: manual`; teams add static annotations or supply manual spec |
| Cross-repo type dependencies — request/response types defined in shared library repos not present in the scanned repo; AST resolution fails | High | Medium | Both | Schema resolves to `{}` with MANUAL confidence; `--prefer-file` glob workaround; long-term: pre-clone dependencies declared in `.spec-engine.yaml` |
| Custom annotation wrappers — company-specific `@JsonApiGet` wrapping `@GetMapping`; scanner only recognises standard patterns | Medium | Medium | Both | Scanner extension point documented; SRE Frameworks adds patterns per request; `--framework` override as workaround |
| Code generation artifacts — Protobuf/gRPC-gateway or OpenAPI-codegen files in repo cause scanner to find generated routes, duplicating real ones | Medium | Medium | Both | `exclude_paths` in CSV or `.spec-engine.yaml` to exclude generated directories (e.g., `**/generated/**`) |
| Annotation patterns don't match scanner expectations | Medium | Medium | Both | `prefer_file`, `.spec-engine.yaml` overrides; SRE Frameworks investigates on request |
| Spec accuracy gap vs actual API behaviour — AST says field is `string`, but runtime enforces `enum`; schema is technically correct but incomplete | Medium | Medium | Both | Confidence reflects what was provable; review workflow surfaces gaps; runtime validation (contract tests) is a separate, future layer |
| Large monorepos slow the batch | Low | Medium | Approach 1 | `exclude_paths` in CSV column; per-module invocations for monorepos |
| Node.js dependency unavailable on CI runners | Medium | Medium | Approach 2 | Pre-built runner image with all dependencies; regex fallback in NestJS scanner; Docker-based action as alternative |

### Operational Risks

| Risk | Likelihood | Impact | Approach | Mitigation |
|---|---|---|---|---|
| Git clone fails for some repos (auth, SSH keys) | Medium | Low | Approach 1 | Use GitHub token auth for clones; service account with read-all org access |
| CSV has stale repo URLs or wrong `framework` column | Medium | Medium | Approach 1 | Validate CSV before batch run; `batch_report.csv` flags failures clearly |
| MANUAL-confidence backlog grows faster than teams can review | Medium | High | Both | Weekly triage cadence; SRE Frameworks provides diagnosis; cap MANUAL-pending at 10% before pausing new onboarding |
| Teams create parallel hand-written specs in catalog, diverging from auto-generated ones | Low | Medium | Both | Single source of truth policy: auto-generated spec is the canonical entry; teams may only annotate, not replace |
| Explorer catalog API changes or goes down; publisher fails silently | Low | High | Both | Publisher logs HTTP status and response body; CI step exits non-zero on failure; catalog API changes communicated via standard change management |
| `EXPLORER_API_TOKEN` expires or is rotated | Low | High | Both | Secret rotation runbook; alert on 401 publish failures |
| CSV ownership gap — no formal owner; CSV becomes stale as new APIs are created | Medium | Medium | Approach 1 | Assign explicit CSV owner (SRE Frameworks or API Governance); sync from CMDB/service registry in Phase 3 |
| Some repos use unsupported frameworks (Ruby, PHP) | Medium | Low | Both | Fails gracefully; row flagged in batch report; teams supply manual spec |

### Organizational Risks

| Risk | Likelihood | Impact | Approach | Mitigation |
|---|---|---|---|---|
| Platform Engineering has competing priorities, delays Approach 2 | Medium | Medium | Approach 2 | Approach 1 delivers value independently; Approach 2 is additive; hard deadline agreed in PE engagement kickoff |
| Required Workflow breaks existing CI pipelines | Low | High | Approach 2 | Test on pilot repos; run as non-blocking initially; rollback via org policy toggle |
| Team trust deficit — teams see one wrong schema and stop trusting the catalog entirely | Low | High | Both | Confidence levels are visible in the catalog; HIGH-confidence specs have very low error rate; remediation SLA communicated |
| Spec-engine CI step treated as a build gate; teams disable it when under release pressure | Medium | Medium | Approach 1B/2 | Run as non-blocking for first 90 days; make failures informational, not blocking |

### Security Risks

| Risk | Likelihood | Impact | Approach | Mitigation |
|---|---|---|---|---|
| Broad PAT scope — batch cloning uses one `GIT_TOKEN` with read access to all repos | Medium | Medium | Approach 1 | Scope token to `repo:contents:read` only; rotate quarterly; use GitHub App with installation token for tighter scoping |
| `EXPLORER_API_TOKEN` in CI logs if verbose output is captured incorrectly | Low | Medium | Both | Token injected as env var, not CLI arg; never echoed in spec-engine output; CI log masking enabled via `::add-mask::` |
| Spec content reveals internal API structure to catalog consumers | Low | Low | Both | Explorer catalog access controls are the responsibility of the catalog team; spec-engine publishes only what is already in source code |

---

## 13. Decision Points for Leadership

### Decision 1: Which approaches to pursue

| Option | Description |
|---|---|
| **Both in parallel (recommended)** | CSV batch delivers immediate catalog coverage; Platform enforcement delivers sustained freshness |
| **Approach 1 only** | Faster to start; requires ongoing batch re-runs for freshness; no platform dependency |
| **Approach 2 only** | Zero team friction once set up; slower initial coverage (only repos that push to main) |

**Recommendation:** Both in parallel. They serve different needs and are not mutually exclusive.

---

### Decision 2: Scope of Approach 2 enforcement

| Option | Description | Team impact |
|---|---|---|
| **All repos** | Required Workflow applies to every repo in the GitHub org | Broadest coverage; may hit repos that don't need specs (SDKs, libraries) |
| **Topic-scoped** | Only repos tagged with `api-service` topic | Teams must tag their repos; clean separation |
| **Allowlist** | Only repos explicitly named in a platform config | Most controlled; highest maintenance overhead |

**Recommendation:** Topic-scoped (`api-service`). SRE Frameworks applies the topic to all rows in the CSV when it bulk-sets repo variables.

---

### Decision 3: Enforcement strictness (Approach 2)

| Option | Description |
|---|---|
| **Non-blocking** | Spec generation runs but failure does not block merge/deploy | Low risk; lower adoption pressure |
| **Blocking on main only** | Failure blocks merges to main | Enforces freshness; teams must fix failures before shipping |
| **Blocking on all branches** | Failure blocks any PR | Highest quality signal; potential developer friction |

**Recommendation:** Non-blocking initially; blocking on main after 90 days when teams have stabilized.

---

### Decision 4: Token distribution model

| Model | Description | Risk |
|---|---|---|
| **Org-level GitHub secret** | One shared token for all repos | Token compromise affects all specs |
| **Team-level secret** | Each team manages their own token | More operational overhead; better blast-radius isolation |
| **OIDC / workload identity** | No long-lived token; short-lived OIDC credentials | Best security posture; requires catalog API support |

**Recommendation:** Org-level GitHub secret now; migrate to OIDC if catalog API supports it.

---

### Decision 5: CSV ownership and update process

| Question | Considerations |
|---|---|
| Who owns the API inventory CSV? | SRE Frameworks? API Governance team? CMDB integration? |
| How is it kept current? | Manual updates by API owners? Auto-sync from service registry? |
| What happens when a new API is created? | Does it get added to the CSV? Does Approach 2 cover it automatically? |

**Recommendation:** CSV owned by SRE Frameworks initially; sync from CMDB or service registry as a Phase 3 enhancement. Approach 2 covers new repos automatically once tagged with `api-service`.

---

## 14. Comparison: Build vs Buy vs Manual

### Manual spec writing

| Criterion | Manual | spec-engine |
|---|---|---|
| Initial cost | Low (developer time per spec) | Zero incremental (tool already built) |
| Ongoing cost | High (continuous maintenance) | Very low (automated) |
| Scalability | Does not scale past ~50 services | CSV batch handles 1,000+ in one run |
| Governance | Difficult to enforce | Enforced programmatically in pipeline |

### Commercial tools (Swagger Hub, Stoplight, etc.)

| Criterion | Commercial tool | spec-engine |
|---|---|---|
| Cost | $10K–50K+/year | Internal tool cost only |
| Data privacy | Code sent to SaaS | Local execution; no external data |
| Air-gap compatibility | Usually requires internet | Fully offline capable |
| CSV/bulk import | Not available | Native CSV batch orchestrator |
| Platform enforcement | Requires webhook or integration | Native GitHub Required Workflow |

### Annotation-based generation (Springdoc, FastAPI built-in, etc.)

| Criterion | Annotation | spec-engine |
|---|---|---|
| Accuracy | Very high (runtime) | High (static AST) |
| Code coupling | Framework-specific | Framework-agnostic; zero app code changes |
| Multi-language | One tool per language | Single unified tool for all 7 frameworks |
| Bulk/batch support | None | CSV-driven batch covers entire inventory |
| Platform enforcement | Not possible | Required Workflow / Shared Library |

---

### AI Coding Agents — could Devin build or replace this?

**Short answer: No. Devin is not the right tool for this project.**

Devin and similar autonomous AI coding agents are genuinely useful for
bounded, well-specified software tasks — "implement this function," "fix
this failing test." This project is not that. Below is an honest assessment
of where AI agents fall short for this specific problem.

#### What Devin is good at

| Devin's strengths | Relevance to this project |
|---|---|
| Writing boilerplate code from a clear specification | Useful for scaffolding (small fraction of total effort) |
| Fixing well-described, reproducible bugs | Useful in isolation; not the bottleneck |
| Generating unit tests for known inputs | Useful but requires human to define edge cases |
| Completing one bounded task autonomously | Most tasks here are interconnected, not bounded |

#### Why Devin cannot deliver this project

**1. The hard work is not code generation — it is integration.**

The majority of effort in this project is not writing Python code.
It is:
- Testing against real internal repos to find annotation patterns that
  no synthetic fixture can predict
- Engaging Platform Engineering to configure runner images, org secrets,
  and Required Workflow policies
- Validating generated specs against the real Explorer catalog API
- Coordinating with API teams during the pilot

Devin cannot access internal GitHub repositories, cannot engage a human
Platform Engineering team, and cannot make judgment calls when edge cases
multiply. These are human problems, not code problems.

**2. Devin produces code that still requires expert engineers to review.**

For software that runs in enterprise CI pipelines across hundreds of repos,
every AI-generated line must be reviewed for correctness by an engineer who
deeply understands the language ecosystem. You still need the engineers —
they just spend their time reviewing instead of writing. For a project
where correctness matters more than speed-of-initial-generation, this is
not a meaningful saving.

**3. AST edge cases are only discovered against real repos, not in a sandbox.**

The most time-consuming bugs in AST-based tooling are discovered when
patterns in real code do not match what a test fixture suggests. Examples
from comparable projects:

- A Java annotation parser that works perfectly on examples from the
  documentation fails on the way a specific internal team chains annotations
- A Python route scanner that handles `@app.get()` correctly misses
  `@router.get()` when the router is aliased to a different variable name
- A Go struct tag parser that handles `json:"name"` fails silently on
  `json:"name,omitempty,string"` because of the three-part tag format

Devin, running in its own environment with no access to internal repos,
will not encounter these patterns. The engineer will find them during
Month 3 integration testing and must fix them with deep ecosystem knowledge.

**4. Using Devin would violate the core security premise of the project.**

The reason spec-engine runs in-house rather than using commercial SaaS tools
is that **source code never leaves the enterprise environment**. Directing
an autonomous AI coding agent to build this tool requires giving it read
access to internal source repositories. This is a larger and more sensitive
access grant than any commercial API documentation tool requires, and it
directly contradicts the privacy rationale in Assumption A4.

**5. Devin's cost model is unbounded for iterative, exploratory work.**

Devin charges per software engineering unit (task-hours). A project
requiring dozens of integration test cycles against real repos, each
revealing new edge cases that require research, experimentation, and
architecture decisions, has no predictable ceiling cost. The $500K
proposal has a fixed budget and a clear scope. Devin's costs for
equivalent work are unpredictable and likely higher.

#### The right use of AI assistance in this project

AI coding assistants (GitHub Copilot, Claude Code) ARE used — by the
engineers on the team, in their own development environment, working
with internal repos. The distinction is:

| | AI coding assistant | Devin (autonomous agent) |
|---|---|---|
| Who drives | Human engineer uses AI as accelerator | AI agent works autonomously |
| Code access | Engineer's existing access only | Requires broad granted access |
| Review loop | Engineer reviews every suggestion | Output requires separate review cycle |
| Edge case discovery | Engineer tests against real repos | Cannot access real repos |
| Cost model | Flat subscription (~$20/mo) | Per-task; unbounded |

AI assistance accelerates individual engineers; it does not replace the
engineering team for a project of this integration complexity.

#### Summary comparison

| Criterion | Devin | spec-engine (proposed) |
|---|---|---|
| Access to internal repos | Requires explicit grants to all repos | Runs in-house; no external access |
| Handles integration edge cases | Cannot test against internal systems | Engineers iterate against real repos |
| Platform Engineering engagement | Cannot engage human teams | Dedicated Platform Engineer |
| Cost predictability | Per-task; unbounded | Fixed $500K budget |
| Data sovereignty | Source code leaves enterprise | Code never leaves the environment |
| Production quality | Requires expert review of all output | Engineers own quality end-to-end |
| Ongoing maintenance | New agent session per change | Permanent internal expertise |

---

## 15. Success Metrics

### Primary KPIs

| Metric | Baseline | After Phase 1 (batch) | After Phase 2 (platform) |
|---|---|---|---|
| % of API inventory in Explorer catalog | ~15% | ≥ 90% | ≥ 95% |
| Spec freshness (days since last update) | 180+ days | ≤ 30 days (batch) | ≤ 1 day (commit-triggered) |
| % of specs with HIGH or MEDIUM confidence | Unknown | ≥ 80% | ≥ 90% |
| Time from code commit to published spec | Days–weeks | Hours (batch re-run) | Minutes (CI step) |
| API onboarding time (consumer team) | 1–2 weeks | 3–5 days | 1–2 days |

### Secondary KPIs

| Metric | Description |
|---|---|
| Batch success rate | % of CSV rows producing a published spec (target: ≥ 90%) |
| Required Workflow coverage | % of `api-service` tagged repos with workflow running |
| Integration incidents from stale docs | Track % reduction quarter-over-quarter |
| MANUAL-confidence review cycle time | Time from flagged → reviewed → resolved |

### Observability

- **Batch run:** `batch_report.csv` and `batch_summary.json` after every run
- **CI pipeline:** spec-engine exit code, route count, confidence breakdown in logs
- **Explorer catalog:** spec freshness dashboard; confidence distribution per team
- **Platform Dashboard:** Required Workflow success rate across org

---

## 16. FAQ

**Q: Does spec-engine require teams to change their application code?**

No. It reads existing source files without modification. No annotations or library imports are needed.

---

**Q: Can we start with just the CSV batch and skip the Platform Engineering engagement?**

Yes. Approach 1 (CSV batch + team-added CI steps) is fully independent. Approach 2 is additive and can start later. The CSV batch delivers immediate catalog coverage on day one.

---

**Q: How do we handle repos in the CSV that use unsupported frameworks (Ruby, PHP, etc.)?**

The batch orchestrator writes those rows to `batch_report.csv` with `success=false` and a clear error. Teams for those repos can supply a hand-written spec. The SRE Frameworks team adds scanner support for high-volume frameworks as a roadmap item.

---

**Q: What if the CSV has wrong or missing data (wrong framework, stale repo URL)?**

The batch report clearly identifies every failed row with the error reason. The CSV can be corrected and the batch re-run for only the failed rows (the orchestrator supports a `--retry-failed` mode).

---

**Q: What does the Platform Engineering team actually have to build?**

They need to: (1) install Python 3.11 and Node.js 20 on CI runners, (2) create the org-level `EXPLORER_API_TOKEN` secret, and (3) configure the Required Workflow org policy pointing to the SRE Frameworks-provided reusable workflow. The reusable workflow itself is built and maintained by the SRE Frameworks team. Total Platform Engineering effort: 2–4 weeks.

---

**Q: Will the spec-engine CI step slow down our build pipeline?**

It adds 45–80 seconds when running tool installation. This can be reduced to near-zero with a pre-built runner image. For most pipelines, the spec-engine step can run in parallel with docker build or integration tests, adding no net time to the critical path.

---

**Q: Who owns fixing specs that have MANUAL confidence?**

The API team that owns the service. The batch report and catalog both show which repos and which types have MANUAL confidence, and from which source files the types were attempted. The SRE Frameworks team is available to diagnose unusual annotation patterns.

---

**Q: What happens if a repo is removed or renamed?**

Update the CSV (remove the row or update `repo_url`). The batch orchestrator skips rows that fail to clone gracefully. For Approach 2, if the repo is archived or deleted, the Required Workflow simply stops running. The last published spec remains in the catalog until manually removed.

---

**Q: Can we suppress spec-engine for a specific repo (opt-out)?**

Yes. For Approach 1: remove the row from the CSV. For Approach 2: remove the `api-service` topic from the repo. Teams can also add a `.spec-engine.yaml` with `skip: true` (requires a one-line engine change) to exclude a repo from processing.

---

**Q: Some of our teams already have OpenAPI specs committed to their repos. What happens to those?**

spec-engine detects existing spec files automatically and applies three quality gates
before deciding what to do:

1. **Format check** — is it valid OpenAPI 3.x or Swagger 2.0?
2. **Coverage check** — does it cover at least 70% of the routes that AST scanning finds in the current source code?
3. **Freshness check** — is the spec file newer than 90 days relative to the last source code change?

Based on the results, the engine chooses the best path automatically:

| Situation | What happens |
|---|---|
| Spec passes all three gates | **Fast-path publish** — inject org metadata, validate, publish in under 10 seconds |
| Spec passes format + freshness, but coverage is incomplete | **Hybrid merge** — AST generates the accurate structure and schemas; existing spec contributes human-written descriptions, examples, and security definitions. Better than either source alone. |
| No spec, or spec fails format check | **Full AST pipeline** — standard generation from source code |

The engine never blindly publishes an existing spec. A spec written 2 years ago
and never updated passes format validation but fails the coverage check, because
the current source code has diverged from what was documented. Publishing it as
authoritative would create false confidence for API consumers.

In typical enterprise inventories, 20–35% of repos already have a committed spec.
Of those, roughly half pass the quality gates for fast-path publish.
This makes Phase 1 batch load 10–15% faster overall, while producing richer
catalog entries for repos where teams already invested in human-authored descriptions.

---

**Q: Could we just ask teams to publish their existing specs themselves instead of building this?**

This is exactly the status quo — and it explains why 85%+ of the API inventory has
no catalog entry today. Teams have specs they have not published because connecting
a spec to the catalog is a manual, low-urgency task that never reaches a sprint.
spec-engine solves the human coordination problem, not just the technical one.
Even for repos with a perfect existing spec, the engine handles format upconversion
(Swagger 2.0 → OpenAPI 3.1), injection of required org metadata (`x-owner`,
`x-gateway`, `x-lifecycle`), validation, and publishing automatically.

---

## 17. Assumptions & Constraints

This section formally records the assumptions that underpin the design and the decisions made about scope. Each assumption was explicitly verified against the implementation during pre-launch review (March 2026).

---

### A1 — Zero application code changes

**Assumption:** spec-engine does not modify application source code, add annotations, change build scripts, or open pull requests in application repositories. Teams are onboarded with no changes to their codebase.

**Status: Confirmed, with one noted exception.**

| Deployment path | Touches app repo? | How |
|---|---|---|
| CSV batch loader (`batch_loader.py`) | No | Clones read-only; discards clone after spec is generated |
| Platform Required Workflow (Approach 2) | No | Injected at org level via GitHub settings; no per-repo file changes |
| `set_repo_variables.sh` | No | Sets repo variables via GitHub API; no commits or PRs |
| `batch_pr_creator.py` | **Yes** | Opens a PR to add `.github/workflows/spec-engine.yml` to the repo |

**Decision:** `batch_pr_creator.py` is classified as a **voluntary, team-initiated option only**. It must not be used as part of the standard rollout. Teams that want to self-host the CI step may request the template; SRE Frameworks will not open PRs on their behalf.

The `.spec-engine.yaml` configuration file (repo-level config override) is the only file that application teams may optionally add — and only if they need to customise scanner behaviour. It is never required.

---

### A2 — Publish trigger: push to default branch only, not every build

**Assumption (original):** "On every build we will run the scanner and publish to Explorer."

**Status: Refined.** "Every build" is interpreted as every push to the **default branch** (`main` / `master`), not every branch push or pull request build.

| Trigger | Publishing? | Rationale |
|---|---|---|
| Push to `main` / `master` | Yes — publish to catalog | Stable, reviewed code; the production contract |
| Pull request build | Optional — validate only, no publish | Surfaces issues early without polluting catalog with WIP specs |
| Feature branch push | No | WIP code; incomplete routes; would flood catalog with draft entries |
| Manual `workflow_dispatch` | Yes | Allows ad-hoc re-publish without a code push |

**Implication:** The Explorer catalog always reflects the last merged, reviewed version of the API. There is no lag between merge and catalog update (CI step completes within ~90 seconds of merge).

---

### A3 — No versioning in the catalog (single latest spec per API)

**Assumption:** Each API has one entry in the Explorer catalog representing the current (latest) version. The publish step overwrites the existing entry; there is no per-commit or per-branch version history in the catalog.

**Status: Confirmed for current implementation.** The publisher uses `POST /apis` (create) or `PUT /apis/{id}` (overwrite by title match). The `info.version` field in the spec is sourced from `pom.xml` / `package.json`, changing only when the application bumps its semantic version.

**Open question:** If the Explorer catalog API supports a `/apis/{id}/versions` endpoint, per-commit or per-release versioning becomes feasible with a small publisher change. This requires confirmation from the catalog team.

**Interim option:** Inject the short commit SHA into `info.version` (e.g., `1.4.2-a3f9b1c`) at publish time. This keeps one catalog entry per API but makes each published spec traceable to a specific commit. Requires a `--spec-version` CLI flag addition.

---

### A4 — Application testing is out of scope

**Assumption:** spec-engine does not run application tests, execute application code, or make HTTP requests to any running service.

**Status: Confirmed by design.** All inference is purely static (AST-level):
- No process execution of the target application
- No HTTP calls to the API under scan
- No database connections
- No test framework execution
- Fully safe to run in restricted, air-gapped build environments

Contract testing (verifying the spec against a live API) is a separate, future concern and is explicitly not part of this project.

---

### A5 — Source code is readable and follows framework conventions

**Assumption:** The scanned repositories contain readable source code (not obfuscated, not compiled-only), and use standard framework annotations as documented (e.g., standard Spring `@GetMapping`, standard FastAPI `@router.get`, not internal forks with renamed decorators).

**Status: Assumed, not verified per repo.** Repos with non-standard patterns produce LOW or MANUAL confidence, which is visible in `batch_report.csv` and in the catalog. Custom annotation patterns can be added to the scanner as a roadmap item.

---

### A6 — Services are single-repository

**Assumption:** Each row in the CSV corresponds to one repository containing one API service. Monorepos (multiple services in one repo) are supported only if `exclude_paths` is used to scope the scan to one service module per run.

**Status: Partial limitation.** Monorepo support is on the roadmap. Workaround: add multiple rows to the CSV for the same `repo_url` with different `exclude_paths` and `api_name` values to scan each service module separately.

---

### A7 — Explorer catalog API is stable

**Assumption:** The Explorer catalog REST API (`POST /apis`, `PUT /apis/{id}`) is stable and does not introduce breaking changes without notice.

**Status: Assumed.** The publisher has no API versioning handshake. If the catalog API changes, the publisher will fail with a non-zero exit code and log the HTTP response. A runbook for publisher failures is maintained by SRE Frameworks.

---

### A8 — Build infrastructure supports Python 3.11+ and Node.js 20

**Assumption:** CI runners (GitHub Actions / Jenkins) have Python 3.11+ and Node.js 20 available, either pre-installed or installable at job start.

**Status: Required for full functionality.** Python is required for the core engine. Node.js is required for TypeScript/NestJS/Express schema inference. Without Node.js, the Go and NestJS scanners fall back to Python regex paths with reduced accuracy.

**For Platform Engineering engagement (Approach 2):** Runner image update or Docker action is the responsibility of the Platform Engineering team. See Section 3 for the engagement scope.

---

*Document version: March 2026*
*Status: Pre-launch review draft — updated for two-approach deployment model*
*Authors: SRE Frameworks Team*
