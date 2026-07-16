"""Real NATS/JetStream event-flow integration tests."""

import asyncio
import json
import uuid

import nats
import pytest
import pytest_asyncio
from nats.js.api import AckPolicy, ConsumerConfig


def _docker_available() -> bool:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _docker_available(), reason="Docker is required for NATS integration tests"
)


@pytest_asyncio.fixture
async def nats_connection(nats_url):
    connection = await nats.connect(nats_url)
    try:
        yield connection
    finally:
        await connection.drain()


@pytest.mark.asyncio
async def test_pod_running_event_is_delivered_to_billing_consumer(nats_connection):
    received = asyncio.Event()
    payload = {}

    async def handler(message):
        payload.update(json.loads(message.data))
        received.set()

    subscription = await nats_connection.subscribe("gpu.pod.running", cb=handler)
    await nats_connection.publish(
        "gpu.pod.running",
        json.dumps({"pod_id": "pod-1", "user_id": "student-1"}).encode(),
    )
    await nats_connection.flush()

    await asyncio.wait_for(received.wait(), timeout=2)
    assert payload == {"pod_id": "pod-1", "user_id": "student-1"}
    await subscription.unsubscribe()


@pytest.mark.asyncio
async def test_pod_terminated_event_is_delivered_to_billing_consumer(nats_connection):
    subscription = await nats_connection.subscribe("gpu.pod.terminated")
    await nats_connection.publish(
        "gpu.pod.terminated", json.dumps({"pod_id": "pod-1"}).encode()
    )
    await nats_connection.flush()

    message = await subscription.next_msg(timeout=2)
    assert json.loads(message.data) == {"pod_id": "pod-1"}


@pytest.mark.asyncio
async def test_low_balance_alert_payload_survives_event_bus(nats_connection):
    subscription = await nats_connection.subscribe("billing.alert.low")
    alert = {"user_id": "student-1", "balance": 9.5, "threshold": 10}
    await nats_connection.publish("billing.alert.low", json.dumps(alert).encode())
    await nats_connection.flush()

    message = await subscription.next_msg(timeout=2)
    assert json.loads(message.data) == alert


@pytest.mark.asyncio
async def test_jetstream_redelivers_nacked_event(nats_connection):
    js = nats_connection.jetstream()
    suffix = uuid.uuid4().hex[:10]
    subject = f"billing.test.{suffix}"
    stream = f"BILLING_{suffix.upper()}"
    durable = f"worker-{suffix}"
    await js.add_stream(name=stream, subjects=[subject])
    subscription = await js.pull_subscribe(
        subject,
        durable=durable,
        config=ConsumerConfig(
            durable_name=durable,
            ack_policy=AckPolicy.EXPLICIT,
            ack_wait=0.2,
            max_deliver=3,
        ),
    )
    await js.publish(subject, b'{"tx_id":"tick-1"}')

    first = (await subscription.fetch(1, timeout=2))[0]
    await first.nak()
    second = (await subscription.fetch(1, timeout=2))[0]
    assert second.data == first.data
    assert second.metadata.num_delivered == 2
    await second.ack()
    await js.delete_stream(stream)


@pytest.mark.xfail(
    strict=True,
    reason="application dead-letter stream and routing policy are not implemented",
)
@pytest.mark.asyncio
async def test_failed_event_routes_to_dead_letter_stream(nats_connection):
    js = nats_connection.jetstream()
    info = await js.stream_info("BILLING_DLQ")
    assert "billing.dead_letter" in info.config.subjects
