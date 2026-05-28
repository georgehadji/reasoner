import asyncio
import json
import logging
import os
import argparse
import time

import asyncpg
from asyncpg.exceptions import PostgresError

from reasoner.security.encryption import get_encryption_service, EncryptionService
from reasoner.infrastructure.persistence.postgres_store import PostgreSQLEventStore, get_postgres_store
from reasoner.core.constants import DEFAULT_DB_COMMAND_TIMEOUT
from reasoner.core.events.domain_events import PipelineEventType, make_event
from reasoner.application.event_bus.bus import get_event_bus

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


async def _fetch_legacy_events(conn: asyncpg.Connection, batch_size: int, offset: int) -> list[asyncpg.Record]:
    """Fetches a batch of legacy events (not yet envelope encrypted)."""
    # Look for events where payload is NOT a JSON object with a '_e' key, or _blind_index is missing
    query = """
        SELECT id, event_id, aggregate_id, payload, event_type, version, timestamp
        FROM events
        WHERE NOT (payload ? '_e') OR NOT (payload ? '_blind_index')
        ORDER BY id ASC
        LIMIT $1 OFFSET $2
    """
    return await conn.fetch(query, batch_size, offset)


async def _fetch_legacy_snapshots(conn: asyncpg.Connection, batch_size: int, offset: int) -> list[asyncpg.Record]:
    """Fetches a batch of legacy snapshots (not yet envelope encrypted)."""
    query = """
        SELECT aggregate_id, version, state
        FROM snapshots
        WHERE NOT (state ? '_e')
        ORDER BY aggregate_id ASC
        LIMIT $1 OFFSET $2
    """
    return await conn.fetch(query, batch_size, offset)


async def migrate_events(store: PostgreSQLEventStore, encryption_service: EncryptionService, batch_size: int, delay_seconds: float) -> int:
    """Migrates legacy events to the new envelope encryption format with blind indexing."""
    migrated_count = 0
    offset = 0
    bus = get_event_bus() # Get event bus for logging errors

    while True:
        async with store._pool.acquire() as conn:
            events_batch = await _fetch_legacy_events(conn, batch_size, offset)
            if not events_batch: break

            logger.info(f"Processing {len(events_batch)} legacy events from offset {offset}...")

            for record in events_batch:
                event_id = record["event_id"]
                aggregate_id = record["aggregate_id"]
                event_type = record["event_type"]
                version = record["version"]
                current_payload = record["payload"]

                try:
                    # Case 1: Payload is a raw Fernet string (oldest format)
                    if isinstance(current_payload, str) and not current_payload.strip().startswith(("{", "[")):
                        decrypted_json = encryption_service.decrypt(current_payload)
                        raw_payload = json.loads(decrypted_json)
                        logger.debug(f"Event {event_id}: Decrypted raw Fernet string.")
                    # Case 2: Payload is JSON but missing _e or _blind_index
                    elif isinstance(current_payload, dict):
                        if "_e" in current_payload and "_blind_index" in current_payload:
                            logger.debug(f"Event {event_id}: Already migrated, skipping.")
                            continue # Already migrated
                        if "_e" in current_payload: # Encrypted but missing blind index
                            decrypted_json = encryption_service.decrypt(current_payload["_e"])
                            raw_payload = json.loads(decrypted_json)
                            logger.debug(f"Event {event_id}: Decrypted missing blind index.")
                        else: # Plaintext JSON or old non-envelope encrypted
                            raw_payload = current_payload # Assume it's the raw content
                            logger.debug(f"Event {event_id}: Processing plaintext or old JSON.")
                    else:
                        logger.warning(f"Event {event_id}: Unknown payload format, skipping. Payload: {current_payload}")
                        asyncio.create_task(bus.publish(make_event(
                            PipelineEventType.ERROR_OCCURRED, aggregate_id, version, 
                            message=f"Unknown event payload format for migration: {event_id}"
                        )))
                        continue

                    # Generate blind indexes from the textual content of the raw_payload
                    blind_indexes: list[str] = []
                    if isinstance(raw_payload, dict):
                        text_to_index = []
                        for key in ['problem', 'content', 'rationale', 'summary', 'message']:
                            if key in raw_payload and isinstance(raw_payload[key], str):
                                text_to_index.append(raw_payload[key])
                        if text_to_index:
                            blind_indexes = encryption_service.generate_blind_index(" ".join(text_to_index))

                    # Re-encrypt with new envelope structure
                    new_encrypted_payload = encryption_service.encrypt(json.dumps(raw_payload))
                    new_payload = {
                        "_e": new_encrypted_payload,
                        "_blind_index": blind_indexes
                    }

                    await conn.execute("""
                        UPDATE events
                        SET payload = $1
                        WHERE event_id = $2
                    """, json.dumps(new_payload), event_id)
                    migrated_count += 1

                except (PostgresError, json.JSONDecodeError) as e:
                    logger.error(f"Error migrating event {event_id} (aggregate {aggregate_id}): {e}")
                    asyncio.create_task(bus.publish(make_event(
                        PipelineEventType.ERROR_OCCURRED, aggregate_id, version, 
                        message=f"Error migrating event {event_id}: {e}",
                        details={
                            "event_id": str(event_id),
                            "error_type": e.__class__.__name__,
                            "payload_sample": str(current_payload)[:200]
                        }
                    )))
                except Exception as e:
                    logger.error(f"Unexpected error migrating event {event_id} (aggregate {aggregate_id}): {e}", exc_info=True)
                    asyncio.create_task(bus.publish(make_event(
                        PipelineEventType.ERROR_OCCURRED, aggregate_id, version, 
                        message=f"Unexpected error migrating event {event_id}: {e}",
                        details={
                            "event_id": str(event_id),
                            "error_type": e.__class__.__name__,
                            "payload_sample": str(current_payload)[:200]
                        }
                    )))
            
            offset += len(events_batch)
            if len(events_batch) < batch_size: break # End of events
            await asyncio.sleep(delay_seconds) # Throttle to prevent DB overload

    return migrated_count


