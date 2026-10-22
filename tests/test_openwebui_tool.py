import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from openwebui_tools.omnicad_tool import Tools


@pytest.mark.anyio
async def test_omnicad_tool_init():
    tool = Tools()
    assert tool.valves.CAD_BACKEND_URL == "http://192.168.11.86:9999"
    assert tool.valves.WORKSTATION_IP == "192.168.11.150"
    assert tool.valves.WORKSTATION_PORT == 8001
    assert tool.valves.AUTO_PUSH_TO_INVENTOR is True


@pytest.mark.anyio
async def test_omnicad_tool_generate_success():
    tool = Tools()
    mock_emitter = AsyncMock()

    mock_chat_response = {
        "project_id": "proj_test",
        "version_label": "v001",
        "plan": {
            "shape_type": "Box",
            "explanation": "Test 100x50x10 mm plate",
            "holes": [{"count": 4, "diameter_mm": 6.0, "pattern_type": "corners"}]
        },
        "validation": {
            "is_valid": True,
            "volume_mm3": 50000.0,
            "surface_area_mm2": 13000.0,
            "face_count": 6,
            "edge_count": 12,
            "vertex_count": 8,
            "bounding_box": {"size_x": 100.0, "size_y": 50.0, "size_z": 10.0}
        },
        "step_url": "http://192.168.11.86:9999/api/projects/proj_test/versions/v001/files/model.step",
        "stl_url": "http://192.168.11.86:9999/api/projects/proj_test/versions/v001/files/model.stl",
        "glb_url": "http://192.168.11.86:9999/api/projects/proj_test/versions/v001/files/model.glb",
        "py_url": "http://192.168.11.86:9999/api/projects/proj_test/versions/v001/files/model.py",
        "ipt_url": "http://192.168.11.86:9999/api/projects/proj_test/versions/v001/files/model.ipt",
        "iam_url": "http://192.168.11.86:9999/api/projects/proj_test/versions/v001/files/model.iam",
        "view_url": "http://192.168.11.86:9999/?project=proj_test&version=v001",
        "duration_ms": 350
    }

    with patch("requests.post") as mock_post:
        # Mock backend response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_chat_response
        mock_post.return_value = mock_resp

        result = await tool.generate_cad_design(
            prompt="100x50x10 mm plate with 4 holes",
            project_id="proj_test",
            __event_emitter__=mock_emitter
        )

        assert "OmniCAD Design Generated: `proj_test` (v001)" in result
        assert "http://192.168.11.86:9999/?project=proj_test&version=v001" in result
        assert "model.ipt" in result
        assert "model.iam" in result
        assert "model.step" in result
        assert "50,000.0 mm³" in result
        assert mock_emitter.called


@pytest.mark.anyio
async def test_omnicad_tool_health_check():
    tool = Tools()
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"version": "1.0.0", "inventor_connected": True}
        mock_get.return_value = mock_resp

        result = await tool.check_omnicad_health()
        assert "OmniCAD System Health Diagnostics" in result
        assert "192.168.11.86:9999" in result
        assert "192.168.11.150" in result
