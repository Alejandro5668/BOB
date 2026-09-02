# Delta for Jira Description Generation

## MODIFIED Requirements

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

## ADDED Requirements

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