async def migrate_snapshots(store: PostgreSQLEventStore, encryption_service: EncryptionService, batch_size: int, delay_seconds: float) -> int:
    """Migrates legacy snapshots to the new envelope encryption format."""
    migrated_count = 0
    offset = 0
    bus = get_event_bus()

    while True:
        async with store._pool.acquire() as conn:
            snapshots_batch = await _fetch_legacy_snapshots(conn, batch_size, offset)
            if not snapshots_batch: break

            logger.info(f"Processing {len(snapshots_batch)} legacy snapshots from offset {offset}...")

            for record in snapshots_batch:
                aggregate_id = record["aggregate_id"]
                version = record["version"]
                current_state = record["state"]

                try:
                    # If already envelope encrypted, skip
                    if isinstance(current_state, dict) and "_e" in current_state:
                        logger.debug(f"Snapshot {aggregate_id} (v{version}): Already migrated, skipping.")
                        continue

                    # Case 1: State is a raw Fernet string
                    if isinstance(current_state, str) and not current_state.strip().startswith(("{", "[")):
                        decrypted_json = encryption_service.decrypt(current_state)
                        raw_state = json.loads(decrypted_json)
                        logger.debug(f"Snapshot {aggregate_id} (v{version}): Decrypted raw Fernet string.")
                    # Case 2: State is plaintext JSON
                    elif isinstance(current_state, dict):
                        raw_state = current_state # Assume it's the raw content
                        logger.debug(f"Snapshot {aggregate_id} (v{version}): Processing plaintext JSON.")
                    else:
                        logger.warning(f"Snapshot {aggregate_id} (v{version}): Unknown state format, skipping. State: {current_state}")
                        asyncio.create_task(bus.publish(make_event(
                            PipelineEventType.ERROR_OCCURRED, aggregate_id, version, 
                            message=f"Unknown snapshot state format for migration: {aggregate_id}"
                        )))
                        continue

                    # Re-encrypt with new envelope structure
                    new_encrypted_state = encryption_service.encrypt(json.dumps(raw_state))
                    new_state = {"_e": new_encrypted_state}

                    await conn.execute("""
                        UPDATE snapshots
                        SET state = $1
                        WHERE aggregate_id = $2 AND version = $3
                    """, json.dumps(new_state), aggregate_id, version)
                    migrated_count += 1

                except (PostgresError, json.JSONDecodeError) as e:
                    logger.error(f"Error migrating snapshot {aggregate_id} (v{version}): {e}")
                    asyncio.create_task(bus.publish(make_event(
                        PipelineEventType.ERROR_OCCURRED, aggregate_id, version, 
                        message=f"Error migrating snapshot {aggregate_id} (v{version}): {e}",
                        details={
                            "aggregate_id": str(aggregate_id),
                            "error_type": e.__class__.__name__,
                            "state_sample": str(current_state)[:200]
                        }
                    )))
                except Exception as e:
                    logger.error(f"Unexpected error migrating snapshot {aggregate_id} (v{version}): {e}", exc_info=True)
                    asyncio.create_task(bus.publish(make_event(
                        PipelineEventType.ERROR_OCCURRED, aggregate_id, version, 
                        message=f"Unexpected error migrating snapshot {aggregate_id} (v{version}): {e}",
                        details={
                            "aggregate_id": str(aggregate_id),
                            "error_type": e.__class__.__name__,
                            "state_sample": str(current_state)[:200]
                        }
                    )))
            
            offset += len(snapshots_batch)
            if len(snapshots_batch) < batch_size: break # End of snapshots
            await asyncio.sleep(delay_seconds) # Throttle

    return migrated_count


