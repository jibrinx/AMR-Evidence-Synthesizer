# AMR Evidence Synthesizer

**Agentic, source-grounded extraction of published Nigerian antimicrobial-resistance estimates — with human-only evidence approval.**

Version 0.1.0 is a single-workspace research application. It is not a finished systematic review, a pre-populated Nigerian resistance database, or clinical decision support.

## What works

- **Discover:** bounded PubMed searches with year filters and abstract import.
- **Upload:** text-based PDFs or UTF-8 text; page-level text and content hashes.
- **Agent:** a genuine iterative model/tool loop that can search, import a discovered abstract, inspect source passages, and submit structured **pending** estimates.
- **Review:** source text beside editable organism–antibiotic–outcome–stratum records, reporting flags, a reviewer-assisted quality checklist, and named decisions.
- **Database:** filters and provenance-rich CSV/JSON exports; approved records only by default.
- **No-key fallback:** narrow narrative rules and manual entry work without an AI account.
- **Deployment:** dependency locks, automated tests, GitHub Actions, a non-root Docker image recipe, persistent-volume configuration, and public read-only mode.

**Validation:** software workflow/boundary tests and live PubMed connectivity have been checked. Real-model extraction accuracy, local model compatibility, and the container build have not been validated in the build environment. Read [docs/VALIDATION.md](docs/VALIDATION.md) before research use.

## Quick start

Requirements: Python 3.11 or 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --frozen --extra dev
# Private, local review workspace. Do not expose editable mode publicly.
AMR_READ_ONLY=false uv run --frozen streamlit run app.py --server.address=127.0.0.1
```

Open `http://localhost:8501`. On PowerShell, set `$env:AMR_READ_ONLY="false"` first, then run the `uv run` command without the leading assignment.

Without that setting, the app starts in **public read-only mode**: no uploads, imports, editing, rules, or AI execution. An absent database appears as an empty read-only workspace. The app never seeds invented study records.

### Tests

```bash
uv run --frozen --extra dev ruff check .
uv run --frozen --extra dev ruff format --check .
uv run --frozen --extra dev pytest
uv run --frozen python scripts/smoke_server.py
```

Tests block unmocked HTTP/AI calls. Scripted model outputs and numeric edge cases are explicitly technical fixtures, not scientific data or real-model benchmarks. The server smoke check uses one loopback health request and no AI or PubMed calls.

## Enable agentic AI

The agent uses a configurable **OpenAI-compatible chat-completions function-tool protocol**. A provider/model must support that protocol, JSON-schema tool definitions, and `max_tokens`. Compatibility is not guaranteed for every model or API with an “OpenAI-compatible” label. No particular paid model is required.

Configure these values on the **server**, not in agent instructions or a public form:

```bash
export AMR_READ_ONLY=false
export AMR_AI_ENABLED=true
export AMR_AI_BASE_URL="https://api.openai.com/v1"
export AMR_AI_MODEL="YOUR_TOOL_CAPABLE_CHAT_MODEL"
# Inject AMR_AI_API_KEY through your host's secret manager or private shell.
uv run --frozen streamlit run app.py --server.address=127.0.0.1
```

Do not commit keys. `.env.example` lists all settings; the app **does not automatically load `.env`**. Docker Compose reads it, or configure environment variables / root-level Streamlit secrets directly.

For a local compatible model server:

```bash
export AMR_AI_BASE_URL="http://localhost:11434/v1"
export AMR_AI_MODEL="YOUR_INSTALLED_TOOL_CAPABLE_LOCAL_MODEL"
export AMR_ALLOW_LOCAL_HTTP=true
export AMR_AI_API_KEY=""
```

The model server must be reachable **from the app server**. `localhost` in a cloud deployment is not your laptop. In Docker, an explicitly configured `host.docker.internal` endpoint can be used where the host supports it; do not expose a model server to the public Internet. Local inference/model downloads are supplied by the operator and were not tested during this build.

In **Agent**, select up to five sources, optionally permit PubMed discovery, enter a goal, inspect the displayed destination/limits, consent to data transfer, then click **Run agent**. There are no autonomous scheduled runs. Review the completion state and every resulting candidate.

### Agent capabilities and limits

Allowed tools: `search_pubmed`, `import_abstract`, `list_pages`, `read_passage`, `submit_candidate`, `finish`.

The agent cannot execute code, open arbitrary paths/URLs, run SQL, edit provider configuration, approve evidence, confirm Nigeria eligibility, or change human assessments. Candidate submission requires a quote that the agent actually read and that matches its source page. A matching quote **does not prove the extracted fields are correct**.

Default limits per run:

| Control | Limit |
|---|---:|
| Model requests | 8 |
| Tool calls | 12 |
| PubMed searches | 3 |
| Discovered abstracts retained | 20 |
| Initially selected sources | 5 |
| Source text/metadata exposure budget | 60,000 characters |
| Serialized conversation budget before a model request | 120,000 characters |
| Requested model output | 2,000 tokens per request |
| Run deadline | 300 seconds, checked between bounded operations |

An in-flight network operation may finish or time out after the deadline; it is not a hard real-time process kill. Requests have individual network timeouts. Providers may interpret token settings differently. These limits **are not an exact monetary cap**: configure provider-side budgets too. Usage is recorded when returned; missing or partially reported usage is explicitly unknown/incomplete. Valid partial outputs stay pending after failures.

