# OraVision AWR Pro: High-Level Architecture

## Runtime Shape

`start.bat` launches a localhost-only FastAPI application. The active UI is
`backend/templates/index.html`; the React and Streamlit surfaces are prototypes
until a deliberate migration is completed.

```text
AWR HTML upload
  -> bounded upload stream
  -> HTML parser
  -> normalized AWRData + evidence-availability metadata
  -> deterministic PE analyzers
       - health scorer
       - comparison engine
       - RCA engine
       - recommendations
       - intelligence pipeline
  -> FastAPI response
  -> OraVision dashboard
```

## Trust Invariants

1. Missing evidence is represented as unavailable, never as a measured zero.
2. Demo data is returned only when the caller explicitly requests demo mode.
3. SQL discovery unions elapsed, CPU, gets, reads, and executions sections.
4. New SQL triage considers total normalized elapsed impact and execution volume.
5. Full SQL text is mapped by SQL ID using table structure with a legacy anchor fallback.
6. Learned HTML is sanitized when stored and again when rendered.
7. LLM output and PDF-derived narrative snippets are sanitized or escaped before rendering.

## Deployment Modes

### Local PE Workstation

`start.bat` binds Uvicorn to `127.0.0.1`. No API key is required. Uploads are
kept in process memory for four hours and capped by `ORAVISION_MAX_UPLOADS`.

### Hosted Internal Service

Set `ORAVISION_API_KEY` and place the service behind TLS. Clients must provide
either `X-API-Key` or `Authorization: Bearer <key>`.

The API-key mode is a guardrail, not a complete multi-user platform. Before a
customer-facing deployment, replace process-local upload storage with a
tenant-scoped repository and add identity-based authorization and audit logs.

## Next Structural Phase

The served HTML template is still a large monolith. The next architecture step
is to choose the React UI as the production surface, expose typed API clients,
move dashboard panels into tested components, bundle CSS locally, and archive
the legacy Streamlit and inline-template prototypes after parity validation.
