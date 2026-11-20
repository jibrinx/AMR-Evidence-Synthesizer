# Build validation — 20 November 2026

## Completed checks

| Check | Result |
|---|---|
| Python syntax/import checks | Passed |
| Ruff lint | Passed |
| Ruff formatting | Applied, then checked for release |
| Offline pytest suite | **133 passed** in an isolated Python 3.11 environment with locked runtime dependencies |
| Streamlit UI tests | Passed in both read-only and private modes, with an interactive human approval save |
| End-to-end mocked agent workflow | Passed: source/read → structured pending candidate → human approval → provenance-rich export |
| Agent discovery workflow | Passed with mocked PubMed/provider: search → import → read → submit → finish |
| Permission and invalid-input tests | Passed for the included cases; not a comprehensive penetration test |
| Actual local Streamlit startup | Passed: loopback `/_stcore/health` returned HTTP 200 and `ok` |
| Live PubMed connectivity | Passed: ESearch + EFetch returned real publication metadata/abstracts |

The 133 tests include parameterized cases. An earlier 126-case suite also passed in the original development environment; the expanded final suite passed in the isolated locked-dependency environment without unrelated scientific-package pytest plugins.

## What the tests establish

The included cases check typed validation, count/percentage rounding, missing-denominator behavior, resistance/non-susceptibility separation, exact source matching, citation/document/estimate duplicates, human approval gates, stale-edit protection, transaction rollback, application audit triggers, CSV safety, JSON null preservation, PubMed XML parsing/errors, bounded PDF/TXT intake, narrow-rule false positives, read-only restrictions, and model tool-loop behavior.

Agent tests use scripted tool requests for malformed arguments, nonexistent tools, nonexistent sources, unread/fabricated quotes, attempts to set approval or human eligibility fields, hostile source instructions, repeated actions/resource limits, provider failure, missing usage, and sanitized errors. They test what application code permits, not whether a real model follows instructions.

A short attributed real PubMed abstract excerpt is included only as a negative extraction example. Neither that article nor technical fixtures seed the research database.

## Not completed or not claimed

- **No paid or live model call.** No cloud API credentials were used; no local inference server was run. Real-model extraction accuracy and cloud/local interoperability remain unvalidated.
- **No scientific benchmark.** No precision/recall, population resistance estimate, meta-analysis, or curated Nigerian AMR corpus was produced.
- **Docker unavailable locally.** The Dockerfile/Compose configuration are supplied, but a successful container build is not claimed. GitHub Actions is configured to build/check it after push.
- **No remote GitHub execution or deployment.** No repository was created in the user's account, no remote Actions badge is claimed, and no live web application was published.
- **Python 3.12 not run locally.** The GitHub test matrix includes 3.11/3.12; only 3.11 was executed here.
- **Not a security certification.** No malware sandbox, comprehensive prompt-injection defense, independent penetration test, formal audit, or validated risk-of-bias instrument is claimed.
- **No empirical human curation study.** Reviewer usability, inter-rater agreement, and checklist validity need separate assessment.

## Reproduce and extend

```bash
uv sync --frozen --extra dev
uv run --frozen --extra dev ruff check .
uv run --frozen --extra dev ruff format --check .
uv run --frozen --extra dev pytest
uv run --frozen python scripts/smoke_server.py
```

Before production research, run the remote CI and container check, deploy privately with durable storage/access control, and pilot a chosen tool-capable model against independently adjudicated evidence. See `AGENT.md` for a suggested scientific validation approach.
