# Delta for Jira Description Generation

## MODIFIED Requirements

### Requirement: Transcript-Only Submission

The system MUST send the current transcript text to the Groq API when the analyst requests description generation. WHEN one or more modules clear the context-retrieval threshold, the system MUST also include their retrieved `_modulo.md` content as a single, distinct, delimited context block alongside the transcript. WHEN no module clears the threshold, the system MUST submit only the transcript, unchanged from Fase 1. In all cases the system MUST NOT include any data beyond the transcript and (when present) that delimited context block. Grounding the description in real module documentation strengthens, and MUST NOT weaken, the existing anti-invention guarantee: generated output MUST NOT state or imply any fact — about the transcript or the matched module — that is not literally present in the transcript or the injected context block.

(Previously: transcript-only in every case, with no mechanism for including any context; retrieval context was explicitly prohibited.)

#### Scenario: Analyst triggers generation without a module match

- GIVEN an editable transcript is present on screen and no module cleared the retrieval threshold
- WHEN the analyst clicks "Generar descripción"
- THEN the system MUST submit only that transcript text to the Groq API using the fixed prompt template, unchanged from Fase 1

#### Scenario: Analyst triggers generation with a module match

- GIVEN an editable transcript is present on screen and retrieval matched one or more modules above threshold
- WHEN the analyst clicks "Generar descripción"
- THEN the system MUST submit the transcript plus a distinct delimited block containing only the matched module(s) `_modulo.md` content to the Groq API

#### Scenario: Retrieval degrade produces transcript-only submission

- GIVEN retrieval degraded because `memory/` was missing or unreadable
- WHEN the analyst clicks "Generar descripción"
- THEN the system MUST submit only the transcript, identical to the no-match case

#### Scenario: Prompt instructs grounding to transcript and injected context only

- GIVEN a module's `_modulo.md` content was injected as context
- WHEN the system constructs the Groq prompt
- THEN the prompt instructions MUST explicitly direct the model to use only the transcript and the injected context block, and MUST NOT state or imply facts about the module beyond that literal content
