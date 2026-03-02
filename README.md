# spec-engine

Automated OpenAPI 3.1 spec generator for enterprise API repositories.

## Pipeline Stages

| # | Stage | Input | Output |
|---|-------|-------|--------|
| 1 | Repo Scanner | Git repo / local path | Route manifest (JSON) |
| 2 | Framework Analyzer | Route manifest + source | Annotated route map |
| 3 | Schema Inferrer (AST) | Route map + model files | JSON Schema definitions |
| 4 | Spec Assembler | Route map + schemas | Raw OpenAPI 3.1 YAML |
| 5 | Validator & Linter | Raw YAML | Validated, linted spec |

## Quick Start

```bash
pip install -e .
spec-engine generate --repo /path/to/api --gateway kong-prod --owner my-team
```

## Requirements

- Python 3.11+
- Node.js 20+ (for TypeScript/Express scanning)
- `npm install -g @redocly/cli @stoplight/spectral-cli`
