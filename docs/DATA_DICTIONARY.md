# Data dictionary — schema version 1

The application stores publications, immutable source pages, candidate estimates, human review decisions, audit events, and agent-run activity. Exported records are estimate-level, not one row per publication.

## Publication and source

| Field | Meaning |
|---|---|
| `study.title` | Publication title; required |
| `study.pmid`, `study.doi` | Optional identifiers; DOI is normalized for exact duplicate detection |
| `study.year` | Publication year, not collection year |
| `study.authors`, `study.journal` | Optional metadata |
| `source_id` | Database-local integer source identifier |
| `source_name`, `source_kind` | Original label and `pdf`, `text`, or `abstract` |
| `source_sha256` | SHA-256 of canonical JSON containing extracted page strings, **not original PDF bytes** |
| `page` | One-based extracted PDF page index; text and abstracts use 1 |
| `quote` | Exact contiguous substring of the identified source page |

Source text is immutable in the interface. Correct extraction outside this app and import a new source if needed. Identical extracted page content is deduplicated; conflicting publication assignments are reported. Sources with different layouts/text can still be the same underlying study, so duplicate cohorts require reviewer investigation.

## Estimate fields

| Field | Meaning / constraints |
|---|---|
| `organism_raw`, `antibiotic_raw` | As reported; required for approval |
| `organism_normalized`, `antibiotic_normalized` | Optional curator-friendly names; raw values are preserved |
| `outcome` | `resistant`, `non_susceptible`, `intermediate`, or `unknown`; unknown cannot be approved |
| `mapping_uncertain` | Explicit unresolved organism–antibiotic–stratum ambiguity; blocks approval while true. False is not proof of a correct mapping |
| `numerator` | Optional reported outcome count, integer ≥0 |
| `denominator` | Optional reported **tested** count, integer >0 |
| `reported_percentage` | Optional numeric string in [0,100], without `%`; retains reported decimal precision |
| `sampling_unit` | Literal unit, e.g. isolates, patients, specimens; no automatic conversion |
| `stratum` | Subgroup / organism–drug mapping qualifier to distinguish estimates |
| `country`, `location`, `setting` | Reported geography/context, not eligibility decisions |
| `collection_dates` | Free text as reported; never inferred from publication year |
| `sector` | `human`, `animal`, `environmental`, `mixed`, or `unknown` |
| `specimen` | Reported specimen/material |
| `ast_method` | Antimicrobial susceptibility testing method |
| `breakpoint_standard`, `breakpoint_version` | Reported standard and version/year, if available |
| `reported_ci` | Confidence interval as reported; no interval is generated |
| `notes` | Extraction/reviewer notes |
| `ai_observations` | Unvalidated model observations; kept separate from human quality assessments |

Counts above one billion are rejected as input errors. Numerator cannot exceed denominator. Missing optional text is null. Percentages are never used to back-calculate counts. A denominator can be absent for an approved *reported percentage*, but its absence remains flagged.

For count/percentage consistency, compute `100*n/d` only for a validation check and compare against the reported value using half a unit at its displayed decimal precision. This does not replace the reported percentage. A conflict blocks approval until corrected.

## Human review

| Field | Meaning |
|---|---|
| `review_status` | Pending by default, or human-approved/rejected |
| `review.reviewer` | Named reviewer identity; **not an authenticated identity** |
| `review.nigeria_eligible` | Explicit human confirmation, not inferred from title or country field |
| `review.rationale` | Human explanation |
| `review.assessments` | Domain judgments and rationales |
| `flags` | Missing-information and consistency warnings derived from current fields |
| `created`, `updated` | UTC timestamps |

Checklist domains: `sampling`, `population`, `ast_breakpoints`, `denominator`, `isolate_deduplication`, `interpretation`.

Judgments: `not_assessed`, `low_concern`, `some_concern`, `high_concern`, `unclear`. Any assessed judgment requires a rationale. Domains may remain unassessed; **approval does not imply all domains were assessed or that a study is high quality**. No aggregate score is calculated.

Approval also requires source matching, organism, antibiotic, defined outcome, and a usable proportion/count pair. All field mappings and scientific judgments remain the reviewer's responsibility.

## Provenance and audit

- `schema_version`: export contract version.
- `estimate_id`: local identifier; do not assume global uniqueness across databases.
- `extraction_method`: `manual`, `rules`, or `agent`; records original creation method.
- `agent_run_id`: originating run, if created by agent. Exact duplicates reuse the original record rather than overwriting its provenance or human decision.
- Audit entries retain before/after content, actor string, action, and timestamp. Ordinary application update/delete operations on the audit table are blocked by triggers; administrators can still alter the database.
- Agent runs retain model/destination, prompt version, goal, permitted scope, limits, counters, usage availability, outcome, and linked candidate IDs. Tool events retain operational success/failure metadata; private model reasoning is not stored.

Default exports contain approved estimates only. Other statuses must be selected explicitly. Each exported estimate embeds its publication metadata and human assessment. JSON includes an export timestamp and true nulls; CSV serializes nested objects as JSON and uses empty cells for nulls. Spreadsheet protection can add a leading apostrophe to text; use JSON when lossless text fidelity matters.

## SQLite layout

`studies` and `sources` store citation/source objects. `estimates` contains the scientific object, status, review JSON, fingerprint, and creation provenance. `audit` is application-append-only. `runs` and `events` contain operational agent records.

`PRAGMA user_version=1` guards compatibility. Initialization creates a new database; incompatible versions are refused. Back up before upgrading; no legacy-schema migration is needed or supplied for this first release.
