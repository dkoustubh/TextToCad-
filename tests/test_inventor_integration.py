import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.api import app
from app.project_manager import project_manager

client = TestClient(app)

def test_inventor_status_offline():
    """Verify that /api/inventor/status gracefully reports offline when agent is not reachable."""
    resp = client.get("/api/inventor/status?workstation_ip=192.168.11.150")
    assert resp.status_code == 200
    data = resp.json()
    assert data["online"] is False
    assert data["workstation_ip"] == "192.168.11.150"
    assert "8001" in data["agent_url"]
    assert "unreachable" in data["message"].lower()

@patch("httpx.AsyncClient.get")
def test_inventor_status_online(mock_get):
    """Verify that /api/inventor/status parses online health payload from agent."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "online",
        "workstation": "192.168.11.150",
        "inventor_connected": True,
        "inventor_version": "Autodesk Inventor Professional 2026",
        "active_documents": 2
    }
    mock_get.return_value = mock_resp

    resp = client.get("/api/inventor/status?workstation_ip=192.168.11.150")
    assert resp.status_code == 200
    data = resp.json()
    assert data["online"] is True
    assert data["inventor_connected"] is True
    assert "2026" in data["inventor_version"]
    assert data["active_documents"] == 2

def test_dispatch_invalid_version():
    """Verify 404 is returned when attempting to dispatch a non-existent version."""
    resp = client.post("/api/projects/proj_nonexistent/versions/v999/inventor", json={
        "workstation_ip": "192.168.11.150",
        "create_assembly": False
    })
    assert resp.status_code == 404

@patch("httpx.AsyncClient.post")
def test_dispatch_part_success(mock_post):
    """Verify successful dispatch to Inventor for a Part (.ipt)."""
    # Ensure at least one project and version exists
    projects = project_manager.list_projects()
    if not projects or not projects[0].versions:
        proj = project_manager.create_project("Test Bracket", "proj_test_dispatch")
        v = project_manager.add_version(
            project_id="proj_test_dispatch",
            prompt="Test 20mm cube",
            job_id="test_job_dispatch"
        )
        p_id = "proj_test_dispatch"
        v_label = v.version_label
    else:
        p_id = projects[0].project_id
        v_label = projects[0].versions[0].version_label

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": True,
        "message": "Opened and saved native Autodesk Inventor Part (.ipt)",
        "file_path": r"C:\OmniCAD_Models\test_part.ipt",
        "file_type": "Part (.ipt)",
        "inventor_version": "Autodesk Inventor 2026",
        "open_documents_count": 1
    }
    mock_post.return_value = mock_resp

    payload = {
        "workstation_ip": "192.168.11.150",
        "create_assembly": False,
        "bring_to_front": True
    }

    resp = client.post(f"/api/projects/{p_id}/versions/{v_label}/inventor", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["file_type"] == "Part (.ipt)"
    assert "test_part.ipt" in data["file_path"]

@patch("httpx.AsyncClient.post")
def test_dispatch_assembly_success(mock_post):
    """Verify successful dispatch to Inventor for an Assembly (.iam)."""
    projects = project_manager.list_projects()
    p_id = projects[0].project_id
    v_label = projects[0].versions[0].version_label

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": True,
        "message": "Created and opened native Autodesk Inventor Assembly (.iam)",
        "file_path": r"C:\OmniCAD_Models\test_assembly.iam",
        "file_type": "Assembly (.iam)",
        "inventor_version": "Autodesk Inventor 2026",
        "open_documents_count": 2
    }
    mock_post.return_value = mock_resp

    payload = {
        "workstation_ip": "192.168.11.150",
        "create_assembly": True,
        "bring_to_front": True
    }

    resp = client.post(f"/api/projects/{p_id}/versions/{v_label}/inventor", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["file_type"] == "Assembly (.iam)"
    assert "test_assembly.iam" in data["file_path"]
