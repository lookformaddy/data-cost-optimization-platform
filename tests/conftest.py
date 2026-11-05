"""Shared fixtures for dcop tests."""

from __future__ import annotations

import datetime as _dt

import pytest

from dcop.models import Budget
from dcop.synthetic import (
    generate_clusters,
    generate_jobs,
    generate_records,
    generate_tables,
    generate_views,
)


@pytest.fixture()
def records():
    return generate_records(seed=42)


@pytest.fixture()
def tables():
    return generate_tables(seed=42)


@pytest.fixture()
def clusters():
    return generate_clusters(seed=42)


@pytest.fixture()
def jobs():
    return generate_jobs(seed=42)


@pytest.fixture()
def views():
    return generate_views(seed=42)


@pytest.fixture()
def budgets():
    return [
        Budget("analytics", 2500.0),
        Budget("growth", 1500.0),
        Budget("risk", 1200.0),
        Budget("platform", 2000.0),
        Budget("marketing", 800.0),
    ]


@pytest.fixture()
def on_date():
    return _dt.date(2026, 11, 4)
