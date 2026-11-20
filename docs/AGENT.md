# Supervised agent operating guide

## What makes the workflow agentic

After an explicit user Run action, the model chooses its next allowlisted tool using results from earlier actions. The application executes validated tool requests and returns observations for another model decision. The loop ends with `finish`, an error, or a resource limit. This is not a single “extract this paper” prompt and does not depend on a multi-agent framework.

The backend is a small auditable state machine in `agent.py`; it does not need a heavyweight agent platform. Tool schemas are sent as JSON Schema, and all arguments are validated again locally. Models without function-tool support fail without bypassing approval.

## Capability boundary

| Tool | Allowed operation | Boundary |
|---|---|---|
| `search_pubmed` | Retrieve candidate publication metadata | Requires run-specific discovery permission; fixed NCBI endpoint and bounded results |
| `import_abstract` | Add a discovered abstract as a source | PMID must have been discovered in this run; no arbitrary URL |
| `list_pages` | Inspect page numbers/lengths | Only sources selected by user or imported in this run |
| `read_passage` | Read a page substring by character offsets | Allowed source and valid page; ≤12,000 characters per call |
| `submit_candidate` | Validate and create/reuse an estimate | Quote must be in a passage read in this run and in the stored page; new records always pending |
| `finish` | Stop with a short operational message | Message is labeled unvalidated and has no approval effect |

No tool offers approval, reviewer changes, arbitrary browsing, shell/code execution, filesystem access, SQL, endpoint changes, or credentials. Model attempts to call nonexistent tools or add fields such as `status="approved"` are rejected. Identical submissions can reuse an already reviewed record, but never overwrite that decision.

The application checks traceability and numeric consistency, **not semantic entailment**. A model can copy a valid quote but map its percentage to the wrong drug, organism, place, or subgroup. Human review is essential.

## Source text and prompt injection

Treat all uploaded text, metadata, and abstracts as untrusted. Instructions inside them do not authorize actions. The prompt says to ignore embedded instructions, but the stronger safeguard is the small tool capability set and server-side validation.

Tests script hostile tool requests to verify the application refuses them. They do **not** demonstrate that every real model will ignore prompt injection or extract data correctly. A manipulated model may still waste bounded calls, make irrelevant PubMed queries, submit bad pending candidates, or include unsupported language in its finish message. Never use that message as a scientific result.

## Data transfer and privacy

The displayed operator-configured model destination receives the goal, tool definitions, tool-call arguments/results, publication metadata, and selected source passages. Calls may resend earlier context. Do not assume character limits equal unique characters or total billed tokens.

Consent is per run. The application does not obtain processing rights for you. Do not upload patient identifiers, unpublished confidential data, or material you cannot send to the chosen provider. Provider retention/processing policies are outside this application. Local-compatible configuration only changes the destination; operators must verify the model server is actually local and whether it forwards any requests.

Credentials are server configuration, excluded from Git and omitted from operational logs. HTTPS is required except explicitly enabled loopback/local Docker HTTP addresses. Cloud redirects are not followed by the provider adapter. Endpoint configuration must remain operator-controlled.

## Stopping and failures

Limits are documented in README and saved in each run. There are no automatic infinite retries, scheduled re-runs, or resumptions. The deadline is cooperative between bounded operations, not a hard OS process kill. Provider timeouts, malformed responses, unsupported tools, and resource exhaustion produce visible error/incomplete states. Valid candidates already saved remain pending; no approval is implied.

A model message without `finish` is incomplete, even if it sounds conclusive. A completed run only means the loop finished, not that it found all relevant estimates or that submitted data are correct.

The provider must support chat completions, tools, and the configured token parameter. Native tool schemas are not assumed to be enforced by the provider; Pydantic enforcement occurs locally. Provider-specific APIs, pricing, and model capabilities can change. Run a small private, manually checked pilot with your chosen model before research-scale use.

## Logs

Run records contain the model and destination, prompt version, initial source IDs, goal, discovery permission, limits, counters, token totals when supplied, usage completeness, candidate IDs, status, timestamps, and finish/error message. Tool event records contain the tool name and success/failure/result-key metadata. Estimate/audit records contain the evidence and later human corrections.

These are operational records, not hidden model reasoning or a full request/response transcript. They support traceability, not exact deterministic model replay or tamper-proof regulatory auditing. Restrict database access accordingly.

## Pilot validation before relying on AI extraction

Select a representative set of authorized Nigerian studies, including tables, mixed strata, resistance/non-susceptibility definitions, absent denominators, and multiple species/drugs. Have independent human curators establish an adjudicated reference. Compare the chosen agent/model's estimate recall, field accuracy, unsupported-value rate, citation correctness, and abstention behavior. Record model/version, prompt version, cost, and time. Keep the pilot distinct from the software tests included here.
