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

### Requirement: Spanish Prose Output

The generated description MUST be free-form Spanish prose without sectioned ticket structure; context/repro-steps/expected-vs-actual sections are out of scope for this phase.

#### Scenario: Description generated from transcript

- GIVEN a valid transcript was submitted
- WHEN the Groq API returns a result
- THEN the system MUST display it as unstructured Spanish prose, not a sectioned template

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
