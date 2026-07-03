#!/usr/bin/env python
"""
Migration Script: SQLite to PostgreSQL Event Store

This script performs a one-shot migration of all data (events, aggregates, snapshots)
from the local SQLite `events.db` to the new PostgreSQL event store.
It reads the DATABASE_URL from the environment or `.env` file.

Usage:
    python scripts/migrate_events_sqlite_to_pg.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src directory to python path
REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT / "src"))

from reasoner.infrastructure.persistence.event_store import EventStore
from reasoner.infrastructure.persistence.postgres_store import PostgreSQLEventStore
from reasoner.core.settings import settings

async def migrate() -> None:
    if not settings.DATABASE_URL:
        print("ERROR: DATABASE_URL is not set in environment or .env file.")
        sys.exit(1)

    print("Initializing PostgreSQL Event Store...")
    pg_store = PostgreSQLEventStore(settings.DATABASE_URL)
    await pg_store.initialize()

    print("Connecting to SQLite Event Store...")
    sqlite_db_path = REPO_ROOT / "events.db"
    if not sqlite_db_path.exists():
        print(f"ERROR: SQLite database not found at {sqlite_db_path}")
        sys.exit(1)
        
    sqlite_store = EventStore(sqlite_db_path)

    # Note: For a robust migration we ideally bypass the DomainEvent abstractions 
    # and do a direct row-for-row copy between the tables using asyncpg for speed.
    
    print("Fetching SQLite data...")
    conn = sqlite_store._get_connection()
    
    # 1. Migrate Events
    cursor = conn.execute("SELECT * FROM events ORDER BY id ASC")
    events = cursor.fetchall()
    print(f"Found {len(events)} events to migrate.")
    
    if events:
        async with pg_store.pool.acquire() as pg_conn:
            await pg_conn.executemany(
                """
                INSERT INTO events 
                (event_id, event_type, aggregate_id, aggregate_type, version, timestamp, payload, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (event_id) DO NOTHING
                """,
                [(
                    r["event_id"], r["event_type"], r["aggregate_id"], r["aggregate_type"], 
                    r["version"], r["timestamp"], r["payload"], r["created_at"]
                ) for r in events]
            )
        print("Events migrated successfully.")

    # 2. Migrate Aggregates
    cursor = conn.execute("SELECT * FROM aggregates")
    aggregates = cursor.fetchall()
    print(f"Found {len(aggregates)} aggregates to migrate.")
    
    if aggregates:
        async with pg_store.pool.acquire() as pg_conn:
            await pg_conn.executemany(
                """
                INSERT INTO aggregates 
                (aggregate_id, aggregate_type, current_version, status, problem, preset, method, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (aggregate_id) DO NOTHING
                """,
                [(
                    r["aggregate_id"], r["aggregate_type"], r["current_version"], r["status"], 
                    r["problem"], r["preset"], r["method"], r["created_at"], r["updated_at"]
                ) for r in aggregates]
            )
        print("Aggregates migrated successfully.")

    # 3. Migrate Snapshots
    cursor = conn.execute("SELECT * FROM snapshots")
    snapshots = cursor.fetchall()
    print(f"Found {len(snapshots)} snapshots to migrate.")
    
    if snapshots:
        async with pg_store.pool.acquire() as pg_conn:
            await pg_conn.executemany(
                """
                INSERT INTO snapshots 
                (aggregate_id, version, state, created_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (aggregate_id) DO NOTHING
                """,
                [(
                    r["aggregate_id"], r["version"], r["state"], r["created_at"]
                ) for r in snapshots]
            )
        print("Snapshots migrated successfully.")

    print("\nMigration completed successfully.")
    
    # Close connections
    sqlite_store.close()
    await pg_store.close()

if __name__ == "__main__":
    # Windows-specific fix for asyncio with ProactorEventLoop
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(migrate())