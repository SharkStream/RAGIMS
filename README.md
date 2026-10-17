# RAGIMS

RAGIMS is a document-ingestion platform scaffold for processing documents into
searchable indexes. The repository is organized into a FastAPI/Temporal backend,
a React frontend, deployment configuration, documentation, and operational
scripts.

## Repository layout

- `backend/` - API, Temporal worker, ingestion pipeline, and tests.
- `frontend/` - React application and UI components.
- `deploy/` - Local dependencies, Kubernetes, Argo CD, and monitoring.
- `docs/` - Product, architecture, API, and operations documentation.
- `scripts/` - Initialization, migration, reconciliation, and backup scripts.
- `.github/workflows/` - CI/CD workflows.

The backend and frontend modules are scaffolding and are not yet a complete
production implementation. See [plan.md](./plan.md) for the project plan.
