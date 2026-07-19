#!/bin/bash
# =============================================================================
# RIP Phase 2 — Kafka Topic Setup
# Run this ONCE after `docker compose up` to create all canonical topics.
# Each topic maps to a pipeline stage. Never skip or rename these.
# =============================================================================

KAFKA_CONTAINER="rip_kafka"
BOOTSTRAP="kafka:29092"

echo "Waiting for Kafka to be ready..."
sleep 10

run() {
  docker exec $KAFKA_CONTAINER kafka-topics --bootstrap-server $BOOTSTRAP "$@"
}

echo ""
echo "Creating RIP Kafka topics..."
echo "================================================"

# P2 — Ingestion
run --create --if-not-exists --topic reputation.raw.ingested \
    --partitions 6 --replication-factor 1 \
    --config retention.ms=604800000   # 7 days

# P3 — Normalization pipeline
run --create --if-not-exists --topic reputation.normalized \
    --partitions 6 --replication-factor 1

run --create --if-not-exists --topic reputation.deduplicated \
    --partitions 6 --replication-factor 1

run --create --if-not-exists --topic reputation.entity.resolved \
    --partitions 6 --replication-factor 1

# P4 — AI classification
run --create --if-not-exists --topic reputation.ai.classified \
    --partitions 6 --replication-factor 1

# P5 — Output layer
run --create --if-not-exists --topic reputation.scored \
    --partitions 3 --replication-factor 1

run --create --if-not-exists --topic reputation.alert.created \
    --partitions 3 --replication-factor 1

run --create --if-not-exists --topic reputation.alert.dispatched \
    --partitions 3 --replication-factor 1

# Dead-letter queue — malformed or unprocessable messages land here
run --create --if-not-exists --topic reputation.dlq \
    --partitions 3 --replication-factor 1 \
    --config retention.ms=2592000000  # 30 days

echo ""
echo "All topics created. Listing:"
run --list
echo "================================================"
echo "Done. Open Kafka UI at http://localhost:8080 to verify."