See [docs/AGENT.md](docs/AGENT.md) for tool boundaries and logs.

## Research workflow

1. Search/import or upload material you are authorized to process. Do not upload identifiable patient data. Original PDFs are not stored; extracted text is.
2. Confirm citation details and screen study eligibility. PubMed results can be irrelevant.
3. Run the agent, conservative rules, or enter candidates manually.
4. Verify organism, antibiotic, resistance definition, number mapping, tested denominator, sampling unit, subgroup, dates, and source passage.
5. Record quality judgments and reasons. The six-domain checklist is **not a validated risk-of-bias instrument**. Unassessed domains remain visible; approval is not a high-quality designation.
6. A named human confirms Nigeria eligibility and approves/rejects. Approval requires a defined outcome, organism, antibiotic, exact evidence quote, and a reported percentage or count pair. Resolve count/percentage inconsistencies first. Denominator-free percentages retain a missing-denominator flag.
7. Export approved records; explicitly select other statuses only if needed. JSON preserves nulls and nested structures. CSV contains JSON strings for nested fields and prefixes dangerous spreadsheet text with an apostrophe.

See [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md).

## Deploy from GitHub

The public source repository is at https://github.com/jibrinx/AMR-Evidence-Synthesizer.

1. Clone the repository or push future changes to `main`:

   ```bash
   git clone https://github.com/jibrinx/AMR-Evidence-Synthesizer.git
   cd AMR-Evidence-Synthesizer
   git pull --ff-only
   ```

2. Inspect the Actions tab. The included workflow tests Python 3.11/3.12 and separately builds and smoke-checks Docker.
3. For a public demonstration, connect the repository to Streamlit Community Cloud, select `app.py`, and use Python 3.11 or 3.12. Keep `AMR_READ_ONLY="true"` and `AMR_AI_ENABLED="false"`. Dependencies are installed from `requirements.txt` and the pinned `requirements.lock`.
4. For editable research work, deploy behind hosting-level access control with a durable database volume. **Do not treat Community Cloud's local filesystem as a backed-up research database.** This application has no built-in login.

Root-level Streamlit secrets can contain configuration keys such as:

```toml
AMR_READ_ONLY = "true"
AMR_AI_ENABLED = "false"
```

Keep `.streamlit/secrets.toml` out of Git. Do not enable paid AI for anonymous users.

### Docker deployment

```bash
cp .env.example .env
# Edit .env; leave read-only for public use.
docker compose up --build
```

Compose binds the app to `127.0.0.1:8501` and mounts a named volume at `/data`. For a private review workspace set `AMR_READ_ONLY=false` in `.env`, and optionally configure AI. Place TLS/authentication at a trusted reverse proxy or private network boundary before remote exposure. The image runs as UID 10001; bind-mounted data directories must be writable by that UID.

Persist and back up the SQLite file while the service is stopped (or use SQLite's backup API for online backup). Do not delete the Docker volume. Never commit your database or source corpus to GitHub. Existing schema versions are checked; future incompatible schemas require an explicit migration, not silent overwriting.

### Dependency maintenance

`uv.lock` pins the development/runtime resolution. `requirements.lock` is the corresponding runtime export for container/Streamlit installs. After intentionally changing dependencies:

```bash
uv lock
uv export --frozen --no-dev --no-hashes --no-emit-project --format requirements-txt --output-file requirements.lock
uv sync --frozen --extra dev
uv run --frozen --extra dev pytest
```

Do not commit `.venv`, credentials, PDFs, private extracted text, or local databases.

## Scope and limitations

- Published Nigerian human, animal, environmental, or mixed AMR studies; human eligibility confirmation is mandatory.
- Discovery uses PubMed, not a comprehensive multi-database systematic search. No automatic paywall access.
- PDFs: 20 MB, 100 pages, up to two million extracted characters. No OCR. Partial/scattered text or broken table layout may require manual correction even when intake succeeds.
- Rules recognize only a small explicit organism/drug vocabulary and narrow narrative patterns. They prioritize abstention, not recall. Agent extraction can still misinterpret tables, negation, strata, or methods.
- No automatic meta-analysis, patient prevalence inference, causal claims, or clinical recommendations.
- Exact quotation checks, structured schemas, and tests are **software safeguards, not external scientific validation**.
- Single workspace, SQLite, named but unauthenticated reviewer identity, application-level audit history. Not a regulated validated system, tamper-proof ledger, or high-concurrency multi-tenant service.
- Public read-only mode exposes the workspace's source text and records to viewers; it is not a confidentiality boundary. Host only material authorized for that audience.

## Project layout

```text
app.py                         Streamlit interface
src/amr_evidence/
  models.py                    Scientific contracts and flags
  store.py                     SQLite, review gates, audit, run storage
  pubmed.py / intake.py         Search and document import
  agent.py / config.py          Bounded tool loop and provider adapter
  extraction.py / export.py     No-key rules and safe data exports
tests/                         Offline unit/integration/UI tests
scripts/smoke_server.py         Foreground runtime startup check
docs/                          Dictionary, agent guide, validation
.github/workflows/ci.yml        Tests and container check on GitHub
```

## License

Application code: MIT; see `LICENSE`. Publication text and metadata are not relicensed by this repository. The small attributed real abstract excerpt under `tests/fixtures/` is a parser test example, not an approved study or a redistributed evidence corpus. See `tests/fixtures/README.md` and [SECURITY.md](SECURITY.md).
