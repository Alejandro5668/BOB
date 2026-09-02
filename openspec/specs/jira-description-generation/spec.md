# Jira Description Generation Specification

## Purpose

Enables an analyst to convert an approved (possibly edited) transcript into an editable, Spanish-prose, plain-language Jira-ready description using the Groq LLM API, without retrieval context or sectioned ticket format (both deferred to later phases). Output must stay understandable to a non-technical reader — no invented implementation detail.

## ADDED Requirements

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

### Requirement: Structured Markdown Ticket Output

The generated description MUST follow a fixed, locked Markdown template instead of free-form prose. The template MUST begin with a `## Módulo afectado` section — always present, MUST use the fixed fallback text `Módulo afectado: no identificado` when retrieval matched no module, and MUST NOT be omitted under any circumstance — followed by a `## Qué pasó` section, which is always present. The template MAY include an optional `## Pasos para reproducir` section and an optional `## Resultado esperado vs. obtenido` section. For each optional section, the system MUST omit BOTH the heading and the body entirely when the analyst did not state the corresponding information (reproduction steps / an expectation) — the system MUST NOT fill an omitted section with generic placeholder text such as "no especificado". The system MUST NOT invent a generic or speculative expected-vs-obtenido statement when the analyst did not state an expectation; this is an absolute prohibition on the model, not a discouraged pattern. As defense-in-depth, when a present `## Resultado esperado vs. obtenido` body is detected as generic filler, a post-processing step MUST replace the body with the fixed notice `Resultado esperado vs. obtenido: no se pudo determinar de forma confiable` rather than silently deleting the section; this post-processor is best-effort and MUST NOT be relied upon as eliminating the underlying invention risk, which is primarily controlled via the prompt template. The output MUST NOT be wrapped in a code fence and MUST NOT be preceded by any preamble text.

(Previously: "Spanish Prose Output" — the generated description was free-form Spanish prose without sectioned ticket structure; context/repro-steps/expected-vs-actual sections were explicitly out of scope.)

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

#### Scenario: Post-processor replaces generic filler with fixed notice

- GIVEN the model produced a `## Resultado esperado vs. obtenido` section whose body is only generic filler
- WHEN the post-processor runs over the raw model output
- THEN it MUST replace the body with `Resultado esperado vs. obtenido: no se pudo determinar de forma confiable` and MUST NOT delete the section silently

#### Scenario: Genuine expectation is preserved verbatim

- GIVEN the model produced a `## Resultado esperado vs. obtenido` section whose body states a genuine, transcript-grounded expectation
- WHEN the post-processor runs over the raw model output
- THEN it MUST leave that section's body unchanged

#### Scenario: Output has no code fence or preamble

- GIVEN any generated description
- WHEN it is returned to the caller
- THEN it MUST NOT be wrapped in a Markdown code fence and MUST NOT contain preamble text before `## Módulo afectado`

### Requirement: Plain-Language, Non-Technical Output

The generated description MUST describe the observed problem in plain language a non-technical reader (the analyst) can understand and verify. It MUST NOT invent or reference internal implementation details (e.g. class names, functions, code structure) that were not explicitly present in the transcript or supplied context — the goal is a precise, faithful description of the reported error/behavior, not a speculative technical diagnosis.

#### Scenario: Generated text avoids implementation jargon

- GIVEN a transcript describing a user-observed error (e.g. "al entrar al módulo de riesgos y hacer clic aquí, sale este error")
- WHEN the system generates the description
- THEN the output MUST describe the observed behavior/error in plain terms and MUST NOT state or imply internal implementation causes (e.g. "la función X falla", "la clase Y no valida esto") that weren't given as fact in the input

### Requirement: Editable Generated Description

The generated description MUST appear in an editable text box so the analyst can adjust it before copying it elsewhere.

#### Scenario: Analyst edits the generated text

- GIVEN a description has been generated
- WHEN the analyst modifies the text in its box
- THEN the system MUST retain the edited version for copy/paste

### Requirement: API Key Fail-Fast

The system MUST read the Groq API key only from the environment (`GROQ_API_KEY`) and MUST fail fast with a clear message when it is absent or invalid, rather than proceeding silently or crashing with a raw stack trace.

#### Scenario: Key missing at runtime

- GIVEN `GROQ_API_KEY` is not set in the environment
- WHEN the analyst clicks "Generar descripción"
- THEN the system MUST show a clear configuration error instead of attempting the API call

#### Scenario: Key present and valid

- GIVEN `GROQ_API_KEY` is set to a valid value
- WHEN the analyst clicks "Generar descripción"
- THEN the system MUST call the Groq API and MUST NOT expose the key value in the UI or logs

### Requirement: Module Testability

The description-generation logic MUST be callable and testable as a standalone module, using a mocked Groq client, without a running Streamlit session.

#### Scenario: Unit test invokes generation directly with mocked client

- GIVEN a test imports the generation module and injects a mocked Groq client
- WHEN it calls the generation function with a sample transcript
- THEN the system MUST return a description without making a real network call

### Requirement: Centralized Prompt Repository

All system and user prompt text used for description generation MUST be defined as named constants in a dedicated `prompts.py` module rather than inline in `generar_descripcion.py`. Each prompt constant's name MUST be role-descriptive (e.g. `GENERADOR_DESCRIPCION_TICKET`) and MUST be accompanied by a short docstring or comment stating its role/use case. `generar_descripcion.py` MUST import prompt text from `prompts.py` and MUST NOT define prompt text inline.

#### Scenario: Prompt constants are centralized and documented

- GIVEN the `prompts.py` module
- WHEN any system or user prompt constant used by description generation is inspected
- THEN it MUST have a role-descriptive name and a short docstring or comment describing its use case

#### Scenario: generar_descripcion.py has no inline prompt text

- GIVEN `generar_descripcion.py`
- WHEN its source is inspected for prompt text
- THEN it MUST reference prompts only via imports from `prompts.py`, with no prompt text literals defined inline
