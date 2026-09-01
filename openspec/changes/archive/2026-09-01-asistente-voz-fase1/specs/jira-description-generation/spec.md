# Jira Description Generation Specification

## Purpose

Enables an analyst to convert an approved (possibly edited) transcript into an editable, Spanish-prose, plain-language Jira-ready description using the Groq LLM API, without retrieval context or sectioned ticket format (both deferred to later phases). Output must stay understandable to a non-technical reader — no invented implementation detail.

## ADDED Requirements

### Requirement: Transcript-Only Submission

The system MUST send only the current transcript text to the Groq API when the analyst requests description generation; it MUST NOT include retrieval context or unrelated data.

#### Scenario: Analyst triggers generation

- GIVEN an editable transcript is present on screen
- WHEN the analyst clicks "Generar descripción"
- THEN the system MUST submit only that transcript text to the Groq API using a fixed prompt template

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
