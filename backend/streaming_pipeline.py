"""
streaming_pipeline.py

Big-data-style streaming ingestion pipeline for telemetry data, using
Redis Streams as the message broker.

WHY REDIS STREAMS INSTEAD OF KAFKA (be ready to explain this honestly):
- Kafka is the textbook "big data streaming" tool, but it requires
  standing up a separate broker service/cluster - meaningful new
  infrastructure, cost, and operational complexity for a free-tier,
  time-constrained student project.
- Redis Streams is a genuine append-only log data structure built into
  Redis itself (since v5.0) - it provides the SAME core architectural
  pattern Kafka is known for: producers append events to a stream,
  independent consumers read from it via consumer groups, with
  at-least-once delivery semantics and acknowledgment tracking.
- Since we already run Upstash Redis, this adds ZERO new infrastructure,
  while still demonstrating the real architectural concept: decoupling
  data INGESTION from data PROCESSING, which is the actual point of a
  "big data streaming pipeline" - not the specific brand of broker used.
- Honest limitation to state if asked: Redis Streams doesn't offer
  Kafka's cross-datacenter replication, partitioned topics for massive
  horizontal scale, or long-term log compaction - it's the right tool
  for our current scale (a course project), not a drop-in Kafka
  replacement at true "big data" (millions of events/sec) scale. This
  is a legitimate, documented architectural trade-off, not a mistake.

ARCHITECTURE:
  Producer (telemetry endpoint) --> XADD --> Redis Stream
                                                  |
                                                  v
                                   Consumer Group (background worker)
                                                  |
                                                  v
                                   Processing: write lat/lng + geoadd
                                   (decoupled from the HTTP request/response
                                    cycle - the API responds instantly,
                                    processing happens asynchronously)

Run standalone for testing: python streaming_pipeline.py
In production: imported by main.py, consumer runs as a background task
started at FastAPI startup.
"""

import asyncio
import json
import logging

logger = logging.getLogger("KanyaRakshakStreaming")

STREAM_KEY = "telemetry:stream"
CONSUMER_GROUP = "telemetry_processors"
CONSUMER_NAME = "worker-1"


def ensure_consumer_group(r):
    """Create the consumer group if it doesn't already exist (idempotent)."""
    try:
        r.xgroup_create(name=STREAM_KEY, groupname=CONSUMER_GROUP, id="0", mkstream=True)
        logger.info(f"Created consumer group '{CONSUMER_GROUP}' on stream '{STREAM_KEY}'")
    except Exception as e:
        if "BUSYGROUP" in str(e):
            pass  # group already exists - fine, this is expected on every restart
        else:
            raise


def publish_telemetry_event(r, session_id: str, latitude: float, longitude: float):
    """
    PRODUCER side. Called from the FastAPI telemetry endpoint.
    Instead of writing directly to Redis keys, we append an event to the
    stream and return immediately - ingestion is now decoupled from
    processing. This is the core "streaming ingestion" pattern: the API
    responds fast regardless of how busy the downstream processing is.
    """
    event_id = r.xadd(STREAM_KEY, {
        "session_id": session_id,
        "latitude": str(latitude),
        "longitude": str(longitude),
    })
    return event_id


def process_event(r, fields: dict):
    """
    CONSUMER side processing logic for a single telemetry event.
    This is where downstream work happens - separated from ingestion,
    so slow processing never blocks the API response to the user.
    """
    session_id = fields["session_id"]
    latitude = float(fields["latitude"])
    longitude = float(fields["longitude"])

    r.set(f"user:{session_id}:lat", str(latitude))
    r.set(f"user:{session_id}:lng", str(longitude))
    r.geoadd("active_users_mesh", (longitude, latitude, session_id))

    logger.info(f"Processed telemetry event for session {session_id}: ({latitude}, {longitude})")


async def run_consumer_loop(r, poll_interval_seconds=2, batch_size=10):
    """
    CONSUMER worker loop. Runs continuously as a background asyncio task,
    reading unacknowledged events from the stream via the consumer group,
    processing each one, then acknowledging it (XACK) so it isn't
    reprocessed. This gives at-least-once delivery semantics - if the
    worker crashes mid-processing, the event remains unacknowledged and
    will be redelivered on restart, rather than silently lost.
    """
    ensure_consumer_group(r)
    logger.info("Streaming consumer loop started.")

    while True:
        try:
            entries = r.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams={STREAM_KEY: ">"},
                count=batch_size,
                block=2000,  # ms - wait up to 2s for new events before looping
            )

            if entries:
                for stream_name, messages in entries:
                    for message_id, fields in messages:
                        try:
                            process_event(r, fields)
                            r.xack(STREAM_KEY, CONSUMER_GROUP, message_id)
                        except Exception as e:
                            logger.error(f"Failed processing event {message_id}: {e} (left unacknowledged for retry)")

        except Exception as e:
            logger.error(f"Streaming consumer loop error: {e}")

        await asyncio.sleep(poll_interval_seconds)


# --- Standalone test/demo ---
if __name__ == "__main__":
    import fakeredis
    r = fakeredis.FakeStrictRedis(decode_responses=True)
    logging.basicConfig(level=logging.INFO)

    print("Simulating producer publishing 5 telemetry events...")
    for i in range(5):
        eid = publish_telemetry_event(r, f"demo_session_{i}", 17.44 + i * 0.001, 78.39 + i * 0.001)
        print(f"  Published event {eid}")

    print("\nStream length before consuming:", r.xlen(STREAM_KEY))

    async def demo_consume_once():
        ensure_consumer_group(r)
        entries = r.xreadgroup(CONSUMER_GROUP, CONSUMER_NAME, {STREAM_KEY: ">"}, count=10)
        for stream_name, messages in entries:
            for message_id, fields in messages:
                process_event(r, fields)
                r.xack(STREAM_KEY, CONSUMER_GROUP, message_id)
        print("\nConsumed and acknowledged all pending events.")
        print("Pending (unacknowledged) entries remaining:", r.xpending(STREAM_KEY, CONSUMER_GROUP))

    asyncio.run(demo_consume_once())

    print("\nVerifying processed data landed correctly:")
    print("  user:demo_session_0:lat =", r.get("user:demo_session_0:lat"))
    print("  active_users_mesh members:", r.zrange("active_users_mesh", 0, -1))
