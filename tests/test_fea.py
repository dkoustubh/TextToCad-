import pytest
import os
from fastapi.testclient import TestClient
from app.api import app
from app.fea_engine import FEAEngine, MATERIALS


def test_fea_materials_database():
    assert "structural_steel" in MATERIALS
    assert "aluminum_6061_t6" in MATERIALS
    assert "titanium_ti6al4v" in MATERIALS
    assert MATERIALS["structural_steel"]["yield_strength_mpa"] == 250.0
    assert MATERIALS["aluminum_6061_t6"]["yield_strength_mpa"] == 276.0


def test_fea_engine_analysis_steel():
    res = FEAEngine.run_analysis(
        length_mm=100.0,
        width_mm=50.0,
        height_mm=10.0,
        volume_mm3=50000.0,
        load_n=1000.0,
        material_id="structural_steel"
    )

    assert "von_mises_stress_mpa" in res
    assert "factor_of_safety" in res
    assert "status" in res
    assert res["status"] in ("OPTIMAL", "SAFE", "MARGINAL", "CRITICAL FAILURE")
    assert res["von_mises_stress_mpa"] > 0.0
    assert res["factor_of_safety"] > 0.0
    assert res["mass_kg"] > 0.0


def test_fea_engine_stress_concentration_with_holes():
    # Part with large hole should have higher stress concentration
    res_no_holes = FEAEngine.run_analysis(
        length_mm=100.0,
        width_mm=50.0,
        height_mm=10.0,
        volume_mm3=50000.0,
        load_n=1000.0,
        material_id="aluminum_6061_t6",
        holes=[]
    )

    res_with_hole = FEAEngine.run_analysis(
        length_mm=100.0,
        width_mm=50.0,
        height_mm=10.0,
        volume_mm3=45000.0,
        load_n=1000.0,
        material_id="aluminum_6061_t6",
        holes=[{"diameter_mm": 15.0}]
    )

    assert res_with_hole["stress_concentration_kt"] > res_no_holes["stress_concentration_kt"]
    assert res_with_hole["von_mises_stress_mpa"] > res_no_holes["von_mises_stress_mpa"]


def test_fea_engine_plot_generation(tmp_path):
    plot_file = str(tmp_path / "fea_plot.png")
    res = FEAEngine.run_analysis(
        length_mm=120.0,
        width_mm=60.0,
        height_mm=12.0,
        volume_mm3=86400.0,
        load_n=2500.0,
        material_id="titanium_ti6al4v",
        output_plot_path=plot_file
    )

    assert res["plot_generated"] is True
    assert os.path.exists(plot_file)
    assert os.path.getsize(plot_file) > 1000  # Valid non-empty PNG


def test_api_fea_materials_endpoint():
    client = TestClient(app)
    resp = client.get("/api/fea/materials")
    assert resp.status_code == 200
    data = resp.json()
    assert "materials" in data
    assert len(data["materials"]) >= 6
