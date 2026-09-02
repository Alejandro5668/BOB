# Documentation Q&A Specification

## Purpose

Enables an analyst to ask a free-form informational question about Kawak
module behavior (e.g. "cómo funciona el módulo de riesgos") and receive an
answer grounded only in retrieved `memory/` documentation via Claude Haiku
4.5 — a distinct mode from `jira-description-generation`'s incident-ticket
generation. Client construction, retry, and the shared Anthropic toolkit are
inherited from the `context-retrieval` and `jira-description-generation`
specs and are not restated here. Output must stay understandable to a
non-technical reader, must surface uncertainty honestly rather than assert a
single confident answer, and must be able to ask back when the question
itself is ambiguous.

## ADDED Requirements

### Requirement: Plain-Language, Non-Technical Answers

The generated answer MUST describe module behavior in plain language a
non-technical reader (the analyst) can understand and verify. It MUST NOT
invent or reference internal implementation details (e.g. class names,
functions, code structure) not explicitly present in the retrieved context —
mirroring the same bar `jira-description-generation`'s "Plain-Language,
Non-Technical Output" requirement applies to ticket descriptions.

#### Scenario: Answer avoids implementation jargon

- GIVEN an analyst asks how a module behaves in a given situation
- WHEN the system answers using retrieved context
- THEN the output MUST describe the behavior in plain terms and MUST NOT
  state or imply internal implementation causes (e.g. "la función X valida
  esto") not literally present in that context

### Requirement: Full Raw-Context Grounding

Q&A answers MUST be grounded in the same full raw-document context assembly
the `context-retrieval` domain specifies (see "Raw Full-Document Context
Block Assembly" and "Bounded Context Size") — Q&A MUST NOT use a separate,
reduced, or summarized retrieval path.

#### Scenario: Q&A reuses the shared raw-context pipeline

- GIVEN an analyst submits a question
- WHEN the system retrieves context to answer it
- THEN it MUST call the same `context-retrieval` pipeline used by
  generation, receiving verbatim raw document content, not a summary

### Requirement: Uncertainty and Variability Signaling

WHEN the retrieved context does not clearly settle the answer, or the
correct answer genuinely varies by Kawak module or configuration, the
system MUST state that uncertainty or variability explicitly in the answer
text rather than asserting one single confident answer as if it universally
applied.

#### Scenario: Answer plausibly varies by module or configuration

- GIVEN retrieved context shows different modules or configurations behave
  differently for the asked question
- WHEN the system composes the answer
- THEN it MUST state that the answer varies by module/configuration and
  MUST describe the known variants rather than pick one silently

#### Scenario: Retrieved context only partially supports the answer

- GIVEN retrieved context addresses part of the question but leaves part
  unclear or unconfirmed
- WHEN the system composes the answer
- THEN it MUST flag which part is uncertain rather than presenting the full
  answer as equally confident

### Requirement: Clarifying Question on Ambiguous Query

WHEN the analyst's question is ambiguous or under-specified such that
materially different reasonable interpretations would produce different
answers, the system MUST be able to return a single clarifying question to
the analyst instead of guessing which interpretation to answer.

#### Scenario: Ambiguous question triggers a clarifying question

- GIVEN an analyst's question could reasonably mean two materially
  different things given the retrieved context
- WHEN the system composes its response
- THEN it MUST return one clarifying question identifying the ambiguity
  instead of answering under an assumed interpretation

#### Scenario: Well-specified question is answered directly

- GIVEN an analyst's question is specific enough that retrieved context
  settles a single interpretation
- WHEN the system composes its response
- THEN it MUST answer directly and MUST NOT ask an unnecessary clarifying
  question

### Requirement: No-Information Degrade Stays Distinct From Uncertainty

The fixed `SIN_INFORMACION` notice ("No se encontró información sobre esto
en la documentación disponible.") MUST continue to apply only when
retrieval finds no relevant context at all, and MUST be returned with zero
network call, exactly as before this change. This is a distinct system
state from an uncertain-but-partially-grounded answer — the two states MUST
remain distinguishable in output and MUST NOT be collapsed into each other.

(Previously: `SIN_INFORMACION` was the only degrade state; there was no
distinct "uncertain/varies" state — this requirement clarifies the two
behaviors now coexist without changing the original degrade path.)

#### Scenario: No retrieved context at all

- GIVEN retrieval finds no relevant context for the question
- WHEN `responder_consulta` runs
- THEN the system MUST return the fixed `SIN_INFORMACION` notice and MUST
  NOT make a network call

#### Scenario: Retrieved context exists but is uncertain

- GIVEN retrieval finds relevant context but that context leaves the answer
  uncertain or varying
- WHEN `responder_consulta` runs
- THEN the system MUST make the network call and return an answer stating
  the uncertainty/variability, and MUST NOT return the fixed
  `SIN_INFORMACION` notice
