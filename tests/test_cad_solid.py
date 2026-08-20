import os
import pytest
from app.schemas import CADPlan, HoleDefinition
from app.cad_engine import cad_engine
from app.cad_validator import cad_validator

def test_100x60x20_block_with_four_8mm_through_holes():
    """
    Test requirement: Create a 100 x 60 x 20 mm block with four 8 mm through holes.
    Verify the STEP is a genuine valid CAD solid.
    """
    plan = CADPlan(
        tool="inventor.create_box_with_holes",
        shape_type="box_with_holes",
        length_mm=100.0,
        width_mm=60.0,
        height_mm=20.0,
        holes=[
            HoleDefinition(
                diameter_mm=8.0,
                pattern_type="grid_4_corners",
                count=4,
                through=True,
                edge_offset_x_mm=15.0,
                edge_offset_y_mm=12.0
            )
        ],
        parameters={
            "length_mm": 100.0,
            "width_mm": 60.0,
            "height_mm": 20.0,
            "hole_diameter_mm": 8.0,
            "hole_count": 4
        }
    )

    solid_obj, report = cad_engine.generate_from_plan(plan, output_id="test_block_4holes")

    # 1. Verification of solid validity
    assert report.is_valid is True, f"Report invalid: {report.message}"
    assert report.is_solid is True, "Generated entity is not a 3D solid"
    assert report.brep_check_status is True, "OpenCascade BRepCheck failed"
    assert report.step_import_verified is True, "STEP file re-import failed"

    # 2. Mathematical volume check
    # Box volume = 100 * 60 * 20 = 120,000 mm3
    # 4 holes volume = 4 * pi * (4^2) * 20 = 4021.2386 mm3
    # Expected net volume ≈ 115,978.76 mm3
    expected_vol = 120000.0 - (4.0 * 3.141592653589793 * (4.0 ** 2) * 20.0)
    assert abs(report.volume_mm3 - expected_vol) < 1.0, f"Volume mismatch: got {report.volume_mm3}, expected {expected_vol}"

    # 3. Bounding box check
    assert abs(report.bounding_box.size_x - 100.0) < 0.1
    assert abs(report.bounding_box.size_y - 60.0) < 0.1
    assert abs(report.bounding_box.size_z - 20.0) < 0.1

    # 4. Topology check: 6 external faces + 4 inner cylindrical surfaces = at least 10 faces
    assert report.face_count >= 10, f"Expected at least 10 faces, got {report.face_count}"

    # 5. STEP file check
    assert os.path.exists(report.step_path)
    assert os.path.getsize(report.step_path) > 500

def test_cube_30mm_solid():
    plan = CADPlan(
        tool="inventor.create_box",
        shape_type="box",
        length_mm=30.0,
        width_mm=30.0,
        height_mm=30.0,
        parameters={"length_mm": 30.0, "width_mm": 30.0, "height_mm": 30.0}
    )
    solid_obj, report = cad_engine.generate_from_plan(plan, output_id="test_cube_30mm")
    assert report.is_valid is True
    assert abs(report.volume_mm3 - 27000.0) < 0.1
    assert report.face_count == 6
