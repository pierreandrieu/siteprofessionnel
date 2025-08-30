import json
from pathlib import Path
import time
import os

import pytest
from django.test import Client
from django.conf import settings


@pytest.fixture(autouse=True)
def _force_celery_eager(settings):
    # Celery 5 names
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    settings.CELERY_TASK_STORE_EAGER_RESULT = True

    # In-memory broker & result backend for tests
    settings.CELERY_BROKER_URL = "memory://"
    settings.CELERY_RESULT_BACKEND = "cache+memory://"


def _post_start(client: Client, payload: dict) -> str:
    r = client.post("/plandeclasse/solve/start", data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 200, r.content
    task_id = r.json()["task_id"]
    assert isinstance(task_id, str)
    return task_id


def _get_status(client: Client, task_id: str) -> dict:
    r = client.get(f"/plandeclasse/solve/status/{task_id}")
    assert r.status_code == 200
    return r.json()


def test_min_payload_end_to_end(db):
    client = Client()
    payload = json.loads((Path(__file__).parent / "data" / "payload_min.json").read_text(encoding="utf-8"))
    task_id = _post_start(client, payload)
    data = _get_status(client, task_id)
    assert data.get("status") == "SUCCESS", data
    assignment = data.get("assignment") or {}
    assert assignment, "affectation vide"
    # chaque clé 'x,y,s' pointe vers un id d'étudiant présent
    ids = {s["id"] for s in payload["students"]}
    assert set(assignment.values()).issubset(ids)


def test_mix_payload_end_to_end(db):
    client = Client()
    payload = json.loads((Path(__file__).parent / "data" / "payload_mix.json").read_text(encoding="utf-8"))
    task_id = _post_start(client, payload)
    data = _get_status(client, task_id)
    assert data.get("status") == "SUCCESS", data
    assignment = data.get("assignment") or {}
    assert assignment
    # un siège est interdit dans payload -> ne doit pas apparaître
    assert "0,1,2" not in assignment