async def main():
    parser = argparse.ArgumentParser(description="Migrate legacy encrypted events and snapshots to new envelope encryption format with blind indexing.")
    parser.add_argument("--batch-size", type=int, default=500, help="Number of records to process per batch.")
    parser.add_argument("--delay-seconds", type=float, default=0.1, help="Delay between batches to avoid overloading the database.")
    parser.add_argument("--connection-string", type=str, default=os.environ.get("DATABASE_URL"),
                        help="PostgreSQL connection string. Defaults to DATABASE_URL environment variable.")
    parser.add_argument("--encryption-key", type=str, default=os.environ.get("ENCRYPTION_KEY"),
                        help="Base64 encoded Fernet encryption key. Defaults to ENCRYPTION_KEY environment variable.")
    parser.add_argument("--blind-index-key", type=str, default=os.environ.get("BLIND_INDEX_KEY"),
                        help="Key for HMAC blind indexing. Defaults to BLIND_INDEX_KEY environment variable.")
    
    args = parser.parse_args()

    if not args.connection_string:
        logger.critical("DATABASE_URL environment variable or --connection-string argument is required.")
        return
    if not args.encryption_key:
        logger.critical("ENCRYPTION_KEY environment variable or --encryption-key argument is required.")
        return
    if not args.blind_index_key:
        logger.critical("BLIND_INDEX_KEY environment variable or --blind-index-key argument is required for blind indexing.")
        return

    # Set environment variables for services to pick up
    os.environ["ENCRYPTION_KEY"] = args.encryption_key
    os.environ["BLIND_INDEX_KEY"] = args.blind_index_key
    os.environ["DATABASE_URL"] = args.connection_string

    # Initialize services
    event_bus = get_event_bus()
    await event_bus.start()

    encryption_service = get_encryption_service(
        encryption_key=args.encryption_key,
        blind_index_key=args.blind_index_key
    )
    # Directly initialize PostgreSQLEventStore with the given connection string
    store = PostgreSQLEventStore(connection_string=args.connection_string)
    await store.initialize() # This will also run schema init

    logger.info("Starting legacy data migration...")

    events_migrated = await migrate_events(store, encryption_service, args.batch_size, args.delay_seconds)
    logger.info(f"Completed event migration. Total events migrated: {events_migrated}")

    snapshots_migrated = await migrate_snapshots(store, encryption_service, args.batch_size, args.delay_seconds)
    logger.info(f"Completed snapshot migration. Total snapshots migrated: {snapshots_migrated}")

    await store.close()
    await event_bus.stop()
    logger.info("Migration script finished.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Migration interrupted by user.")
    except Exception as e:
        logger.critical(f"Migration failed: {e}", exc_info=True)
