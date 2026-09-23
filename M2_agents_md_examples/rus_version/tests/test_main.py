"""Tests for the cars REST API."""

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main as app_module

INITIAL_CARS = [
    {
        "id": 1,
        "make": "Ford",
        "model": "Mustang",
        "year": 1969,
        "horsepower": 290,
        "engine_cc": 5752,
        "transmission": "Manual",
    }
]


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Return a TestClient isolated from the real data file.

    Args:
        tmp_path: Temporary directory for the data file.
        monkeypatch: Fixture used to redirect the data file.

    Returns:
        A TestClient bound to an isolated in-memory car collection.
    """
    data_file = tmp_path / "cars.json"
    data_file.write_text(json.dumps(INITIAL_CARS))
    monkeypatch.setattr(app_module, "CARS_FILE", data_file)
    app_module.cars = app_module._load_cars()
    with TestClient(app_module.app) as test_client:
        yield test_client


def test_list_cars(client: TestClient) -> None:
    """List all cars and verify every record contains all fields."""
    response = client.get("/cars")
    assert response.status_code == 200
    assert response.json() == INITIAL_CARS


def test_get_car(client: TestClient) -> None:
    """Fetch a single car by its id."""
    response = client.get("/cars/1")
    assert response.status_code == 200
    assert response.json()["make"] == "Ford"


def test_get_car_not_found(client: TestClient) -> None:
    """Requesting a missing car returns 404."""
    assert client.get("/cars/999").status_code == 404


def test_create_car(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Create a car and verify id assignment plus persistence."""
    payload = {
        "make": "Tesla",
        "model": "Model S",
        "year": 2022,
        "horsepower": 670,
        "engine_cc": 0,
        "transmission": "Automatic",
    }
    response = client.post("/cars", json=payload)
    assert response.status_code == 201
    created = response.json()
    assert created["id"] == 2
    assert created["engine_cc"] == 0
    assert client.get("/cars/2").json() == created

    stored = json.loads(app_module.CARS_FILE.read_text())
    assert any(car["id"] == 2 for car in stored)


def test_create_car_rejects_negative_engine_cc(client: TestClient) -> None:
    """An invalid payload with negative engine_cc returns 422."""
    payload = {
        "make": "Tesla",
        "model": "Model S",
        "year": 2022,
        "horsepower": 670,
        "engine_cc": -1,
        "transmission": "Automatic",
    }
    assert client.post("/cars", json=payload).status_code == 422


def test_delete_car(client: TestClient) -> None:
    """Delete a car by id and verify it is removed and persisted."""
    deleted = client.delete("/cars/1")
    assert deleted.status_code == 200
    assert deleted.json()["id"] == 1
    assert client.get("/cars/1").status_code == 404
    assert client.delete("/cars/1").status_code == 404

    stored = json.loads(app_module.CARS_FILE.read_text())
    assert stored == []
