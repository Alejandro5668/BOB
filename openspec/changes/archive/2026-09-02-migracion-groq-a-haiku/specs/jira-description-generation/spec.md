# Delta for Jira Description Generation

This delta resolves the file's prior STALE banner: at archive time, remove the
banner and replace the Purpose paragraph's "Groq LLM API" wording with "Claude
Haiku 4.5 (via the shared Anthropic client toolkit)".

## MODIFIED Requirements

### Requirement: Transcript-Only Submission

The system MUST send the current transcript text to Claude Haiku 4.5 via the shared Anthropic client toolkit when the analyst requests description generation. WHEN one or more modules clear the context-retrieval threshold, the system MUST also include their retrieved raw document content as a single, distinct, delimited context block alongside the transcript. WHEN no module clears the threshold, the system MUST submit only the transcript, unchanged from Fase 1. In all cases the system MUST NOT include any data beyond the transcript and (when present) that delimited context block. Grounding the description in real module documentation strengthens, and MUST NOT weaken, the existing anti-invention guarantee: generated output MUST NOT state or imply any fact — about the transcript or the matched module — that is not literally present in the transcript or the injected context block.

(Previously: submission target was the Groq API; injected context was the module's enriched functional summary rather than raw document content.)

#### Scenario: Analyst triggers generation without a module match
- GIVEN an editable transcript is present on screen and no module cleared the retrieval threshold
- WHEN the analyst clicks "Generar descripción"
- THEN the system MUST submit only that transcript text to Claude Haiku 4.5 using the fixed prompt template, unchanged from Fase 1

#### Scenario: Analyst triggers generation with a module match
- GIVEN an editable transcript is present on screen and retrieval matched one or more modules above threshold
- WHEN the analyst clicks "Generar descripción"
- THEN the system MUST submit the transcript plus a distinct delimited block containing only the matched module(s)' raw document content to Claude Haiku 4.5

#### Scenario: Retrieval degrade produces transcript-only submission
- GIVEN retrieval degraded because `memory/` was missing or unreadable
- WHEN the analyst clicks "Generar descripción"
- THEN the system MUST submit only the transcript, identical to the no-match case

#### Scenario: Prompt instructs grounding to transcript and injected context only
- GIVEN a module's raw document content was injected as context
- WHEN the system constructs the Haiku prompt
- THEN the prompt instructions MUST explicitly direct the model to use only the transcript and the injected context block, and MUST NOT state or imply facts about the module beyond that literal content

### Requirement: Structured Markdown Ticket Output

The generated description MUST follow a fixed, locked Markdown template instead of free-form prose. The template MUST begin with a `## Módulo afectado` section — always present, MUST use the fixed fallback text `Módulo afectado: no identificado` when retrieval matched no module, and MUST NOT be omitted under any circumstance — followed by a `## Qué pasó` section, which is always present. The template MAY include an optional `## Pasos para reproducir` section and an optional `## Resultado esperado vs. obtenido` section. For each optional section, the system MUST omit BOTH the heading and the body entirely when the analyst did not state the corresponding information (reproduction steps / an expectation) — the system MUST NOT fill an omitted section with generic placeholder text such as "no especificado". The system MUST NOT invent a generic or speculative expected-vs-obtenido statement when the analyst did not state an expectation; this is an absolute prohibition on the model, not a discouraged pattern. As defense-in-depth, when a present `## Resultado esperado vs. obtenido` body is detected as ungrounded in the transcript or injected context, a separate, conditional Claude Haiku 4.5 grounding-check call MUST replace the body with the fixed notice `Resultado esperado vs. obtenido: no se pudo determinar de forma confiable` rather than silently deleting the section. This grounding check MUST run only when that section is present, MUST NOT be merged into the generation call, and MUST leave the original text unchanged if the check itself fails (missing key, API error, or malformed response) rather than erase real analyst-provided content. The output MUST NOT be wrapped in a code fence and MUST NOT be preceded by any preamble text.

(Previously: the defense-in-depth mechanism was described generically as detecting "generic filler" via an unspecified post-processor; it is now an explicit, conditional, separate Claude Haiku 4.5 grounding-check call with a documented fail-open policy.)

#### Scenario: Full template with module match, steps, and expectation stated
- GIVEN a transcript states an affected module, reproduction steps, and an expected-vs-obtained result
- WHEN the description is generated
- THEN the output MUST contain, in order, `## Módulo afectado`, `## Qué pasó`, `## Pasos para reproducir`, and `## Resultado esperado vs. obtenido`, each with real content drawn from the transcript

#### Scenario: No module matched falls back to fixed notice
- GIVEN retrieval matched no module above threshold
- WHEN the description is generated
- THEN the `## Módulo afectado` section MUST be present and MUST read `Módulo afectado: no identificado`

#### Scenario: Steps not stated omits the section entirely
- GIVEN the analyst never described reproduction steps
- WHEN the description is generated
- THEN the output MUST NOT contain a `## Pasos para reproducir` heading or any placeholder body for it

#### Scenario: Expectation not stated omits the section entirely
- GIVEN the analyst never stated an expected-vs-obtained result
- WHEN the description is generated
- THEN the output MUST NOT contain a `## Resultado esperado vs. obtenido` heading or body

#### Scenario: Model MUST NOT invent a generic expectation
- GIVEN the analyst did not state an expectation
- WHEN the model constructs the response
- THEN the prompt instructions MUST prohibit inventing any generic or speculative expected-vs-obtenido statement, and this prohibition MUST be explicit and absolute (MUST NOT), not merely a recommendation

#### Scenario: Grounding check replaces ungrounded body with fixed notice
- GIVEN the model produced a `## Resultado esperado vs. obtenido` section whose body is not grounded in the transcript or injected context
- WHEN the separate Claude Haiku 4.5 grounding-check call runs over the raw model output
- THEN it MUST replace the body with `Resultado esperado vs. obtenido: no se pudo determinar de forma confiable` and MUST NOT delete the section silently

#### Scenario: Genuine expectation is preserved verbatim
- GIVEN the model produced a `## Resultado esperado vs. obtenido` section whose body states a genuine, transcript-grounded expectation
- WHEN the grounding-check call runs over the raw model output
- THEN it MUST leave that section's body unchanged

#### Scenario: Grounding-check failure keeps original text
- GIVEN the grounding-check call itself fails (missing `ANTHROPIC_API_KEY`, API error, or malformed response)
- WHEN the failure occurs
- THEN the system MUST keep the model's original `## Resultado esperado vs. obtenido` body unchanged and MUST NOT block or abort description generation

#### Scenario: Output has no code fence or preamble
- GIVEN any generated description
- WHEN it is returned to the caller
- THEN it MUST NOT be wrapped in a Markdown code fence and MUST NOT contain preamble text before `## Módulo afectado`

### Requirement: API Key Fail-Fast

The system MUST read the Anthropic API key only from the environment (`ANTHROPIC_API_KEY`) and MUST fail fast with a clear message when it is absent or invalid, rather than proceeding silently or crashing with a raw stack trace.

(Previously: read `GROQ_API_KEY`.)

#### Scenario: Key missing at runtime
- GIVEN `ANTHROPIC_API_KEY` is not set in the environment
- WHEN the analyst clicks "Generar descripción"
- THEN the system MUST show a clear configuration error instead of attempting the API call

#### Scenario: Key present and valid
- GIVEN `ANTHROPIC_API_KEY` is set to a valid value
- WHEN the analyst clicks "Generar descripción"
- THEN the system MUST call Claude Haiku 4.5 via the shared Anthropic client toolkit and MUST NOT expose the key value in the UI or logs

### Requirement: Module Testability

The description-generation logic MUST be callable and testable as a standalone module, using a mocked Anthropic client (`FakeAnthropic`), without a running Streamlit session.

(Previously: used a mocked Groq client (`FakeGroq`).)

#### Scenario: Unit test invokes generation directly with mocked client
- GIVEN a test imports the generation module and injects a mocked Anthropic client
- WHEN it calls the generation function with a sample transcript
- THEN the system MUST return a description without making a real network call
