from fastapi.testclient import TestClient

from main import app, cars

client = TestClient(app)


def test_list_cars():
    response = client.get("/cars")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        car = data[0]
        for key in [
            "id",
            "make",
            "model",
            "year",
            "horsepower",
            "engine_cc",
            "transmission",
        ]:
            assert key in car


def test_get_car():
    if not cars:
        return
    car_id = cars[0]["id"]
    response = client.get(f"/cars/{car_id}")
    assert response.status_code == 200
    for key in [
        "id",
        "make",
        "model",
        "year",
        "horsepower",
        "engine_cc",
        "transmission",
    ]:
        assert key in response.json()


def test_get_car_not_found():
    response = client.get("/cars/999999")
    assert response.status_code == 404


CAR_FIELDS = [
    "id",
    "make",
    "model",
    "year",
    "horsepower",
    "engine_cc",
    "transmission",
]

NEW_CAR = {
    "make": "Tesla",
    "model": "Roadster",
    "year": 2025,
    "horsepower": 1000,
    "engine_cc": 0,
    "transmission": "Automatic",
}


def test_create_car():
    response = client.post("/cars", json=NEW_CAR)
    assert response.status_code == 201
    car = response.json()
    for key in CAR_FIELDS:
        assert key in car
    assert car["make"] == "Tesla"

    created = next(c for c in cars if c["id"] == car["id"])
    assert created["model"] == "Roadster"


def test_update_car():
    car_id = cars[0]["id"]
    body = {k: v for k, v in cars[0].items() if k != "id"}
    body["year"] = 2000
    response = client.put(f"/cars/{car_id}", json=body)
    assert response.status_code == 200
    assert response.json()["year"] == 2000


def test_update_car_not_found():
    response = client.put("/cars/999999", json=NEW_CAR)
    assert response.status_code == 404


def test_patch_car():
    car_id = cars[0]["id"]
    response = client.patch(f"/cars/{car_id}", json={"year": 1999})
    assert response.status_code == 200
    assert response.json()["year"] == 1999


def test_patch_car_not_found():
    response = client.patch("/cars/999999", json={"year": 1999})
    assert response.status_code == 404


def test_delete_car():
    car_id = cars[-1]["id"]
    response = client.delete(f"/cars/{car_id}")
    assert response.status_code == 204
    assert all(c["id"] != car_id for c in cars)


def test_delete_car_not_found():
    response = client.delete("/cars/999999")
    assert response.status_code == 404
