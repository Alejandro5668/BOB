# Audio Transcription Specification

## Purpose

Enables an analyst to capture or upload spoken audio describing a client issue and receive a locally-generated, editable Spanish transcript — including recordings that run several minutes, without blocking the UI.

## ADDED Requirements

### Requirement: Audio Capture

The system MUST allow the analyst to provide audio via microphone recording or file upload on a single Streamlit screen.

#### Scenario: Analyst records audio via microphone

- GIVEN the analyst is on the main screen
- WHEN they record audio using the browser microphone control
- THEN the system MUST accept the recorded audio for transcription

#### Scenario: Analyst uploads an audio file

- GIVEN the analyst has a pre-recorded audio file
- WHEN they upload it through the file input
- THEN the system MUST accept the uploaded file for transcription

#### Scenario: Recording control unavailable

- GIVEN the installed Streamlit version does not support live audio recording
- WHEN the analyst opens the screen
- THEN the system MUST still offer the file upload path as a fallback

### Requirement: Local CPU Transcription

The system MUST transcribe audio locally using `faster-whisper` model `base`, without sending raw audio to any external service.

#### Scenario: Audio transcribed locally

- GIVEN a valid audio input
- WHEN transcription runs
- THEN the system MUST produce a Spanish-language transcript sourced only from local processing

#### Scenario: Missing decode dependency

- GIVEN ffmpeg or the `av` package is not available in the environment
- WHEN transcription is attempted
- THEN the system MUST show an explicit setup error message and MUST NOT crash with a raw stack trace

### Requirement: Long-Audio Progress Visibility

The system MUST support audio recordings lasting several minutes and MUST show visible transcription progress without freezing the UI while processing runs.

#### Scenario: Multi-minute recording transcribed

- GIVEN an audio input lasting several minutes
- WHEN the analyst starts transcription
- THEN the system MUST display a progress indicator (e.g., spinner or status) for the duration of processing
- AND the UI MUST remain responsive, not frozen, until transcription completes

#### Scenario: Transcription in progress, analyst waits

- GIVEN transcription of a multi-minute recording is running
- WHEN the analyst checks the screen
- THEN the system MUST communicate that work is ongoing rather than appearing stalled or errored

### Requirement: Editable Transcript Output

The transcript produced by transcription MUST be presented in an editable text box before any further action is taken.

#### Scenario: Analyst corrects a mis-transcribed term

- GIVEN the transcript contains a misrecognized term (e.g., internal jargon)
- WHEN the analyst edits the text box
- THEN the system MUST retain the edited text as the transcript for subsequent steps

### Requirement: Temporary Audio Cleanup

The system MUST delete any temporary audio file it creates after transcription completes, whether it succeeds or fails.

#### Scenario: Temp file removed after successful transcription

- GIVEN a temporary audio file was created for processing
- WHEN transcription finishes successfully
- THEN the system MUST delete the temporary file

#### Scenario: Temp file removed after failed transcription

- GIVEN a temporary audio file was created for processing
- WHEN transcription fails with an error
- THEN the system MUST still delete the temporary file

### Requirement: Module Testability

The transcription logic MUST be callable and testable as a standalone module without a running Streamlit session.

#### Scenario: Unit test invokes transcription directly

- GIVEN a test imports the transcription module
- WHEN it calls the transcription function with a sample audio path
- THEN the system MUST execute without requiring a Streamlit runtime
