# Test data provenance

- All `[TEST ONLY]` strings, arithmetic edge cases, publication placeholders, and scripted provider responses in the tests are technical software fixtures. They are not published Nigerian AMR estimates, scientific simulations, or evidence that any model extracts accurately.
- `pubmed_example.json` contains attributed metadata and a short literal excerpt from the abstract identified in that file. It was retrieved through PubMed during build validation. The original record is linked in `source_url`; publication content remains subject to its own rights.
- The real example is deliberately a **negative** rule-extraction case: a search result mentioning resistant organisms is not necessarily an eligible population resistance estimate. It is not imported into the app automatically or marked human-approved.
- Automated tests are offline. PubMed/AI HTTP calls use explicit mocks; unmocked requests fail the suite.
