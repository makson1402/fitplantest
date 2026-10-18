"""B-28: property-based testing of the running API against the frozen contract (schemathesis).

For every implemented operation schemathesis generates many requests from docs/api/openapi.yaml (valid and invalid
ones) and checks that the server never answers with a 5xx, that every answer has the content type and the body
schema the contract promises, and that the contract's own examples work. The fixed seed keeps CI deterministic.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import schemathesis
import yaml
from hypothesis import HealthCheck, Phase, settings
from schemathesis.checks import content_type_conformance, not_a_server_error, response_schema_conformance

CONTRACT = Path(__file__).resolve().parents[3] / "docs" / "api" / "openapi.yaml"
PENDING = Path(__file__).with_name("pending_operations.txt")

pytestmark = pytest.mark.skipif(not CONTRACT.exists(), reason="docs/ is not part of this checkout")


def _pending() -> list[str]:
    return [ln.strip() for ln in PENDING.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]


def _load():
    raw = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    schema = schemathesis.openapi.from_dict(raw)
    # operations the backend does not implement yet answer 404 by design; they are covered by the pending list
    return schema.exclude(operation_id=_pending()).exclude(path="/users/me/delete")  # that one ends the session


schema = _load()


EXAMPLES = int(os.environ.get("SCHEMATHESIS_EXAMPLES", "12"))  # CI keeps it short; raise it for a deep local run


@schema.parametrize()
@settings(max_examples=EXAMPLES, deadline=None, derandomize=EXAMPLES == 12, database=None,
          phases=[Phase.explicit, Phase.generate],
          suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much, HealthCheck.data_too_large])
def test_the_running_api_follows_the_contract(case, live_api, auth_header):
    case.call_and_validate(base_url=live_api, headers=auth_header,
                           checks=[not_a_server_error, response_schema_conformance, content_type_conformance])
