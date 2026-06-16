# Recruiting Ontology Backend

Phase 1 foundation for a deterministic, governance-controlled recruiting ontology and normalization platform.

This backend is intentionally:

- relational-first
- deterministic-first
- explainability-first
- governance-controlled

It intentionally does not include embeddings, vector databases, autonomous ontology mutation, or AI ranking.

## Local Development

```powershell
cd backend
uvicorn app.main:app --reload
```

Set `DATABASE_URL` to a PostgreSQL DSN before running migrations.

```powershell
alembic upgrade head
```
