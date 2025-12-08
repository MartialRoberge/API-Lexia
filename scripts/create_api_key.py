#!/usr/bin/env python3
"""
Script pour créer une nouvelle clé API.

Usage:
    python scripts/create_api_key.py
    python scripts/create_api_key.py --name "Mon App"
"""

import argparse
import asyncio
import hashlib
import os
import secrets
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key and its hash."""
    # Get salt from environment or use default
    salt = os.environ.get("API_KEY_SALT", "your-salt-16-chars")

    # Generate random key
    random_part = secrets.token_hex(20)
    api_key = f"lx_{random_part}"

    # Hash the key (without prefix)
    key_body = api_key[3:]
    key_hash = hashlib.sha256((salt + key_body).encode()).hexdigest()

    return api_key, key_hash


async def insert_key_to_db(key_hash: str, name: str, user_id: str) -> str:
    """Insert the API key hash into the database."""
    from sqlalchemy import text
    from src.db.session import async_session_maker, init_db

    await init_db()

    async with async_session_maker() as session:
        result = await session.execute(
            text("""
                INSERT INTO api_keys (id, key_hash, name, user_id, permissions, rate_limit, is_revoked, created_at, updated_at)
                VALUES (gen_random_uuid(), :key_hash, :name, :user_id, '["*"]', 60, false, now(), now())
                RETURNING id
            """),
            {"key_hash": key_hash, "name": name, "user_id": user_id}
        )
        key_id = result.scalar()
        await session.commit()
        return str(key_id)


def main():
    parser = argparse.ArgumentParser(description="Create a new API key")
    parser.add_argument("--name", default="API Key", help="Name for the API key")
    parser.add_argument("--user-id", default="user-1", help="User ID")
    parser.add_argument("--no-db", action="store_true", help="Only generate key, don't insert in DB")
    args = parser.parse_args()

    # Generate key
    api_key, key_hash = generate_api_key()

    print("=" * 70)
    print("  NOUVELLE CLÉ API GÉNÉRÉE")
    print("=" * 70)
    print()
    print(f"  Clé API:  {api_key}")
    print()
    print("  ⚠️  COPIE CETTE CLÉ MAINTENANT ! Elle ne sera plus affichée.")
    print()
    print("=" * 70)

    if args.no_db:
        print()
        print(f"Hash (pour insertion manuelle): {key_hash}")
        print()
        print("Commande SQL pour insérer:")
        print(f"""
su - postgres -c "psql -d lexia -c \\"INSERT INTO api_keys (id, key_hash, name, user_id, permissions, rate_limit, is_revoked, created_at, updated_at) VALUES (gen_random_uuid(), '{key_hash}', '{args.name}', '{args.user_id}', '[\\\\\\\"*\\\\\\\"]', 60, false, now(), now());\\""
""")
    else:
        # Insert into database
        try:
            key_id = asyncio.run(insert_key_to_db(key_hash, args.name, args.user_id))
            print()
            print(f"  ✓ Clé insérée dans la base de données")
            print(f"  ID: {key_id}")
            print()
        except Exception as e:
            print()
            print(f"  ✗ Erreur lors de l'insertion: {e}")
            print()
            print(f"  Hash (pour insertion manuelle): {key_hash}")
            print()


if __name__ == "__main__":
    main()
