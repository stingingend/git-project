# Phase 17: source-cited questions

Build the semantic index, choose **Ask repository**, and ask a question. The default returns source-backed findings: ranked definitions plus bounded approximate call-graph neighbors, exact source excerpts, and commit-pinned GitHub links. It identifies evidence to inspect; it does not pretend to generate an explanation when no language model is running.

`POST /repositories/{id}/questions` accepts `question` (2–1,000 characters) and `generate` (default false). Responses include the question, commit SHA, mode, answer, numbered citations with paths and line ranges, and approximate graph context. Source excerpts are bounded; truncation is explicit. Empty or weak retrieval yields an insufficient-evidence response.

Optional generation uses a configured chat-completions-compatible server. For example, with a separately installed local model server:

```powershell
$env:CODEATLAS_GENERATION_URL = 'http://127.0.0.1:11434/v1'
$env:CODEATLAS_GENERATION_MODEL = 'your-installed-model'
# For a hosted compatible server, use HTTPS and set CODEATLAS_GENERATION_KEY.
```

Restart the API after setting its environment, then select **Use the configured model server for an explanation**. This sends the question and retrieved source to that configured server. Generation stays disabled unless requested. No paid model or cloud account is provisioned automatically.

The model has no tools, receives source as untrusted evidence, and must cite supplied numeric labels. Redirects are refused, requests time out, and response size is bounded. Missing/unknown citation labels or invented URLs cause a fallback to source findings. Valid labels do not prove that every generated claim is correct; inspect the linked evidence. Repository code is never executed. The read transaction is released before model inference.

Tests cover real stored-source citations, generation opt-in, unavailable/invalid model fallback, request validation, and rejecting fabricated citation labels. Model-server configuration and a model download are intentionally separate from repository indexing.
