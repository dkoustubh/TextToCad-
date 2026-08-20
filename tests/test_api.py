from fastapi.testclient import TestClient
from app.api import app

client = TestClient(app)

def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "OpenCascade" in data["engine"]

def test_agents_endpoint():
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data
    assert len(data["agents"]) >= 1
    assert data["agents"][0]["ip_address"] == "192.168.11.150"

def test_chat_generation_endpoint():
    req = {
        "prompt": "Create a 100 x 60 x 20 mm block with four 8 mm through holes.",
        "workstation_ip": "192.168.11.150"
    }
    resp = client.post("/api/chat", json=req)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["validation"]["is_valid"] is True
    assert data["validation"]["brep_check_status"] is True
    assert data["validation"]["volume_mm3"] > 100000.0
    assert data["step_url"] is not None
