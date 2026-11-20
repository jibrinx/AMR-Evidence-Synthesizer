# Security and responsible research use

This is early research software, not an authenticated multi-tenant service or regulated system.

## Deployment boundary

- Default `AMR_READ_ONLY=true` disables mutations and AI execution in the UI and store.
- Public read-only access is **not confidentiality**: source text, review records, and exported data may be visible. Publish only authorized material.
- Editable mode requires host/network authentication, TLS, restricted operator access, and backups. Reviewer names are not verified identities.
- Do not expose an editable app or model server to anonymous Internet access.
- SQLite is for a small, single-instance workspace with durable local storage. Concurrent edits use an optimistic timestamp check, but this is not a distributed database.
- Audit triggers prevent normal update/delete operations, not privileged tampering.

## Files and model actions

- Only PDF/TXT intake is offered. Size/page/text caps reduce accidental overload; they are not a malware scanner, decompression-bomb defense, or isolated PDF sandbox. Process trusted, authorized publications and keep PDF dependencies updated.
- Original PDFs are not retained; extracted text, source quotes, goals, records, and operational logs are retained in the database.
- The agent has a fixed tool allowlist, run-scoped source access, and local argument/source validation. No arbitrary shell, SQL, URL fetch, or approval capability is available.
- Treat document instructions and model messages as untrusted. Pending candidates can still be wrong despite valid quotes.
- Spreadsheet exports escape dangerous text prefixes. JSON retains original text and should not be pasted into executable contexts.

## Secrets and external services

- Use environment variables or root-level Streamlit secrets; never commit `.env`, `secrets.toml`, databases, or keys.
- Endpoint configuration is operator-only. Review the destination and local-server routing before enabling AI. HTTPS is required for cloud endpoints.
- API keys are sent only in the provider Authorization header; raw authentication errors are not surfaced by the adapter. Do not put secrets in research goals, uploaded publications, or model names.
- Consent is required for each run. Check publication rights and the provider's data-processing terms separately.
- Set provider-side spend limits. App counters are not a dollar guarantee.

## Reporting an issue

Before opening a public GitHub issue, remove keys, patient details, unpublished text, and database contents. Use your repository's private vulnerability reporting channel if available; the repository owner should configure it. Do not attach a full research database to a public issue.
