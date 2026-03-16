#!/usr/bin/env python3
"""Print decrypted OpenAI API keys for all tenants.

Requires APP_ENCRYPTION_KEY and database access. Run from backend with:
  cd backend && python scripts/show_openai_keys.py

Or: python -m scripts.show_openai_keys (from backend dir, with . in PYTHONPATH)
"""
import sys
from pathlib import Path

# Allow importing app when run as script
backend = Path(__file__).resolve().parent.parent
if str(backend) not in sys.path:
    sys.path.insert(0, str(backend))

from sqlalchemy import select

from app.database import SessionLocal
from app.encryption import decrypt
from app.models.llm_key import LlmKey
from app.models.tenant import Tenant


def main() -> None:
    db = SessionLocal()
    try:
        stmt = (
            select(LlmKey, Tenant)
            .join(Tenant, Tenant.id == LlmKey.tenant_id)
            .where(LlmKey.provider == "openai")
            .order_by(Tenant.name)
        )
        rows = db.execute(stmt).all()
        if not rows:
            print("No OpenAI keys found in llm_keys.")
            return
        for llm_key, tenant in rows:
            try:
                api_key = decrypt(llm_key.encrypted_key)
            except Exception as e:
                print(f"Tenant: {tenant.name} (id={tenant.id})")
                print(f"  Error decrypting: {e}")
                print()
                continue
            print(f"Tenant: {tenant.name} (id={tenant.id})")
            print(f"  OpenAI API key: {api_key}")
            print()
    finally:
        db.close()


if __name__ == "__main__":
    main()
