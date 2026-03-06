# spec-engine — Developer Guide

> Automated OpenAPI 3.1 spec generator for multi-language, multi-framework API repositories.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Prerequisites & Installation](#2-prerequisites--installation)
3. [Repository Layout](#3-repository-layout)
4. [Pipeline Architecture](#4-pipeline-architecture)
5. [Configuration Reference](#5-configuration-reference)
6. [CLI Reference](#6-cli-reference)
7. [Framework Scanners](#7-framework-scanners)
8. [Schema Inferrers](#8-schema-inferrers)
   - [8.0 AST-Based Analysis: How It Works](#80-ast-based-analysis-how-it-works)
9. [Assembler, Validator & Publisher](#9-assembler-validator--publisher)
10. [Data Models](#10-data-models)
11. [Testing Guide](#11-testing-guide)
12. [Running Against Thousands of Repos](#12-running-against-thousands-of-repos)
13. [Extending the Engine](#13-extending-the-engine)
14. [Debugging & Troubleshooting](#14-debugging--troubleshooting)
15. [Contributing Checklist](#15-contributing-checklist)

---

## 1. Project Overview

spec-engine performs five automated stages against any API repository:

```
Repository
    │
    ▼
┌─────────────────────────────────────────────┐
│  Stage 1 – Scanner                          │
│  Detects framework, walks source files,     │
│  extracts HTTP routes, params, handler names│
└────────────────────────┬────────────────────┘
                         │  List[RouteInfo]
                         ▼
┌─────────────────────────────────────────────┐
│  Stage 3 – Schema Inferrer (AST-only)       │
│  Resolves request/response types from       │
│  annotations, struct tags, Pydantic fields  │
└────────────────────────┬────────────────────┘
                         │  Dict[str, SchemaResult]
                         ▼
┌─────────────────────────────────────────────┐
│  Stage 4 – Assembler                        │
│  Builds OpenAPI 3.1 YAML with metadata,     │
│  paths, components, x-fields                │
└────────────────────────┬────────────────────┘
                         │  openapi.yaml
                         ▼
┌─────────────────────────────────────────────┐
│  Stage 5 – Validator                        │
│  Redocly lint + Spectral ruleset +          │
│  custom x-field checks                      │
└────────────────────────┬────────────────────┘
                         │  ValidationResult
                         ▼
┌─────────────────────────────────────────────┐
│  Stage 6 – Publisher (optional)             │
│  POST/PUT validated spec to Explorer catalog│
└─────────────────────────────────────────────┘
```

**Supported frameworks:** Spring, FastAPI, Django REST Framework, Express, NestJS, Gin, Echo

**Language runtimes needed at scan time:** Python 3.11+, Node.js 20+ (Express/NestJS/TypeScript), Go 1.21+ (Gin/Echo — optional, regex fallback available)

---

## 2. Prerequisites & Installation

### System requirements

| Tool | Minimum | Purpose |
|---|---|---|
| Python | 3.11 | Engine runtime |
| Node.js | 20 LTS | Express/NestJS/TypeScript scanning |
| Go | 1.21 | Gin/Echo scanning (optional — regex fallback) |
| `@redocly/cli` | latest | OpenAPI structural validation |
| `@stoplight/spectral-cli` | latest | Amex business-rule linting |

### Install engine

```bash
# Clone the repo
git clone <repo-url>
cd spec-engine

# Create virtualenv (recommended)
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Install with all dev dependencies
pip install -e ".[dev]"

# Verify
spec-engine --help
```

### Install optional tools

```bash
# Validation tools (global install)
npm install -g @redocly/cli @stoplight/spectral-cli

# Verify
redocly --version
spectral --version
```

### Install Node.js helper dependencies (for Express/NestJS scanning)

```bash
cd spec_engine/scanner
npm install        # installs @babel/parser
cd ../inferrer
npm install        # installs ts-morph
```

---

## 3. Repository Layout

```
spec-engine/
├── spec_engine/                  # Main package
│   ├── __init__.py
│   ├── cli.py                    # Click command group: generate scan schema assemble validate publish
│   ├── config.py                 # Config dataclass + layered loader
│   ├── models.py                 # RouteInfo, SchemaResult, ParamInfo, Confidence, manifest I/O
│   ├── assembler.py              # Stage 4: builds OpenAPI 3.1 YAML
│   ├── validator.py              # Stage 5: redocly + spectral + x-field checks
│   ├── publisher.py              # Stage 6: HTTP POST/PUT to catalog
│   │
│   ├── scanner/                  # Stage 1 scanners
│   │   ├── __init__.py           # detect_framework() + get_scanner() factory
│   │   ├── base.py               # BaseScanner: _iter_files(), SKIP_DIRS
│   │   ├── spring.py             # Java + javalang AST
│   │   ├── fastapi.py            # Python AST (two-pass)
│   │   ├── django.py             # Python AST (two-pass + nested routers)
│   │   ├── express.py            # Node.js subprocess → express_ast.js
│   │   ├── nestjs.py             # Node.js delegation + Python regex fallback
│   │   ├── gin.py                # Go binary + regex fallback
│   │   ├── express_ast.js        # @babel/parser AST walker
│   │   └── gin_ast.go            # go/ast route extractor
│   │
│   └── inferrer/                 # Stage 3 inferrers
│       ├── __init__.py           # run_inference() orchestrator
│       ├── base.py               # BaseInferrer: resolve_type(), cycle detection, _rank_candidates()
│       ├── python_ast.py         # Pydantic model inference
│       ├── java_ast.py           # javalang class/annotation inference
│       ├── typescript_ast.py     # Node.js subprocess → ts_schema.js
│       ├── go_ast.py             # Go binary + regex struct parsing
│       ├── ts_schema.js          # ts-morph interface → JSON Schema
│       └── go_schema.go          # go/ast struct → JSON Schema
│
├── tests/                        # pytest test suite (365 tests)
│   ├── fixtures/                 # Sample repos per framework
│   │   ├── django/               # urls.py + views.py samples
│   │   ├── fastapi/              # FastAPI app samples
│   │   ├── spring/               # @RestController samples
│   │   └── express/              # Express/NestJS samples
│   ├── test_models.py
│   ├── test_config.py
│   ├── test_scanner_*.py         # One file per scanner
│   ├── test_inferrer_*.py        # One file per inferrer + integration
│   ├── test_assembler.py
│   ├── test_validator.py
│   ├── test_publisher.py
│   ├── test_pipeline.py          # End-to-end
│   └── test_cli.py               # All CLI subcommands
│
├── docs/
│   ├── DEVELOPER_GUIDE.md        # This file
│   └── STAKEHOLDER_OVERVIEW.md   # Leadership/architecture review doc
│
├── config.yaml                   # Default config (edit per environment)
├── .spectral.amex.yaml           # Amex Spectral ruleset
├── setup.py
├── requirements.txt
└── README.md
```

---

## 4. Pipeline Architecture

### Stage 0 — Existing Spec Detection (Pre-flight)

Before any scanning or inference runs, spec-engine checks whether the repository
already contains a committed OpenAPI spec. This pre-flight stage can save significant
time in the initial batch load: roughly 20–35% of enterprise repos already have a
committed spec that was never published to the catalog.

**Entry point:** `spec_engine/detector.py :: detect_existing_spec()`

#### What spec-engine looks for

```python
# Default search paths (checked in priority order)
KNOWN_SPEC_PATHS = [
    "openapi.yaml",  "openapi.yml",  "openapi.json",
    "swagger.yaml",  "swagger.yml",  "swagger.json",
    "api.yaml",      "api.json",
    "docs/openapi.yaml",         "docs/api.yaml",
    "docs/swagger.yaml",
    ".openapi/spec.yaml",
    "src/main/resources/openapi.yaml",          # Spring Boot convention
    "src/main/resources/static/openapi.yaml",
    "src/main/resources/swagger.yaml",
]
```

Custom paths can be added via `existing_spec_paths:` in `.spec-engine.yaml`.

#### Decision algorithm — three outcomes

```
Repo contains a committed spec file?
│
├── No → run full AST pipeline (Stage 1–6, current behaviour)
│
└── Yes
      │
      ├── Step A: Format validation
      │     Is it valid OpenAPI 3.x or Swagger 2.0?
      │     ├── No  → log WARNING, fall back to full AST pipeline
      │     └── Yes → continue
      │
      ├── Step B: Coverage check
      │     Run Stage 1 scanner (routes only, no inference — fast)
      │     Compare AST route set vs routes in existing spec
      │     Coverage = (routes in spec) / (routes found by AST)
      │
      │     Coverage < 70%  → existing spec is incomplete
      │     │                  run full AST pipeline
      │     │                  optionally merge descriptions (hybrid mode)
      │     │
      │     Coverage ≥ 70%  → continue to Step C
      │
      ├── Step C: Staleness check
      │     spec_mtime = git log --format="%ci" -1 -- <spec_file>
      │     code_mtime = git log --format="%ci" -1 -- src/
      │     days_behind = (code_mtime - spec_mtime).days
      │
      │     days_behind > freshness_threshold (default: 90)
      │     → flag as STALE in x-spec-source metadata
      │     → still usable but publish with staleness warning
      │
      └── Step D: Mode decision
            Mode = config.existing_spec_mode
            │
            ├── "fast-path" → inject required x- fields, validate, publish
            │                 skip Stage 1–5 entirely
            │
            ├── "merge"     → run Stage 1–3 for structure + schemas
            │                 pull descriptions, examples, servers,
            │                 security schemes from existing spec
            │                 publish merged result
            │
            └── "skip"      → ignore existing spec, run full AST pipeline
```

#### Mode comparison

| Mode | When to use | What is published | Stage 1–3 run? |
|---|---|---|---|
| `fast-path` | Existing spec is trusted, current, and well-maintained | Existing spec + injected x- fields | No |
| `merge` | Existing spec has good descriptions but may be incomplete or slightly stale | AST-derived structure + existing spec enrichment | Yes |
| `skip` | Existing spec is known to be generated/outdated; always regenerate | Full AST-generated spec | Yes |
| `auto` (default) | Let the engine decide based on coverage and staleness | Fast-path if quality gates pass; merge otherwise | Conditional |

#### Why "just publish" is not the default

A spec file that passes Spectral/Redocly validation is **format-correct** but
not necessarily **content-correct**. A spec written 18 months ago looks completely
valid yet every schema could be wrong. Publishing it to the catalog as authoritative
is worse than no spec, because it creates false confidence for API consumers.

The coverage check (Step B) is the critical gate. It cross-references the existing
spec against what the AST scanner actually finds in the current source code. A spec
that misses 35% of routes is not a candidate for fast-path publish, regardless of
how well-formatted it is.

#### The hybrid merge — what gets taken from where

The `merge` mode combines the accuracy of AST inference with the richness of
human-authored content:

| Field | Source | Reason |
|---|---|---|
| HTTP methods and paths | **AST scanner** (authoritative) | Existing spec may have obsolete paths |
| Path/query parameters | **AST scanner** (authoritative) | Annotation-derived; more accurate than prose |
| Request body schema | **AST inferrer** (authoritative) | Field types and constraints from current code |
| Response schema | **AST inferrer** (authoritative) | Return type from current code |
| `summary`, `description` | **Existing spec** (if present) | Human-written; AST cannot infer prose |
| `examples` in bodies | **Existing spec** (if present) | Hand-crafted; AST cannot generate |
| `servers` section | **Existing spec** (preferred) | Hard to derive from code |
| `securitySchemes` | **Existing spec** (preferred) | Often not in annotations |
| `info.description` | **Existing spec** (preferred) | High-level API narrative |
| `externalDocs` | **Existing spec** (if present) | Documentation links |
| `x-owner`, `x-gateway`, `x-lifecycle` | **Config / CLI** (always injected) | Org governance metadata |

This produces a spec that is accurate (structure from code) and rich
(documentation from humans) — better than either source alone.

#### Detecting framework-generated specs

Some frameworks auto-generate spec files that are committed to the repo:

| Source | Location | Quality | Recommended mode |
|---|---|---|---|
| SpringDoc / Springfox | `src/main/resources/static/openapi.yaml` | High (runtime-generated) | `fast-path` if recent |
| FastAPI export | `openapi.json` (often in root or `docs/`) | High | `fast-path` if recent |
| `drf-spectacular` export | `schema.yaml` | High | `fast-path` if recent |
| Hand-written | Any | Variable | `merge` (safe default) |
| Another tool (Postman export, etc.) | Various | Low-Medium | `merge` or `skip` |

For framework-generated specs, coverage will typically be very high (>95%).
Combined with a recent staleness check, these are excellent fast-path candidates.

#### Configuration

```yaml
# config.yaml or .spec-engine.yaml
existing_spec_mode: auto          # skip | fast-path | merge | auto
existing_spec_freshness: 90       # days; flag as stale if code newer than spec by this
existing_spec_min_coverage: 0.70  # 0.0–1.0; below this threshold → fall back to AST
existing_spec_paths:              # additional search paths (appended to defaults)
  - "api-contracts/openapi.yaml"
  - "internal/docs/swagger.yaml"
```

#### CLI flag

```bash
# Override mode for a single run
spec-engine generate --repo . --existing-spec-mode fast-path
spec-engine generate --repo . --existing-spec-mode skip    # always regenerate
spec-engine generate --repo . --existing-spec-mode merge
```

#### Output metadata

When an existing spec is detected and used, the published spec includes:

```yaml
info:
  x-spec-source: existing       # existing | ast | merged
  x-existing-spec-path: docs/openapi.yaml
  x-existing-spec-coverage: 0.94   # fraction of AST routes found in existing spec
  x-existing-spec-age-days: 22     # days since spec was last committed
  x-spec-freshness: current        # current | stale (if age > freshness_threshold)
```

This makes it transparent in the catalog exactly how each spec was produced.

#### Batch loader integration

The batch orchestrator reports existing spec detection per row:

```
batch_report.csv columns added:
  existing_spec_found     true/false
  existing_spec_mode_used fast-path | merge | skip | none
  existing_spec_coverage  0.0–1.0
  existing_spec_age_days  integer
```

Fast-path repos complete in 5–10 seconds instead of 30–90 seconds, significantly
reducing total batch run time when a large fraction of the inventory has existing specs.

---

### Stage 1 — Scanner

**Entry point:** `spec_engine/scanner/__init__.py :: get_scanner()`

```python
from spec_engine.scanner import get_scanner
from spec_engine.config import Config

scanner = get_scanner("/path/to/repo", Config())
routes = scanner.scan()          # List[RouteInfo]
```

**Framework detection order:**
1. `go.mod` present → `gin` (or `echo` if labstack/echo in content)
2. `pom.xml` or `build.gradle` → `spring`
3. `requirements.txt` or `pyproject.toml` with `django` → `django`
4. `requirements.txt` or `pyproject.toml` with `fastapi` → `fastapi`
5. `package.json` with `@nestjs` → `nestjs`
6. `package.json` → `express`
7. Otherwise → `unknown` (raises ValueError)

Override via `--framework` flag or `framework:` in `config.yaml`.

**Skip directories (built-in):**
```python
SKIP_DIRS = {
    ".git", ".hg", ".svn",
    "node_modules", "__pycache__", ".pytest_cache",
    "target", "build", "dist", ".gradle",
    ".idea", ".vscode", "vendor",
}
```

Add custom exclusions via `exclude_paths` in `config.yaml`:
```yaml
exclude_paths:
  - "**/generated/**"
  - "**/legacy/**"
  - "docs/**"
```

---

### Stage 3 — Schema Inferrer

**Entry point:** `spec_engine/inferrer/__init__.py :: run_inference()`

```python
from spec_engine.inferrer import run_inference

schemas = run_inference(routes, repo_path, framework, config)
# Returns Dict[str, SchemaResult]
```

**Type resolution algorithm (in BaseInferrer.resolve_type):**

```
resolve_type("CreateAccountRequest")
  ├── Is it a generic? → unwrap outer, recurse on inner
  │     List<Account>    → array of Account schema
  │     Map<K,V>         → object with additionalProperties
  │     Optional<T>      → nullable T schema
  │
  ├── Is it a primitive? → return inline schema
  │     string / String / str / int / Integer / bool ...
  │
  ├── Is it in visited set? → cycle detected → return $ref (no recursion)
  │
  ├── Is it in schema_registry? → return cached result
  │
  └── Find source file → extract fields → cache → return SchemaResult
```

**Confidence levels:**

| Level | Meaning | Auto-publish? |
|---|---|---|
| `HIGH` | All fields fully resolved from type annotations | Yes |
| `MEDIUM` | Partial resolution; some fields unknown | Yes (after review) |
| `LOW` | Heuristic fallback used | No |
| `MANUAL` | Type unresolvable (dynamic code, reflection) | No |

---

### AST-Based Analysis — Technical Foundations

Both the Scanner (Stage 1) and the Schema Inferrer (Stage 3) are built on
**Abstract Syntax Tree (AST) parsing**. Understanding what an AST is and how each
language produces one is essential to understanding how spec-engine works and how
to extend it.

#### What is an Abstract Syntax Tree?

When a compiler or interpreter reads source code it first converts raw text into a
structured, hierarchical data model that captures the meaning of the code without
the noise of whitespace, comments, or operator precedence rules. This data model is
the **Abstract Syntax Tree**.

```
Source text                       AST (simplified)
─────────────────────             ──────────────────────────────────────
@GetMapping("/accounts")          MethodDeclaration
public List<Account>                ├── annotation: GetMapping
  listAccounts(                   │     └── value: "/accounts"
    @RequestParam int page) {     ├── returnType: List<Account>
  return accountService.all();    ├── name: "listAccounts"
}                                 └── parameters:
                                        └── Parameter
                                              ├── annotation: RequestParam
                                              └── type: int
                                              └── name: "page"
```

The tree makes it trivial to answer questions like:
- "What is the HTTP path for this method?" → walk to `annotation.GetMapping.value`
- "What are the request parameters?" → walk to `parameters[*].annotation`
- "What is the return type?" → walk to `returnType`

Without an AST, answering these questions with regex would require handling
thousands of whitespace, comment, and formatting variations. The AST collapses
all of those surface differences into a single, uniform structure.

#### How each language produces an AST

spec-engine uses a different library per language, but the traversal pattern
is the same in every case: **walk the tree, match node types, extract values**.

| Language | AST library | Where it runs | Notes |
|---|---|---|---|
| Python | `ast` (stdlib) | In-process | Zero dependencies; parses Python source natively |
| Java | `javalang` (pip) | In-process | Pure-Python Java parser; no JVM required |
| TypeScript | `ts-morph` (npm) | Node.js subprocess | Wraps the TypeScript compiler's own type-checker |
| Go | `go/ast` (stdlib) | Compiled Go binary | Called as a subprocess; outputs JSON to stdout |

#### The Scanner's use of AST (Stage 1)

Framework scanners use AST to find **route declarations** — the annotations or
function-call patterns that define HTTP endpoints.

**Python example (FastAPI scanner):**

```python
import ast

source = open("routes.py").read()
tree = ast.parse(source)

for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        for decorator in node.decorator_list:
            # Match @router.get("/path") or @app.post("/path")
            if isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Attribute):
                    http_method = decorator.func.attr.upper()  # "get" → "GET"
                    if http_method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                        path = decorator.args[0].s  # "/v1/accounts"
                        handler = node.name          # "list_accounts"
```

**Java example (Spring scanner):**

```python
import javalang

tree = javalang.parse.parse(open("AccountController.java").read())

for _, method in tree.filter(javalang.tree.MethodDeclaration):
    for annotation in method.annotations:
        if annotation.name in ("GetMapping", "PostMapping", "PutMapping", ...):
            # annotation.element is the path string value
            path = _get_annotation_value(annotation, "value") or "/"
```

**Go example (Gin scanner — via compiled binary):**

The Go scanner can't use a Python library because no Python-native Go parser
exists with sufficient quality. Instead, a small Go binary (`gin_ast.go`) is
compiled once and called as a subprocess:

```go
// gin_ast.go — compiled to a binary, called as subprocess
package main

import (
    "go/ast"
    "go/parser"
    "go/token"
)

func extractRoutes(filename string) []Route {
    fset := token.NewFileSet()
    f, _ := parser.ParseFile(fset, filename, nil, 0)

    ast.Inspect(f, func(n ast.Node) bool {
        call, ok := n.(*ast.CallExpr)
        if !ok { return true }
        // Match r.GET("/path", handler) or v1.POST("/accounts", ...)
        if sel, ok := call.Fun.(*ast.SelectorExpr); ok {
            method := sel.Sel.Name  // "GET", "POST", ...
            if isHTTPMethod(method) && len(call.Args) >= 1 {
                path := extractStringLit(call.Args[0])
                // emit route ...
            }
        }
        return true
    })
}
```

The binary outputs JSON to stdout; the Python scanner reads and parses it.
If the binary is unavailable, a Python regex fallback activates automatically.

#### The Inferrer's use of AST (Stage 3)

Schema inferrers use AST to find **type definitions** — the class, struct, or
interface declarations that describe request/response bodies.

The traversal pattern is different from the scanner: instead of looking for
decorated methods, it looks for named type declarations and extracts their fields.

**Python — Pydantic model resolution:**

```python
import ast

source = open("models.py").read()
tree = ast.parse(source)

for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == "CreateAccountRequest":
        for item in node.body:
            if isinstance(item, ast.AnnAssign):  # name: str = Field(...)
                field_name = item.target.id        # "name"
                field_type = item.annotation       # ast.Name("str")
                default    = item.value            # ast.Call(Field, ...)
```

**Java — javalang class resolution:**

```python
import javalang

tree = javalang.parse.parse(open("CreateAccountRequest.java").read())

for _, cls in tree.filter(javalang.tree.ClassDeclaration):
    if cls.name == "CreateAccountRequest":
        for field in cls.fields:               # FieldDeclaration
            type_name = field.type.name        # "String", "Integer", ...
            fname     = field.declarators[0].name
            for ann in field.annotations:      # @NotNull, @Size(min=1, max=50)
                # ann.name = "NotNull"
                # ann.element = [MemberValuePair("min", "1"), ...]
```

**Go — struct tag parsing (via binary):**

```go
// go/ast struct → JSON Schema
for _, field := range structType.Fields.List {
    tag := ""
    if field.Tag != nil {
        tag = field.Tag.Value  // `json:"name" validate:"required,min=1"`
    }
    jsonName  := parseJsonTag(tag)      // "name"
    required  := hasValidateRequired(tag) // true
    minVal    := parseValidateMin(tag)   // 1.0
}
```

**TypeScript — ts-morph interface resolution:**

```typescript
// ts_schema.js — Node.js companion script
import { Project } from "ts-morph";

const project = new Project();
const sf = project.addSourceFileAtPath(process.argv[2]);

for (const iface of sf.getInterfaces()) {
    if (iface.getName() === targetType) {
        for (const prop of iface.getProperties()) {
            const name     = prop.getName();           // "accountName"
            const type     = prop.getType().getText(); // "string"
            const optional = prop.hasQuestionToken();  // → nullable
        }
    }
}
// Output as JSON to stdout → Python reads and converts to JSON Schema
```

#### Cycle detection during AST inference

Recursive types (a `Comment` that contains a list of `Comment` replies) would
cause infinite recursion if not handled. `BaseInferrer` maintains a `_visiting`
set:

```python
def resolve_type(self, type_name: str) -> SchemaResult:
    if type_name in self._visiting:
        # Cycle detected — return a $ref to break the loop
        return SchemaResult(
            json_schema={"$ref": f"#/components/schemas/{type_name}"},
            confidence=Confidence.HIGH,
        )
    self._visiting.add(type_name)
    try:
        result = self._extract_fields(type_name)
    finally:
        self._visiting.discard(type_name)
    return result
```

This mirrors what Java/TypeScript compilers do internally: deferred resolution
using a forward reference until the full type is known.

#### When regex is used instead of AST

Regex fallback activates when the AST dependency is unavailable:

| Situation | Fallback | Confidence penalty |
|---|---|---|
| `node` not installed → NestJS scanner | Python regex on `.ts`/`.js` files | None for route paths; schema MANUAL |
| Go binary not compiled → Gin scanner | Python regex on `.go` files | LOW on complex path groups |
| `go/ast` binary fails → Go inferrer | Python regex on struct declarations | MEDIUM for simple structs; MANUAL for complex |
| `ts-morph` unavailable → TS inferrer | No fallback; returns empty | MANUAL |

**Regex is always a degraded path.** It cannot handle multi-line declarations,
complex generic types, or annotations that span multiple lines.
The AST path is always preferred when dependencies are available.

---

### Stage 4 — Assembler

**Entry point:** `spec_engine/assembler.py :: assemble()`

```python
from spec_engine.assembler import assemble

yaml_str = assemble(routes, schemas, repo_path, config)
Path("openapi.yaml").write_text(yaml_str)
```

**Auto-detected metadata:**
- `info.title` — from `pom.xml <artifactId>`, `package.json name`, or repo directory name
- `info.version` — from `pom.xml <version>`, `package.json version`, or `"1.0.0"`
- `x-owner` — from `CODEOWNERS` file (first non-comment `@team` entry)

**operationId generation rules:**

| Method | Path | operationId |
|---|---|---|
| `GET` | `/v1/accounts` | `getAccounts` |
| `POST` | `/v1/accounts` | `createAccounts` |
| `GET` | `/v1/accounts/{id}` | `getAccountsById` |
| `PUT` | `/v1/accounts/{id}` | `updateAccountsById` |
| `DELETE` | `/v1/accounts/{id}/activate` | `deleteAccountsByIdActivate` |
| `PATCH` | `/v1/accounts/{id}` | `patchAccountsById` |

Version path segments (`v1`, `v2`, `v3`) are omitted from operationId.
Duplicate operationIds within the same spec are suffixed with `_2`, `_3`, etc.

**Standard error responses added to every operation:**
```yaml
400:
  description: Bad Request
  content: { application/json: { schema: { $ref: '#/components/schemas/Error' } } }
401:
  description: Unauthorized
403:
  description: Forbidden
404:
  description: Not Found
500:
  description: Internal Server Error
```

---

### Stage 5 — Validator

```python
from spec_engine.validator import validate

result = validate("openapi.yaml", config)
if not result.passed:
    for err in result.errors:
        print(f"ERROR: {err}")
```

**Three validation passes (all non-blocking if tool absent):**

1. **Redocly structural check** — `redocly lint openapi.yaml --format json`
2. **Spectral ruleset** — `spectral lint openapi.yaml --ruleset .spectral.amex.yaml --format json`
3. **Custom x-field check** — validates presence of `x-owner`, `x-gateway`, `x-lifecycle` in `info`

---

### Stage 6 — Publisher

```python
from spec_engine.publisher import publish

result = publish("openapi.yaml", config, dry_run=False)
```

**Environment variable required:**
```bash
export EXPLORER_API_TOKEN="eyJhbGciOiJSUzI1NiJ9..."
```

**Config fields required:**
```yaml
catalog_url: "https://catalog.example.com/api/v1"
```

**HTTP behavior:**
- `GET /apis` → find by title match
- If found: `PUT /apis/{id}` → update existing spec
- If not: `POST /apis` → create new spec

---

## 5. Configuration Reference

### Config fields

| Field | Type | Default | Description |
|---|---|---|---|
| `gateway` | str | `"unknown"` | API gateway name (e.g. `kong-prod`) |
| `env` | str | `"production"` | Deployment environment |
| `owner` | str | `"unknown"` | Owning team name |
| `strict_mode` | bool | `true` | Fail pipeline if gateway is still `"unknown"` |
| `required_x_fields` | list | `["x-owner","x-gateway","x-lifecycle"]` | Fields required in OpenAPI info block |
| `exclude_paths` | list | `[]` | Glob patterns to exclude from scanning |
| `framework` | str | `""` | Override framework auto-detection |
| `prefer_file` | str | `""` | fnmatch glob to prefer when multiple files define same type |
| `out` | str | `"./openapi.yaml"` | Output spec path |
| `lifecycle` | str | `"production"` | Value for `x-lifecycle` field |
| `catalog_url` | str | `null` | Publisher catalog endpoint |
| `servers` | list | `[{url: "/"}]` | OpenAPI servers block |
| `existing_spec_mode` | str | `"auto"` | `auto` \| `fast-path` \| `merge` \| `skip` — see Stage 0 |
| `existing_spec_freshness` | int | `90` | Days; flag as stale if source code is newer than spec by this amount |
| `existing_spec_min_coverage` | float | `0.70` | Minimum fraction of AST routes that must appear in existing spec; below this → fall back to AST |
| `existing_spec_paths` | list | `[]` | Additional search paths appended to built-in defaults |

### Config file (`config.yaml`)

```yaml
gateway: kong-prod
env: production
owner: payments-team
lifecycle: beta
catalog_url: https://catalog.example.com/api/v1

strict_mode: true
required_x_fields:
  - x-owner
  - x-gateway
  - x-lifecycle

exclude_paths:
  - "**/test/**"
  - "**/generated/**"
  - "docs/**"

out: ./specs/openapi.yaml

servers:
  - url: https://api.example.com
    description: Production
  - url: https://api-staging.example.com
    description: Staging
```

### Repo-level override (`.spec-engine.yaml`)

Place at the root of any API repo to override global config for that repo:

```yaml
# .spec-engine.yaml
gateway: kong-eu
owner: eu-payments-team
framework: spring          # force framework if detection is ambiguous
prefer_file: "*/dto/*.java"  # prefer DTO files for type resolution
```

### Priority order (highest → lowest)

1. CLI flags (`--gateway`, `--framework`, etc.)
2. Repo `.spec-engine.yaml`
3. `config.yaml` (via `--config` flag or `./config.yaml`)
4. Dataclass defaults

---

## 6. CLI Reference

### `generate` — Full pipeline

```bash
spec-engine generate \
  --repo       /path/to/api-repo \
  --config     config.yaml \
  --gateway    kong-prod \
  --owner      my-team \
  --env        production \
  --framework  spring \
  --out        ./specs/openapi.yaml \
  --publish \
  --dry-run \
  --verbose
```

**Exit codes:**
- `0` — Success (spec written and validated)
- `1` — No routes found, or validation failed

---

### `scan` — Routes only

```bash
spec-engine scan \
  --repo       /path/to/api-repo \
  --config     config.yaml \
  --framework  fastapi \
  --manifest   ./manifest.json \
  --verbose
```

Writes a JSON manifest of all discovered routes. Use this to inspect what the scanner found before running inference.

**Sample manifest output:**
```json
{
  "repo": "/path/to/api-repo",
  "framework": "fastapi",
  "generated_at": "2026-03-01T14:23:00Z",
  "routes": [
    {
      "method": "GET",
      "path": "/v1/accounts",
      "handler": "account_list",
      "file": "app/routers/accounts.py",
      "line": 15,
      "framework": "fastapi",
      "request_body_type": null,
      "response_type": "Account",
      "params": []
    }
  ]
}
```

---

### `schema` — Type inference only

```bash
spec-engine schema \
  --manifest  ./manifest.json \
  --repo      /path/to/api-repo \
  --config    config.yaml \
  --out       ./schemas.json \
  --verbose
```

Reads the manifest written by `scan` and infers JSON Schemas for all referenced types.

---

### `assemble` — YAML generation only

```bash
spec-engine assemble \
  --manifest  ./manifest.json \
  --repo      /path/to/api-repo \
  --gateway   kong-prod \
  --owner     my-team \
  --out       ./openapi.yaml \
  --verbose
```

---

### `validate` — Lint only

```bash
spec-engine validate openapi.yaml --config config.yaml --verbose
```

**Output example:**
```
ERROR: [redocly] Operation must have at least one 2xx response. (line 45)
WARN:  [spectral] operationId should be camelCase. (line 67)
INFO:  [x-fields] All required x-fields present.
Validation failed (1 error(s)).
```

---

### `publish` — Upload to catalog

```bash
export EXPLORER_API_TOKEN="your-token-here"
spec-engine publish openapi.yaml \
  --config  config.yaml \
  --dry-run \
  --verbose
```

---

## 7. Framework Scanners

### Spring (Java)

**Detected annotations:**

| Annotation | HTTP method | Example |
|---|---|---|
| `@GetMapping("/path")` | GET | `@GetMapping("/v1/accounts")` |
| `@PostMapping("/path")` | POST | `@PostMapping("/v1/accounts")` |
| `@PutMapping("/path/{id}")` | PUT | |
| `@DeleteMapping("/path/{id}")` | DELETE | |
| `@PatchMapping("/path/{id}")` | PATCH | |
| `@RequestMapping(value="/path", method=RequestMethod.GET)` | any | |

**Parameter annotations:**

| Annotation | OpenAPI location | Example |
|---|---|---|
| `@PathVariable("id")` | path | `@PathVariable("accountId") String id` |
| `@RequestParam("page")` | query | `@RequestParam(required=false) int page` |
| `@RequestHeader("Authorization")` | header | |
| `@CookieValue("session")` | cookie | |
| `@RequestBody` | requestBody | `@RequestBody CreateAccountRequest body` |

**Additional metadata extracted:**
- `@Deprecated` → `deprecated: true` on operation
- `@PreAuthorize("hasRole('ADMIN')")` → `auth_schemes` field
- `@JsonProperty("custom_name")` → field name override in schema

---

### FastAPI (Python)

**Detected patterns:**

```python
@app.get("/v1/accounts", response_model=List[Account])
async def list_accounts(
    page: int = Query(0, ge=0),                    # query param
    account_id: UUID = Path(...),                   # path param
    auth: str = Header(...),                        # header param
    body: CreateAccountRequest = Body(...)          # request body
) -> AccountResponse:
```

**Router prefix resolution:**
```python
router = APIRouter(prefix="/v1/accounts")

@router.get("/{account_id}")        # → /v1/accounts/{account_id}
async def get_account(account_id: UUID):
    ...

app.include_router(router)           # Links router to app
```

**Parameter skip list:**
- Skipped by name: `self`, `cls`, `db`, `session`
- Skipped by annotation type: `Request`, `HTTPConnection`, `BackgroundTasks`, etc.

---

### Django REST Framework (Python)

**Detected patterns:**

```python
# ViewSet (auto-generates list/create/retrieve/update/destroy)
router = DefaultRouter()
router.register(r'accounts', AccountViewSet, basename='account')

# Nested router (DRF-nested-routers)
nested = NestedSimpleRouter(router, r'accounts', lookup='account')
nested.register(r'transactions', TransactionViewSet)
# → GET /accounts/{account_pk}/transactions/

# @action decorator
class AccountViewSet(ModelViewSet):
    @action(methods=['post'], detail=True, url_path='activate')
    def activate(self, request, pk=None):
        ...
# → POST /accounts/{pk}/activate/

# APIView
class AccountView(APIView):
    def get(self, request):   ...   # → GET /accounts/
    def post(self, request):  ...   # → POST /accounts/
```

**Mixin filtering:**
```python
class ReportViewSet(RetrieveModelMixin, ListModelMixin, GenericViewSet):
    pass
# Generates only: GET /reports/ and GET /reports/{pk}/
```

---

### Express (Node.js/JavaScript)

**Detected patterns:**
```javascript
app.get('/v1/accounts', handler)
app.post('/v1/accounts', createAccount)
router.put('/v1/accounts/:id', updateAccount)
app.use('/v1', router)               // prefix mounting
```

**Requires:** Node.js + `@babel/parser` npm package

**Path conversion:** `:userId` → `{userId}` (OpenAPI style)

---

### NestJS (TypeScript)

**Detected patterns:**
```typescript
@Controller('v1/accounts')
export class AccountController {

  @Get()
  findAll(): Account[] { ... }

  @Get(':id')
  findOne(@Param('id') id: string): Account { ... }

  @Post()
  create(@Body() dto: CreateAccountDto): Account { ... }
}
```

**When Node.js is unavailable:** Falls back to Python regex scanner that parses `@Controller`, `@Get`, `@Post`, `@Put`, `@Patch`, `@Delete` decorators directly.

---

### Gin / Echo (Go)

**Detected patterns:**
```go
r := gin.Default()
r.GET("/v1/accounts", listAccounts)
r.POST("/v1/accounts", createAccount)

v1 := r.Group("/v1")
{
    v1.GET("/accounts/:id", getAccount)
    v1.DELETE("/accounts/:id", deleteAccount)
}
```

**Fallback:** If Go is not installed, uses regex on `.go` source files. Regex captures `\.(GET|POST|PUT|DELETE|PATCH)\s*\(\s*"([^"]+)"` and group prefixes.

---

## 8. Schema Inferrers

### 8.0 AST-Based Analysis: How It Works

Before diving into per-language details, this section explains the shared
AST traversal model that all four inferrers follow.

#### The three-step inference loop

Every inferrer follows the same three-step loop regardless of language:

```
Step 1 — Find the file
   BaseInferrer._find_type_file("CreateAccountRequest")
   ├── Glob all source files of the right extension
   ├── Grep each for the type name
   ├── Apply model-first heuristic (prefer "model", "dto" in path)
   ├── Apply prefer_file glob from config
   └── Return best candidate Path

Step 2 — Parse the file into an AST
   Language-specific library reads the file and builds a tree
   Python  → ast.parse(source)                       (in-process)
   Java    → javalang.parse.parse(source)             (in-process)
   Go      → go/ast via compiled binary subprocess    (out-of-process)
   TypeScript → ts-morph via Node.js subprocess       (out-of-process)

Step 3 — Walk the tree to extract fields
   Language-specific traversal finds the named type declaration
   For each field:
     - Extract JSON field name       (from annotation / tag / property name)
     - Determine JSON Schema type    (string, integer, number, boolean, array, object)
     - Check required / nullable     (from annotation or type modifier)
     - Extract constraints           (min, max, pattern, format, ...)
     - If nested type → recurse via resolve_type() with cycle guard
```

#### How a source file becomes a JSON Schema object

Taking a Spring Boot request body as a worked example across all four stages:

```
Java source                      javalang AST nodes               JSON Schema output
──────────────────────           ─────────────────────────        ──────────────────────────────
@NotNull                         AnnotationDeclaration            "required": ["name"]
@Size(min=1, max=50)              └─ name: "Size"
private String name;              └─ element: [{min:1},{max:50}]  "minLength": 1, "maxLength": 50

@Valid                           AnnotationDeclaration            "$ref": "#/components/schemas/
private Address addr;             └─ name: "Valid"                          Address"
                                 FieldDeclaration
                                  └─ type: ReferenceType("Address")

@JsonIgnore                      AnnotationDeclaration            (field excluded)
private String _cache;            └─ name: "JsonIgnore"
```

The same principle applies for every language — the AST node type and the
annotation/tag/decorator is the input; the JSON Schema keyword is the output.

#### Why `_find_type_file` is important

A common source of MANUAL confidence is the engine not finding the type file.
This happens when:

1. **Type is in a shared library** — a separate repo, not present in the clone
2. **Type is defined in a generated file** — in a path covered by `exclude_paths`
3. **Type is a primitive wrapped in a typedef** — `type UserID = string` in Go
4. **Multiple files define the same type** — engine warns and picks one; use
   `prefer_file` in config to be explicit

To debug a missing type, run the schema subcommand directly:

```bash
spec-engine schema \
  --manifest route_manifest.json \
  --repo .  \
  --verbose
# DEBUG lines show: "Searching for type 'CreateAccountRequest' in X files"
# DEBUG: "Found at: src/main/java/com/example/dto/CreateAccountRequest.java"
# DEBUG: "Resolved 5 fields with HIGH confidence"
```

---

### Java (javalang)

Resolves types from `.java` files using full AST parsing:

```java
// Input
public class CreateAccountRequest {
    @NotNull
    @Size(min=1, max=50)
    @JsonProperty("account_name")
    private String name;

    @NotBlank
    @Email
    private String email;

    @Min(0)
    private Integer age;

    @JsonIgnore
    private String internalId;   // excluded
}

// Output JSON Schema
{
  "type": "object",
  "properties": {
    "account_name": { "type": "string", "minLength": 1, "maxLength": 50 },
    "email": { "type": "string", "format": "email", "minLength": 1 },
    "age": { "type": "integer", "minimum": 0 }
  },
  "required": ["account_name", "email"]
}
```

**Supported annotation → schema mapping:**

| Annotation | JSON Schema field |
|---|---|
| `@NotNull` | required: true |
| `@NotBlank` | required: true, minLength: 1 |
| `@NotEmpty` | required: true, minLength: 1 |
| `@Size(min=N, max=M)` | minLength: N, maxLength: M |
| `@Min(N)` | minimum: N |
| `@Max(N)` | maximum: N |
| `@Pattern(regexp="...")` | pattern: "..." |
| `@Email` | format: "email" |
| `@Positive` | minimum: 1 |
| `@PositiveOrZero` | minimum: 0 |
| `@Negative` | maximum: -1 |
| `@NegativeOrZero` | maximum: 0 |

---

### Python (Pydantic / ast)

```python
class CreateAccountRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    email: str = Field(..., description="Primary email")
    age: Optional[int] = None
    tags: List[str] = []
    address: Address           # nested type → $ref

# Output JSON Schema
{
  "type": "object",
  "properties": {
    "name": { "type": "string", "minLength": 1, "maxLength": 50 },
    "email": { "type": "string", "description": "Primary email" },
    "age": { "type": "integer", "nullable": true },
    "tags": { "type": "array", "items": { "type": "string" } },
    "address": { "$ref": "#/components/schemas/Address" }
  },
  "required": ["name", "email"]
}
```

**Supported base classes:** `BaseModel`, `Schema`, `SQLModel`, `BaseSettings`

**Supported Field() kwargs → JSON Schema:**

| Field kwarg | JSON Schema |
|---|---|
| `min_length` | `minLength` |
| `max_length` | `maxLength` |
| `pattern` / `regex` | `pattern` |
| `ge` | `minimum` |
| `le` | `maximum` |
| `gt` | `exclusiveMinimum` |
| `lt` | `exclusiveMaximum` |
| `min_items` | `minItems` |
| `max_items` | `maxItems` |
| `multiple_of` | `multipleOf` |
| `title` | `title` |
| `description` | `description` |

---

### Go (struct tags)

```go
type CreateOrderRequest struct {
    Name  string   `json:"name"  validate:"required,min=1,max=100"`
    Email string   `json:"email" validate:"required"`
    Count *int     `json:"count,omitempty"`
    Tags  []string `json:"tags"`
    Addr  Address  `json:"address"`
    secret string          // unexported → excluded
    Skip  string  `json:"-"` // json:"-" → excluded
}

// Output JSON Schema
{
  "type": "object",
  "properties": {
    "name":    { "type": "string",  "minimum": 1.0, "maximum": 100.0 },
    "email":   { "type": "string" },
    "count":   { "type": "integer", "nullable": true },
    "tags":    { "type": "array",   "items": { "type": "string" } },
    "address": { "$ref": "#/components/schemas/Address" }
  },
  "required": ["name", "email"]
}
```

**Struct tag parsing:**
- `json:"name"` → field name
- `json:"name,omitempty"` → name + nullable
- `json:"-"` → excluded
- `validate:"required"` → required
- `validate:"min=N,max=M"` → minimum / maximum constraints
- Unexported fields (lowercase) → always excluded

---

### TypeScript (ts-morph via Node.js)

```typescript
interface CreateAccountRequest {
  name: string;
  email: string;
  age?: number;              // optional → nullable
  tags: string[];
  address: Address;
}

// Output JSON Schema (via ts_schema.js)
{
  "type": "object",
  "properties": {
    "name":    { "type": "string" },
    "email":   { "type": "string" },
    "age":     { "type": "number", "nullable": true },
    "tags":    { "type": "array", "items": { "type": "string" } },
    "address": { "$ref": "#/components/schemas/Address" }
  },
  "required": ["name", "email", "tags", "address"]
}
```

**Requires:** Node.js + `ts-morph` npm package

**Graceful fallback:** Returns empty SchemaResult (MANUAL confidence) if Node.js or ts-morph unavailable.

---

### Schema conflict resolution (`prefer_file`)

When multiple files define the same type name:

1. Engine logs a `WARNING` listing all candidate files
2. Applies `prefer_file` glob from config if set:

```yaml
# config.yaml
prefer_file: "*/dto/*.java"     # prefer DTO classes over domain model duplicates
```

3. Falls back to model-first heuristic (file path contains "model", "dto", "domain", etc.)

---

## 9. Assembler, Validator & Publisher

### Assembler internals

Key functions in `assembler.py`:

```python
assemble(routes, schemas, repo_path, config) -> str
    ├── _detect_api_metadata(repo_path)
    │     Reads pom.xml / package.json / CODEOWNERS
    ├── _build_info_block(metadata, config)
    │     Adds x-owner, x-gateway, x-lifecycle
    ├── _build_paths(routes, schemas)
    │     Groups routes by path string
    │     Generates operationId per route
    │     Adds parameters, requestBody, responses
    ├── _build_components(schemas)
    │     Adds x-confidence, x-source-file to each schema
    │     Always includes Error schema
    └── _to_yaml(openapi_dict)
          Uses ruamel.yaml to preserve key ordering
```

### Validator internals

```python
validate(spec_path, config) -> ValidationResult
    ├── _run_redocly(spec_path)       # subprocess call, mocked in tests
    ├── _run_spectral(spec_path)      # subprocess call, mocked in tests
    └── _check_x_fields(spec_path, config.required_x_fields)
```

**Adding a custom validation rule without Spectral:**

```python
# In validator.py, add to validate():
result.errors.extend(_check_operation_ids(spec_path))

def _check_operation_ids(spec_path: str) -> List[str]:
    """Ensure all operationIds are camelCase."""
    ...
```

### Publisher internals

```python
publish(spec_path, config, dry_run=False) -> dict
    ├── _validate_config(config)
    ├── _read_spec(spec_path)
    ├── _extract_api_name(spec_content)     # from info.title
    ├── _check_existing(catalog_url, token, api_name)
    │     GET /apis → find by title
    └── if existing: PUT /apis/{id}
        else:        POST /apis
```

---

## 10. Data Models

### RouteInfo

```python
@dataclass
class RouteInfo:
    method: str                           # GET | POST | PUT | DELETE | PATCH | HEAD | OPTIONS
    path: str                             # /v1/accounts/{id}
    handler: str                          # AccountController.getById
    file: str                             # relative path from repo root
    line: int                             # line number in source file
    framework: str                        # spring | fastapi | django | express | nestjs | gin | echo
    params: List[ParamInfo] = field(...)
    request_body_type: Optional[str] = None
    response_type: Optional[str] = None
    auth_schemes: List[str] = field(...)
    tags: List[str] = field(...)
    summary: str = ""
    deprecated: bool = False

    @property
    def operation_id(self) -> str:
        # POST /v1/accounts/{id}/activate → createAccountsByIdActivate
```

### SchemaResult

```python
@dataclass
class SchemaResult:
    type_name: str                        # "Account"
    json_schema: Dict[str, Any]           # {"type": "object", "properties": {...}}
    confidence: Confidence                # HIGH | MEDIUM | LOW | MANUAL
    source_file: str                      # "src/main/java/com/.../Account.java"
    refs: List[str] = field(...)          # ["Address", "PhoneNumber"] (nested types)

    @property
    def is_empty(self) -> bool:
        return not self.json_schema or not isinstance(self.json_schema, dict)

    def to_component_schema(self) -> dict:
        # Returns json_schema + x-confidence + x-source-file
```

### ParamInfo

```python
@dataclass
class ParamInfo:
    name: str                             # "accountId"
    location: str                         # path | query | header | cookie
    required: bool = True
    schema: Dict[str, Any] = field(...)   # {"type": "string"}
    description: str = ""

    def to_openapi(self) -> dict:
        # {"name": ..., "in": ..., "required": ..., "schema": ..., "description": ...}
```

---

## 11. Testing Guide

### Run full test suite

```bash
# All 365 tests
pytest tests/ -v

# With coverage report
pytest tests/ --cov=spec_engine --cov-report=term-missing

# Specific file
pytest tests/test_scanner_spring.py -v

# Specific test class or function
pytest tests/test_inferrer_python.py::TestExtractFields -v
pytest tests/test_scanner_django.py::TestDjangoScanner::test_has_list_route -v

# Fail fast on first failure
pytest tests/ -x

# Run in parallel (install pytest-xdist first)
pip install pytest-xdist
pytest tests/ -n auto
```

### Coverage by module (current baseline)

```
spec_engine/config.py               91%
spec_engine/models.py               87%
spec_engine/cli.py                  82%
spec_engine/assembler.py            78%
spec_engine/validator.py            85%
spec_engine/publisher.py            79%
spec_engine/scanner/spring.py       74%
spec_engine/scanner/fastapi.py      71%
spec_engine/scanner/django.py       69%
spec_engine/scanner/express.py      89%
spec_engine/scanner/nestjs.py       83%
spec_engine/scanner/gin.py          61%
spec_engine/inferrer/base.py        88%
spec_engine/inferrer/java_ast.py    76%
spec_engine/inferrer/python_ast.py  81%
spec_engine/inferrer/typescript_ast.py  88%
spec_engine/inferrer/go_ast.py      83%
Overall                             83%
```

### Writing new tests

All tests follow the same pattern:

```python
# tests/test_scanner_my_framework.py
import pytest
from pathlib import Path
from spec_engine.scanner.my_framework import MyScanner
from spec_engine.config import Config


@pytest.fixture
def scanner(tmp_path):
    return MyScanner(str(tmp_path), Config())


class TestMyScanner:
    def test_finds_get_route(self, scanner, tmp_path):
        (tmp_path / "main.py").write_text(...)  # write fixture inline
        routes = scanner.scan()
        assert any(r.method == "GET" for r in routes)

    def test_framework_label(self, scanner, tmp_path):
        (tmp_path / "main.py").write_text(...)
        routes = scanner.scan()
        assert all(r.framework == "myframework" for r in routes)
```

**Mocking subprocess calls:**

```python
from unittest.mock import MagicMock
import subprocess

def test_node_unavailable(scanner, tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )
    routes = scanner.scan()
    assert routes == []   # graceful empty return
```

### Fixture repos

Place multi-file fixture repos under `tests/fixtures/<framework>/`:

```
tests/fixtures/spring/
├── src/main/java/com/example/
│   ├── AccountController.java
│   └── model/Account.java
├── pom.xml
└── urls.py          # (not applicable for Spring, but shows structure)
```

Reference them in tests:
```python
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "spring"

def test_full_spring_scan():
    scanner = SpringScanner(str(FIXTURE_DIR), Config())
    routes = scanner.scan()
    assert len(routes) >= 5
```

---

## 12. Running Against Thousands of Repos

Two deployment approaches are described below, matching the architecture in `STAKEHOLDER_OVERVIEW.md`:

- **Approach 1A:** CSV-driven batch orchestrator — reads the existing API inventory CSV, clones each repo, generates and publishes specs. Covers the entire inventory in one run.
- **Approach 1B:** Repo-level CI step — each repo's pipeline runs spec-engine on every push to main.
- **Approach 2:** Platform-level enforcement — spec-engine injected at the GitHub/Jenkins platform layer (see Platform CI Templates section).

---

### Approach 1A — CSV-Driven Batch Orchestrator

#### CSV format

Save your API inventory as `api_inventory.csv`. The orchestrator reads these columns:

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
| `api_name` | Yes | Unique API name; used for output spec filename |
| `team` | Yes | Owning team; used as `--owner` if `owner` column is blank |
| `gateway` | Yes | API gateway; used as `--gateway` |
| `repo_url` | Yes | Full git clone URL (HTTPS or SSH) |
| `framework` | No | Override framework detection; leave blank for auto-detect |
| `lifecycle` | No | `production`, `beta`, or `deprecated`; defaults to `production` |
| `owner` | No | `x-owner` override; defaults to `team` value |
| `env` | No | Environment tag; defaults to `production` |
| `exclude_paths` | No | Semicolon-separated glob patterns to skip during scan |

#### Full batch orchestrator (`tools/batch_loader.py`)

```python
#!/usr/bin/env python3
"""
batch_loader.py — CSV-driven bulk spec generator.

Usage:
    python3 tools/batch_loader.py \
        --csv api_inventory.csv \
        --config config.yaml \
        --spec-dir ./specs \
        --log-dir  ./logs \
        --workers  16 \
        --publish \
        --retry-failed  # re-run only rows that previously failed

Requires:
    - spec-engine installed in active virtualenv
    - GIT_TOKEN env var (for HTTPS clone auth) or SSH key configured
    - EXPLORER_API_TOKEN env var (for --publish)
"""

import argparse
import concurrent.futures
import csv
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("batch_loader")

# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class RepoRow:
    api_name: str
    team: str
    gateway: str
    repo_url: str
    framework: str = ""
    lifecycle: str = "production"
    owner: str = ""
    env: str = "production"
    exclude_paths: str = ""

    def effective_owner(self) -> str:
        return self.owner or self.team


@dataclass
class RepoResult:
    api_name: str
    repo_url: str
    success: bool
    routes_found: int = 0
    confidence_high: int = 0
    confidence_medium: int = 0
    confidence_manual: int = 0
    spec_path: str = ""
    error: str = ""
    duration_seconds: float = 0.0


# ──────────────────────────────────────────────────────────────────────────────
# CSV loading
# ──────────────────────────────────────────────────────────────────────────────

def load_csv(csv_path: Path) -> List[RepoRow]:
    rows = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            api_name = row.get("api_name", "").strip()
            repo_url = row.get("repo_url", "").strip()
            if not api_name or not repo_url:
                log.warning("Row %d: missing api_name or repo_url — skipped", i)
                continue
            rows.append(RepoRow(
                api_name=api_name,
                team=row.get("team", "").strip(),
                gateway=row.get("gateway", "unknown").strip(),
                repo_url=repo_url,
                framework=row.get("framework", "").strip(),
                lifecycle=row.get("lifecycle", "production").strip() or "production",
                owner=row.get("owner", "").strip(),
                env=row.get("env", "production").strip() or "production",
                exclude_paths=row.get("exclude_paths", "").strip(),
            ))
    log.info("Loaded %d rows from %s", len(rows), csv_path)
    return rows


def load_failed_from_report(report_path: Path) -> List[str]:
    """Return api_names that failed in a previous batch_report.csv run."""
    failed = []
    with report_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("success", "true").lower() != "true":
                failed.append(row["api_name"])
    return failed


# ──────────────────────────────────────────────────────────────────────────────
# Git clone helper
# ──────────────────────────────────────────────────────────────────────────────

def clone_repo(repo_url: str, clone_dir: Path, git_token: Optional[str]) -> bool:
    """Shallow-clone repo_url into clone_dir. Returns True on success."""
    # Inject token for HTTPS URLs if available
    url = repo_url
    if git_token and url.startswith("https://"):
        # https://github.com/org/repo → https://TOKEN@github.com/org/repo
        url = url.replace("https://", f"https://{git_token}@", 1)

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", url, str(clone_dir)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            log.debug("git clone failed for %s: %s", repo_url, result.stderr.strip())
            return False
        return True
    except subprocess.TimeoutExpired:
        log.debug("git clone timeout for %s", repo_url)
        return False
    except FileNotFoundError:
        log.error("git not found in PATH")
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Parse spec-engine stdout for metrics
# ──────────────────────────────────────────────────────────────────────────────

def _parse_routes(output: str) -> int:
    m = re.search(r"Scanned (\d+) routes", output)
    return int(m.group(1)) if m else 0

def _parse_confidence(output: str, level: str) -> int:
    m = re.search(rf"{level}:\s*(\d+)", output, re.IGNORECASE)
    return int(m.group(1)) if m else 0


# ──────────────────────────────────────────────────────────────────────────────
# Process one row
# ──────────────────────────────────────────────────────────────────────────────

def process_row(
    row: RepoRow,
    spec_dir: Path,
    log_dir: Path,
    config_path: str,
    do_publish: bool,
    git_token: Optional[str],
) -> RepoResult:
    started = datetime.now(timezone.utc)
    out_path = spec_dir / f"{row.api_name}.yaml"
    log_path = log_dir / f"{row.api_name}.log"

    with tempfile.TemporaryDirectory(prefix=f"spec_batch_{row.api_name}_") as tmp:
        clone_dir = Path(tmp) / "repo"

        # Step 1: clone
        if not clone_repo(row.repo_url, clone_dir, git_token):
            duration = (datetime.now(timezone.utc) - started).total_seconds()
            return RepoResult(
                api_name=row.api_name,
                repo_url=row.repo_url,
                success=False,
                error="git clone failed",
                duration_seconds=duration,
            )

        # Step 2: write per-repo .spec-engine.yaml if exclude_paths are set
        if row.exclude_paths:
            patterns = [p.strip() for p in row.exclude_paths.split(";") if p.strip()]
            repo_cfg = clone_dir / ".spec-engine.yaml"
            lines = ["exclude_paths:"]
            for p in patterns:
                lines.append(f'  - "{p}"')
            repo_cfg.write_text("\n".join(lines) + "\n")

        # Step 3: build spec-engine command
        cmd = [
            "spec-engine", "generate",
            "--repo",      str(clone_dir),
            "--config",    config_path,
            "--gateway",   row.gateway,
            "--owner",     row.effective_owner(),
            "--env",       row.env,
            "--out",       str(out_path),
            "--verbose",
        ]
        if row.framework:
            cmd += ["--framework", row.framework]
        if do_publish:
            cmd.append("--publish")

        # Step 4: run
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            combined = result.stdout + "\n" + result.stderr
            log_path.write_text(combined)

            success = result.returncode == 0
            duration = (datetime.now(timezone.utc) - started).total_seconds()

            return RepoResult(
                api_name=row.api_name,
                repo_url=row.repo_url,
                success=success,
                routes_found=_parse_routes(combined),
                confidence_high=_parse_confidence(combined, "HIGH"),
                confidence_medium=_parse_confidence(combined, "MEDIUM"),
                confidence_manual=_parse_confidence(combined, "MANUAL"),
                spec_path=str(out_path) if success else "",
                error="" if success else result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown",
                duration_seconds=duration,
            )
        except subprocess.TimeoutExpired:
            duration = (datetime.now(timezone.utc) - started).total_seconds()
            log_path.write_text("TIMEOUT after 180 seconds\n")
            return RepoResult(
                api_name=row.api_name,
                repo_url=row.repo_url,
                success=False,
                error="timeout (180s)",
                duration_seconds=duration,
            )


# ──────────────────────────────────────────────────────────────────────────────
# Report writers
# ──────────────────────────────────────────────────────────────────────────────

def write_batch_report(results: List[RepoResult], report_path: Path) -> None:
    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "api_name", "success", "routes_found",
            "confidence_high", "confidence_medium", "confidence_manual",
            "spec_path", "error", "duration_seconds",
        ])
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))
    log.info("Batch report written to %s", report_path)


def write_batch_summary(results: List[RepoResult], started: datetime, summary_path: Path) -> None:
    succeeded = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    duration = (datetime.now(timezone.utc) - started).total_seconds()

    all_high = sum(
        1 for r in succeeded
        if r.confidence_medium == 0 and r.confidence_manual == 0
    )
    has_medium = sum(1 for r in succeeded if r.confidence_medium > 0)
    has_manual = sum(1 for r in succeeded if r.confidence_manual > 0)

    summary = {
        "run_date": started.isoformat(),
        "total_repos": len(results),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "duration_minutes": round(duration / 60, 1),
        "confidence_breakdown": {
            "all_high": all_high,
            "has_medium": has_medium,
            "has_manual": has_manual,
        },
        "failed_repos": [{"api_name": r.api_name, "error": r.error} for r in failed],
    }
    summary_path.write_text(json.dumps(summary, indent=2))
    log.info("Batch summary written to %s", summary_path)

    # Print to stdout
    print(f"\n{'='*60}")
    print(f"  Batch complete: {len(succeeded)}/{len(results)} succeeded")
    print(f"  Duration:       {duration/60:.1f} minutes")
    print(f"  All-HIGH:       {all_high} specs")
    print(f"  Has MEDIUM:     {has_medium} specs (review recommended)")
    print(f"  Has MANUAL:     {has_manual} specs (review required)")
    if failed:
        print(f"\n  FAILED ({len(failed)}):")
        for r in failed:
            print(f"    - {r.api_name}: {r.error}")
    print(f"{'='*60}\n")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="CSV-driven spec-engine batch loader")
    parser.add_argument("--csv",          required=True, help="Path to API inventory CSV")
    parser.add_argument("--config",       default="config.yaml", help="Path to spec-engine config.yaml")
    parser.add_argument("--spec-dir",     default="./specs",     help="Output directory for generated specs")
    parser.add_argument("--log-dir",      default="./logs",      help="Output directory for per-repo logs")
    parser.add_argument("--report",       default="./batch_report.csv",   help="Output batch report CSV")
    parser.add_argument("--summary",      default="./batch_summary.json", help="Output batch summary JSON")
    parser.add_argument("--workers",      type=int, default=8,   help="Parallel workers")
    parser.add_argument("--publish",      action="store_true",   help="Publish specs to Explorer catalog")
    parser.add_argument("--retry-failed", metavar="PREV_REPORT", help="Only process rows that failed in a previous report")
    parser.add_argument("--dry-run",      action="store_true",   help="Clone and validate only; skip publish")
    args = parser.parse_args()

    spec_dir = Path(args.spec_dir)
    log_dir  = Path(args.log_dir)
    spec_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Git auth token (for HTTPS clones)
    git_token = os.environ.get("GIT_TOKEN") or os.environ.get("GITHUB_TOKEN")

    # Load CSV
    rows = load_csv(Path(args.csv))
    if not rows:
        log.error("No valid rows found in CSV. Exiting.")
        return 1

    # Filter to retry-failed only if requested
    if args.retry_failed:
        failed_names = set(load_failed_from_report(Path(args.retry_failed)))
        rows = [r for r in rows if r.api_name in failed_names]
        log.info("Retry mode: %d rows to re-process", len(rows))

    do_publish = args.publish and not args.dry_run
    started = datetime.now(timezone.utc)
    results: List[RepoResult] = []

    log.info("Starting batch: %d repos, %d workers, publish=%s", len(rows), args.workers, do_publish)

    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
        future_to_row = {
            executor.submit(
                process_row, row, spec_dir, log_dir, args.config, do_publish, git_token
            ): row
            for row in rows
        }
        for future in concurrent.futures.as_completed(future_to_row):
            row = future_to_row[future]
            try:
                result = future.result()
            except Exception as exc:
                result = RepoResult(
                    api_name=row.api_name,
                    repo_url=row.repo_url,
                    success=False,
                    error=str(exc),
                )
            results.append(result)
            status = "OK  " if result.success else "FAIL"
            print(f"[{status}] {result.api_name:40s}  routes={result.routes_found:4d}  {result.duration_seconds:.1f}s")

    write_batch_report(results, Path(args.report))
    write_batch_summary(results, started, Path(args.summary))

    failed_count = sum(1 for r in results if not r.success)
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
```

#### Running the batch

```bash
# Set credentials
export EXPLORER_API_TOKEN="eyJhbGci..."
export GIT_TOKEN="ghp_xxxx"          # GitHub PAT with repo:read scope
                                      # (or set up SSH key for SSH clone URLs)

# Install spec-engine
pip install spec-engine
npm install -g @redocly/cli @stoplight/spectral-cli

# Run full batch (all rows in CSV)
python3 tools/batch_loader.py \
    --csv        api_inventory.csv \
    --config     config.yaml \
    --spec-dir   ./specs \
    --log-dir    ./logs \
    --workers    16 \
    --publish

# Dry-run first (clone + generate, skip publish)
python3 tools/batch_loader.py \
    --csv      api_inventory.csv \
    --config   config.yaml \
    --workers  16 \
    --dry-run

# Re-run only rows that failed in the previous batch
python3 tools/batch_loader.py \
    --csv          api_inventory.csv \
    --config       config.yaml \
    --workers      8 \
    --publish \
    --retry-failed batch_report.csv
```

#### Outputs

```
specs/
  payments-api.yaml
  accounts-api.yaml
  risk-api.yaml
  rewards-ts.yaml
  ...

logs/
  payments-api.log      # full spec-engine --verbose output
  accounts-api.log
  fraud-service.log     # contains error details for failed repos
  ...

batch_report.csv        # row-per-repo status, routes found, confidence breakdown
batch_summary.json      # aggregate metrics for dashboard/alerting
```

**`batch_report.csv` example:**
```
api_name,success,routes_found,confidence_high,confidence_medium,confidence_manual,spec_path,error,duration_seconds
payments-api,true,84,76,8,0,specs/payments-api.yaml,,12.4
accounts-api,true,42,38,4,0,specs/accounts-api.yaml,,7.1
fraud-service,false,0,0,0,0,,git clone failed,3.2
risk-api,true,31,20,9,2,specs/risk-api.yaml,,9.8
rewards-ts,true,55,50,5,0,specs/rewards-ts.yaml,,18.6
```

---

### Approach 1B — Repo-Level CI Step

After the initial batch load, update each repo's existing CI pipeline to keep its spec current on every merge. This is a self-service step — the team adds it to their existing pipeline file.

**GitHub Actions (add to existing workflow):**
```yaml
# In the repo's .github/workflows/ci.yml — add this job
  generate-spec:
    name: Generate OpenAPI Spec
    runs-on: ubuntu-latest
    needs: [build, test]           # run after build succeeds
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }

      - uses: actions/setup-node@v4
        with: { node-version: "20" }

      - name: Generate and publish spec
        run: |
          pip install spec-engine --quiet
          npm install -g @redocly/cli @stoplight/spectral-cli --silent
          spec-engine generate \
            --repo . \
            --gateway "${{ vars.API_GATEWAY }}" \
            --owner   "${{ vars.API_OWNER }}" \
            --out     openapi.yaml \
            --publish
        env:
          EXPLORER_API_TOKEN: ${{ secrets.EXPLORER_API_TOKEN }}

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: openapi-spec
          path: openapi.yaml
```

**Jenkins (add stage to existing Jenkinsfile):**
```groovy
stage('Generate OpenAPI Spec') {
    when { branch 'main' }
    steps {
        withCredentials([string(credentialsId: 'EXPLORER_API_TOKEN', variable: 'EXPLORER_API_TOKEN')]) {
            sh '''
                pip install spec-engine --quiet
                npm install -g @redocly/cli @stoplight/spectral-cli --silent
                spec-engine generate \
                    --repo . \
                    --gateway "${API_GATEWAY}" \
                    --owner   "${API_OWNER}" \
                    --out openapi.yaml \
                    --publish --verbose
            '''
        }
    }
    post {
        always { archiveArtifacts artifacts: 'openapi.yaml', allowEmptyArchive: true }
    }
}
```

#### Sending PRs at scale (bulk CI step adoption)

To add the CI step to many repos without waiting for teams, use the `batch_pr_creator.py` script:

```python
#!/usr/bin/env python3
"""
batch_pr_creator.py — Opens a PR in each repo from the CSV to add the spec-engine CI step.

Usage:
    python3 tools/batch_pr_creator.py \
        --csv api_inventory.csv \
        --template tools/templates/spec-engine-step.yml \
        --workers 8
"""

import argparse
import csv
import concurrent.futures
import subprocess
import tempfile
from pathlib import Path


WORKFLOW_TEMPLATE = Path("tools/templates/spec-engine-step.yml").read_text()
PR_TITLE = "chore: add spec-engine OpenAPI spec generation step"
PR_BODY = """\
## Summary

Adds an automated OpenAPI 3.1 spec generation step using spec-engine.

- Runs on every push to `main`
- Generates and publishes spec to the API Explorer catalog
- No application code changes required

**Review:** The step is non-blocking — it will not fail your build if spec generation fails
during the initial stabilization period.

Raised by the SRE Frameworks team as part of the API catalog rollout.
"""


def add_spec_step_pr(row: dict, template: str) -> dict:
    api_name = row["api_name"]
    repo_url = row["repo_url"]

    with tempfile.TemporaryDirectory() as tmp:
        clone_dir = Path(tmp) / "repo"
        subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", repo_url, str(clone_dir)],
            check=True, timeout=90,
        )

        # Write workflow file
        wf_dir = clone_dir / ".github" / "workflows"
        wf_dir.mkdir(parents=True, exist_ok=True)
        (wf_dir / "spec-engine.yml").write_text(template)

        # Commit and push branch
        branch = "chore/add-spec-engine"
        subprocess.run(["git", "-C", str(clone_dir), "checkout", "-b", branch], check=True)
        subprocess.run(["git", "-C", str(clone_dir), "add", ".github/workflows/spec-engine.yml"], check=True)
        subprocess.run(["git", "-C", str(clone_dir), "commit", "-m", PR_TITLE], check=True)
        subprocess.run(["git", "-C", str(clone_dir), "push", "origin", branch], check=True)

        # Open PR via GitHub CLI
        result = subprocess.run(
            ["gh", "pr", "create",
             "--title", PR_TITLE,
             "--body", PR_BODY,
             "--base", "main",
             "--head", branch,
            ],
            capture_output=True, text=True, cwd=str(clone_dir), timeout=30,
        )
        pr_url = result.stdout.strip()
        return {"api_name": api_name, "pr_url": pr_url, "success": result.returncode == 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--template", default="tools/templates/spec-engine-step.yml")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    template = Path(args.template).read_text()
    rows = []
    with open(args.csv, newline="") as f:
        rows = list(csv.DictReader(f))

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(add_spec_step_pr, row, template): row for row in rows}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            status = "PR opened" if result["success"] else "FAILED"
            print(f"[{status}] {result['api_name']}: {result.get('pr_url', result.get('error', ''))}")
            results.append(result)

    opened = sum(1 for r in results if r["success"])
    print(f"\nPRs opened: {opened}/{len(results)}")


if __name__ == "__main__":
    main()
```

---

### Approach 2 — Platform-Level CI Templates

When Platform Engineering has enabled the Required Workflow or Shared Library, teams get spec-engine automatically. These are the templates maintained in the `platform-workflows` repository.

**GitHub Actions reusable workflow** (`platform-workflows/.github/workflows/spec-engine.yml`):

```yaml
name: Generate OpenAPI Spec (Reusable)
on:
  workflow_call:
    inputs:
      gateway:
        type: string
        default: "unknown"
      owner:
        type: string
        default: "unknown"
      framework:
        type: string
        default: ""
      lifecycle:
        type: string
        default: "production"
      publish:
        type: boolean
        default: true
    secrets:
      explorer-token:
        required: true

jobs:
  generate-spec:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 1 }

      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }

      - uses: actions/setup-node@v4
        with: { node-version: "20" }

      - name: Install tools
        run: |
          pip install spec-engine
          npm install -g @redocly/cli @stoplight/spectral-cli

      - name: Generate and publish spec
        env:
          EXPLORER_API_TOKEN: ${{ secrets.explorer-token }}
        run: |
          FRAMEWORK_FLAG=""
          [ -n "${{ inputs.framework }}" ] && FRAMEWORK_FLAG="--framework ${{ inputs.framework }}"
          spec-engine generate \
            --repo . \
            --gateway "${{ inputs.gateway }}" \
            --owner   "${{ inputs.owner }}" \
            --env     "${{ inputs.lifecycle }}" \
            $FRAMEWORK_FLAG \
            --out openapi.yaml \
            ${{ inputs.publish && '--publish' || '' }} \
            --verbose

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: openapi-spec
          path: openapi.yaml
          retention-days: 30
          if-no-files-found: warn
```

**Required Workflow caller** (`platform-workflows/.github/workflows/spec-engine-required.yml`):

```yaml
# Org-level Required Workflow — Platform Engineering configures this
# in GitHub org settings. It runs automatically on all tagged repos.
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

**Bulk-set repo variables from CSV** (run by SRE Frameworks after Platform Engineering enables Required Workflow):

```bash
#!/usr/bin/env bash
# tools/set_repo_variables.sh
# Sets GitHub repo variables for each row in the CSV.
# Requires: gh CLI authenticated with admin:org scope.

CSV="api_inventory.csv"

tail -n +2 "$CSV" | while IFS=, read -r api_name team gateway repo_url framework lifecycle owner env exclude_paths; do
    # Derive org/repo from URL
    repo_slug=$(echo "$repo_url" | sed 's|https://github.com/||')

    echo "Setting variables for $repo_slug ..."

    gh api "repos/${repo_slug}/actions/variables" \
        --method POST \
        --field name="API_GATEWAY" \
        --field value="${gateway}" 2>/dev/null || \
    gh api "repos/${repo_slug}/actions/variables/API_GATEWAY" \
        --method PATCH --field value="${gateway}"

    gh api "repos/${repo_slug}/actions/variables" \
        --method POST \
        --field name="API_OWNER" \
        --field value="${owner:-$team}" 2>/dev/null || \
    gh api "repos/${repo_slug}/actions/variables/API_OWNER" \
        --method PATCH --field value="${owner:-$team}"

    if [ -n "$framework" ]; then
        gh api "repos/${repo_slug}/actions/variables" \
            --method POST \
            --field name="API_FRAMEWORK" \
            --field value="${framework}" 2>/dev/null || \
        gh api "repos/${repo_slug}/actions/variables/API_FRAMEWORK" \
            --method PATCH --field value="${framework}"
    fi

    gh api "repos/${repo_slug}/actions/variables" \
        --method POST \
        --field name="API_LIFECYCLE" \
        --field value="${lifecycle:-production}" 2>/dev/null || \
    gh api "repos/${repo_slug}/actions/variables/API_LIFECYCLE" \
        --method PATCH --field value="${lifecycle:-production}"

    # Apply api-service topic so Required Workflow policy targets this repo
    gh api "repos/${repo_slug}/topics" \
        --method PUT \
        --field "names[]=api-service" >/dev/null

    echo "  Done: $repo_slug"
done

echo "All repo variables set."
```

---

### Bulk smoke tests after batch run

After the initial load, validate all produced specs:

```bash
#!/usr/bin/env bash
# tools/validate_all_specs.sh
PASS=0
FAIL=0

for spec in specs/*.yaml; do
  name=$(basename "$spec")
  if spec-engine validate "$spec" --config config.yaml 2>/dev/null; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAILED: $name"
  fi
done

echo ""
echo "Validation summary: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
```

---

### Performance summary

| Scenario | Workers | Includes git clone | Estimated time |
|---|---|---|---|
| 50 repos (Spring/FastAPI) | 8 | Yes (~10s/clone) | 10–20 minutes |
| 150 repos (mixed frameworks) | 16 | Yes | 20–40 minutes |
| 500 repos | 32 | Yes | 45–90 minutes |
| 1,000 repos | 64 (K8s pods) | Yes | 60–120 minutes |
| Per-repo CI step (Approach 1B/2) | 1 | No (checked out) | 45–80 seconds |

**Bottlenecks and mitigations:**

| Bottleneck | Mitigation |
|---|---|
| Git clone network time | Pre-clone to shared NFS/EBS volume before batch; use `--depth 1` |
| Node.js install per repo in CI | Pre-built runner image with spec-engine + Node pre-installed |
| Go binary compilation per run | Binary cached in `/tmp/go_schema_tool_*` for the process lifetime |
| Large repos (1000+ files) | `exclude_paths` in CSV column; scope to `src/` only |
| Sequential file discovery | Already uses `_iter_files()` with early-exit on SKIP_DIRS |

---

## 13. Extending the Engine

### Add a new framework scanner

1. **Create the scanner file:**

```python
# spec_engine/scanner/rails.py
from spec_engine.scanner.base import BaseScanner
from spec_engine.models import RouteInfo, ParamInfo
from spec_engine.config import Config
from pathlib import Path
from typing import List
import re

class RailsScanner(BaseScanner):
    EXTENSIONS = [".rb"]

    def scan(self) -> List[RouteInfo]:
        routes = []
        for file_path in self._iter_files():
            if file_path.name != "routes.rb":
                continue
            try:
                routes.extend(self._parse_routes(file_path))
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug("Rails: error %s: %s", file_path, e)
        return routes

    def _parse_routes(self, file_path: Path) -> List[RouteInfo]:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        rel_path = str(file_path.relative_to(self.repo_path))
        routes = []
        # resources :accounts  →  GET /accounts, POST /accounts, GET /accounts/:id, etc.
        for m in re.finditer(r"resources\s+:(\w+)", source):
            name = m.group(1)
            for method, suffix in [("GET", ""), ("POST", ""), ("GET", "/{id}"), ("PUT", "/{id}"), ("DELETE", "/{id}")]:
                routes.append(RouteInfo(
                    method=method,
                    path=f"/{name}{suffix}",
                    handler=f"{name.capitalize()}Controller",
                    file=rel_path,
                    line=m.start(),
                    framework="rails",
                ))
        return routes
```

2. **Register in `scanner/__init__.py`:**

```python
elif framework == "rails":
    from spec_engine.scanner.rails import RailsScanner
    return RailsScanner(repo_path, config)
```

3. **Add detection in `detect_framework()`:**

```python
# Check for Gemfile
gemfile = root / "Gemfile"
if gemfile.exists():
    content = gemfile.read_text(errors="ignore").lower()
    if "rails" in content:
        return "rails"
```

4. **Write tests:**

```python
# tests/test_scanner_rails.py
class TestRailsScanner:
    def test_resources_generates_crud(self, tmp_path):
        (tmp_path / "routes.rb").write_text("resources :accounts")
        scanner = RailsScanner(str(tmp_path), Config())
        routes = scanner.scan()
        assert any(r.method == "GET" and r.path == "/accounts" for r in routes)
        assert any(r.method == "POST" for r in routes)
```

5. **Write tests:** Run `pytest tests/test_scanner_rails.py -v`

---

### Add a new schema inferrer

1. Create `spec_engine/inferrer/ruby_ast.py` inheriting from `BaseInferrer`
2. Implement `_find_type_file()` and `_extract_fields()`
3. Register in `inferrer/__init__.py`:

```python
INFERRER_MAP = {
    ...
    "rails": "RubyASTInferrer",
}
```

4. Import:
```python
from spec_engine.inferrer.ruby_ast import RubyASTInferrer
```

---

### Add a custom validation rule

In `validator.py`, add a new check function and call it from `validate()`:

```python
def _check_no_inline_schemas(spec_path: str) -> List[str]:
    """Flag operations that use inline schemas instead of $refs."""
    errors = []
    # ... parse YAML, walk paths, check for inline schemas
    return errors

def validate(spec_path: str, config: Config) -> ValidationResult:
    result = ValidationResult()
    result.errors.extend(_run_redocly(spec_path))
    result.errors.extend(_run_spectral(spec_path))
    result.errors.extend(_check_x_fields(spec_path, config))
    result.errors.extend(_check_no_inline_schemas(spec_path))    # NEW
    return result
```

---

### Add a new config field

1. Add to `Config` dataclass in `config.py`:
```python
@dataclass
class Config:
    ...
    my_new_field: str = "default_value"
```

2. Use it anywhere with `config.my_new_field` or `getattr(config, "my_new_field", "fallback")`

3. Set via config file:
```yaml
my_new_field: custom_value
```

4. Or via CLI:
```bash
spec-engine generate --repo . ... # (add --my-new-field option to the Click command)
```

---

## 14. Debugging & Troubleshooting

### Enable debug logging

```bash
spec-engine generate --repo . --verbose
```

This sets logging level to `DEBUG`, printing:
- Every file discovered
- Every route found
- Every type resolution step
- Every AST parse result

### Common errors and fixes

**"No routes found"**
- Check `--framework` matches actual framework
- Check `--repo` points to project root (not a subdirectory)
- Run `spec-engine scan --verbose` to see what files are being discovered
- Check that `exclude_paths` isn't too broad

**"Config.gateway must be set when strict_mode=True"**
- Pass `--gateway <name>` or add `gateway: my-gateway` to `config.yaml`

**"node not found"**
- Node.js is not installed; Express/NestJS scanning falls back to empty routes
- Install Node.js 20+ and re-run

**"go: build failed"**
- Go is not installed; Gin/Echo scanning uses regex fallback
- If regex fallback is insufficient, install Go 1.21+

**"Type defined in N files: ... Set config.prefer_file..."**
- Multiple files define the same class/interface name
- Set `prefer_file: "*/dto/*.java"` in `.spec-engine.yaml` to control selection

**Schema has LOW or MANUAL confidence**
- The type uses reflection, dynamic proxy, or a code pattern the AST parser doesn't understand
- Inspect the source file manually
- Add manual schema override: write a custom `_extract_fields()` for that pattern

### Inspect intermediate outputs

```bash
# See exactly what routes were found
spec-engine scan --repo . --manifest /tmp/manifest.json
cat /tmp/manifest.json | jq '.routes[] | {method, path, handler}'

# See what schemas were inferred
spec-engine schema --manifest /tmp/manifest.json --repo . --out /tmp/schemas.json
cat /tmp/schemas.json | jq 'to_entries[] | {key, confidence: .value.confidence}'

# Assemble without validating
spec-engine assemble --manifest /tmp/manifest.json --repo . --gateway test --out /tmp/spec.yaml
```

### Testing with a real repo locally

```bash
# Clone a sample Spring repo
git clone https://github.com/spring-projects/spring-petclinic /tmp/petclinic

# Run spec generation
spec-engine generate \
  --repo /tmp/petclinic \
  --gateway local \
  --owner dev-test \
  --strict-mode=false \
  --out /tmp/petclinic.yaml \
  --verbose

# Inspect output
cat /tmp/petclinic.yaml | head -80
```

---

## 15. Contributing Checklist

Before submitting a PR, verify:

- [ ] `pytest tests/ -v` — all tests pass
- [ ] `pytest tests/ --cov=spec_engine --cov-report=term-missing` — coverage not regressed
- [ ] New scanner: has `test_scanner_<framework>.py` with ≥ 8 tests
- [ ] New inferrer: has `test_inferrer_<language>.py` with ≥ 10 tests
- [ ] New config field: documented in Config reference table (Section 5)
- [ ] New CLI option: documented in CLI reference table (Section 6)
- [ ] `--verbose` / `--dry-run` options work correctly if applicable
- [ ] No hardcoded paths; all paths relative to `repo_path` or `config.out`
- [ ] Subprocess calls have `timeout=` set and `FileNotFoundError` handled
- [ ] `SchemaResult.empty()` returned (not raised) on all parse failures
- [ ] Framework label uses lowercase constant: `"spring"`, `"fastapi"`, etc.
