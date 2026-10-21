"""Idempotent seed script — default tenant, default admin, embedding model.

Run AFTER ``alembic upgrade head`` (from ``backend/``)::

    env/Scripts/python.exe scripts/seed.py

Safe to run repeatedly: every row is looked up by its natural/unique key and
skipped when present (B2 acceptance: re-running must not create duplicates).
Seeding is deliberately NOT part of the Alembic migration so ``alembic
downgrade`` can never wipe business data (B2 step 6).

The embedding model row is seeded from ``settings.openai`` (model name,
dimension, base_url) so the DB, the Qdrant collection (``init_qdrant.py``)
and the E1 embedder stay consistent with the configured environment.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.deps import DEFAULT_TENANT_ID, DEFAULT_USER_ID
from app.core.logging import setup_logging
from app.models import EmbeddingModel, Tenant, User
from sqlalchemy import select
from sqlalchemy.orm import Session

setup_logging(level=settings.app.log_level)

TENANT_NAME = "default"
ADMIN_USERNAME = "admin"
ADMIN_EMAIL = "admin@ragims.local"


def seed_tenant(session: Session) -> Tenant:
    """Return the preset default tenant, creating it only if missing."""
    tenant = session.get(Tenant, DEFAULT_TENANT_ID)
    if tenant is not None:
        print(f"= tenant exists: {tenant.id} ({tenant.name})")
        return tenant
    tenant = Tenant(id=DEFAULT_TENANT_ID, name=TENANT_NAME, status="active")
    session.add(tenant)
    session.flush()
    print(f"+ tenant created: {tenant.id} ({tenant.name})")
    return tenant


def seed_admin_user(session: Session, tenant_id: str) -> User:
    """Return the preset default admin, creating it only if missing."""
    user = session.scalars(
        select(User).where(User.tenant_id == tenant_id, User.username == ADMIN_USERNAME)
    ).one_or_none()
    if user is not None:
        print(f"= admin user exists: {user.id} ({user.username})")
        return user
    user = User(
        id=DEFAULT_USER_ID,
        tenant_id=tenant_id,
        username=ADMIN_USERNAME,
        email=ADMIN_EMAIL,
        role="admin",
        status="active",
    )
    session.add(user)
    session.flush()
    print(f"+ admin user created: {user.id} ({user.username})")
    return user


def seed_embedding_model(session: Session) -> EmbeddingModel:
    """Return the default embedding model row, creating it only if missing."""
    model_name = settings.openai.embedding_model
    model = session.scalars(
        select(EmbeddingModel).where(
            EmbeddingModel.provider == "openai",
            EmbeddingModel.model_name == model_name,
        )
    ).one_or_none()
    if model is not None:
        print(f"= embedding model exists: {model.model_name} (dim={model.dimension})")
        return model
    model = EmbeddingModel(
        name=model_name,
        provider="openai",
        model_name=model_name,
        dimension=settings.openai.embedding_dimension,
        config={
            "base_url": settings.openai.base_url,
            "batch_size": 64,
            "timeout_s": settings.openai.timeout,
            "max_retries": 3,
        },
        is_default=True,
    )
    session.add(model)
    session.flush()
    print(f"+ embedding model created: {model.model_name} (dim={model.dimension})")
    return model


def main() -> None:
    """Seed all preset rows in one transaction; commit only on full success."""
    session = SessionLocal()
    try:
        tenant = seed_tenant(session)
        seed_admin_user(session, tenant.id)
        seed_embedding_model(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    print("seed done (idempotent — safe to re-run)")


if __name__ == "__main__":
    main()
