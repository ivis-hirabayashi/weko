# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2017-2022 CERN.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Pytest configuration."""

from unittest.mock import patch

import pytest
from flask import Flask
from flask_babel import Babel
from kombu import Exchange, Connection, Queue
from invenio_stats import InvenioStats
from invenio_queues import InvenioQueues

MOCK_MQ_EXCHANGE = Exchange(
    "test_events",
    type="direct",
    delivery_mode="transient",  # in-memory queue
    durable=True,
)


def remove_queues(app):
    """Delete all queues declared on the current app."""
    with app.app_context():
        ext = app.extensions["invenio-queues"]
        for name, queue in ext.queues.items():
            if queue.exists:
                queue.queue.delete()


def mock_iter_entry_points_factory(data):
    """Create a mock iter_entry_points function."""
    from pkg_resources import iter_entry_points

    def entrypoints(group, name=None):
        if group == "invenio_queues.queues":
            for entrypoint in data:
                yield entrypoint
        else:
            for x in iter_entry_points(group=group, name=name):
                yield x

    return entrypoints


@pytest.yield_fixture()
def test_queues_entrypoints(app):
    """Declare some queues by mocking the invenio_queues.queues entrypoint.

    It yields a list like [{name: queue_name, exchange: conf}, ...].
    """
    from pkg_resources import EntryPoint

    data = []
    result = []
    for idx in range(5):
        queue_name = "queue{}".format(idx)
        entrypoint = EntryPoint(queue_name, queue_name)
        conf = dict(name=queue_name, exchange=MOCK_MQ_EXCHANGE)
        entrypoint.load = lambda conf=conf: (lambda: [conf])
        data.append(entrypoint)
        result.append(conf)

    entrypoints = mock_iter_entry_points_factory(data)

    with patch("pkg_resources.iter_entry_points", entrypoints):
        try:
            yield result
        finally:
            remove_queues(app)


@pytest.yield_fixture()
def test_queues(app, test_queues_entrypoints):
    """Declare test queues."""
    with app.app_context():
        ext = app.extensions["invenio-queues"]
        for conf in test_queues_entrypoints:
            queue = ext.queues[conf["name"]]
            queue.queue.declare()
            assert queue.exists
    yield test_queues_entrypoints


@pytest.fixture()
def app():
    """Flask application fixture."""

    app_ = Flask("testapp")
    app_.config.update(
        SECRET_KEY="SECRET_KEY",
        TESTING=True,
        BROKER_URL="amqp://guest:guest@rabbitmq:5672//",
        CELERY_BROKER_URL="amqp://guest:guest@rabbitmq:5672//",
        BABEL_DEFAULT_LOCALE='en',
        CACHE_REDIS_URL='redis://redis:6379/0',
        CACHE_REDIS_DB='0',
        CACHE_REDIS_HOST="redis",
    )
    InvenioQueues(app_)
    Babel(app_)
    InvenioStats(app_)
    return app_

@pytest.fixture()
def set_redis_host(app):
    """Set Redis host to 'redis'."""
    original_queues_broker_url = app.config.get("QUEUES_BROKER_URL")

    # Update the Redis host in the configuration
    if original_queues_broker_url and "redis://" in original_queues_broker_url:
        app.config["QUEUES_BROKER_URL"] = original_queues_broker_url.replace("localhost", "redis")

    yield

    # Restore the original configuration
    app.config["QUEUES_BROKER_URL"] = original_queues_broker_url

@pytest.fixture(scope="session")
def check_redis_connection():
    """Check Redis connection."""
    try:
        conn = Connection("redis://redis:6379/")
        conn.connect()
        assert conn.connected, "Failed to connect to Redis at redis://redis:6379/"
        print("Redis connection successful.")
    except Exception as e:
        pytest.fail(f"Redis connection failed: {e}")
