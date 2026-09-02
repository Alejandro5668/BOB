# Delta for Context Retrieval

## MODIFIED Requirements

### Requirement: Schema-Free Discovery and Haiku-Assisted Selection

The system MUST discover every `.md` file anywhere under `MEMORY_DIR`, regardless of folder layout, and MUST NOT require any fixed index file or per-module naming convention. The system MUST send a lightweight preview listing of candidate documents to Claude Haiku 4.5 and MUST select only paths Haiku returned that were actually present in that listing, capped at a fixed maximum count.

(Previously: selection was performed by Groq (`gpt-oss-20b`/`120b`); discovery, listing mechanics, and the selection cap are otherwise unchanged.)

#### Scenario: Flat or nested corpus discovered without a fixed schema
- GIVEN `MEMORY_DIR` contains `.md` files in an arbitrary folder layout with no index file
- WHEN discovery runs
- THEN every `.md` file MUST be found as a candidate regardless of its folder depth or naming convention

#### Scenario: Model never invents a path
- GIVEN Haiku's selection response names a path not present in the listing
- WHEN the system reads that response
- THEN the invented path MUST be discarded and MUST NOT appear in the final selection

### Requirement: Raw Full-Document Context Block Assembly

When assembling context for the final-selected documents, the system MUST use each document's verbatim raw content. No enriched or summarized intermediate form MUST be produced, consulted, or fallen back to at this stage. The system MUST preserve selection order when building blocks.

(Previously: "Enriched-or-Raw Context Block Assembly" — used an enriched functional summary when available and fell back to raw content only when enrichment failed or was never produced.)

#### Scenario: Selected document injected as raw content
- GIVEN a document was selected by Haiku
- WHEN the context block for that document is assembled
- THEN the block MUST contain that document's verbatim raw content, not a summary

#### Scenario: Selection order preserved across blocks
- GIVEN two or more documents were selected
- WHEN blocks are assembled
- THEN blocks MUST appear in the same order as the original selection

### Requirement: Bounded Context Size

The system MUST enforce a 120,000-character budget (~30K tokens) across all injected raw document blocks and MUST truncate deterministically rather than exceed it.

(Previously: enforced an unspecified "configured budget" implicitly sized for enriched-summary content; the concrete raw-content budget value is new.)

#### Scenario: Combined raw content exceeds budget
- GIVEN the concatenated raw content of the selected documents exceeds 120,000 characters
- WHEN context is assembled
- THEN the system MUST truncate deterministically to fit within the 120,000-character budget

#### Scenario: Combined raw content within budget
- GIVEN the concatenated raw content is within 120,000 characters
- WHEN context is assembled
- THEN the content MUST be included unmodified
