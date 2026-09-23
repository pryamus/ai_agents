from app import models


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_get_update_delete_flow(client):
    create_resp = client.post(
        "/tickets",
        json={
            "title": "API ticket",
            "description": "Created via HTTP",
            "employee_id": 42,
        },
    )
    assert create_resp.status_code == 201
    ticket = create_resp.json()
    assert ticket["title"] == "API ticket"
    assert ticket["status"] == "new"
    ticket_id = ticket["id"]

    list_resp = client.get("/tickets")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    get_resp = client.get(f"/tickets/{ticket_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == ticket_id

    patch_resp = client.patch(
        f"/tickets/{ticket_id}",
        json={"status": "in_progress", "employee_id": 99},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "in_progress"
    assert patch_resp.json()["employee_id"] == 99

    delete_resp = client.delete(f"/tickets/{ticket_id}")
    assert delete_resp.status_code == 204

    assert client.get(f"/tickets/{ticket_id}").status_code == 404


def test_missing_ticket_returns_404(client):
    assert client.get("/tickets/999999").status_code == 404
    assert (
        client.patch(
            "/tickets/999999",
            json={"status": "closed"},
        ).status_code
        == 404
    )
    assert client.delete("/tickets/999999").status_code == 404


def test_invalid_payload_returns_422(client):
    assert (
        client.post(
            "/tickets",
            json={"title": "x", "description": "y", "status": "unknown", "employee_id": 1},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/tickets",
            json={"title": "no description", "employee_id": 1},
        ).status_code
        == 422
    )
    assert client.get("/tickets?limit=100000").status_code == 422


def test_created_status_default_is_new(client):
    resp = client.post(
        "/tickets",
        json={
            "title": "Status check",
            "description": "default status",
            "employee_id": 5,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == models.TicketStatus.new.value
