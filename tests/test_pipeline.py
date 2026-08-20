import asyncio
import pytest
from app.pipeline import pipeline

def test_pipeline_100x60x20_with_four_holes():
    prompt = "Create a 100 x 60 x 20 mm block with four 8 mm through holes."
    result = asyncio.run(pipeline.run(prompt=prompt, job_id="test_pipeline_run"))

    assert result.success is True, f"Pipeline failed: {result.error}"
    assert result.plan is not None
    assert result.validation is not None
    assert result.validation.is_valid is True
    assert result.validation.is_solid is True
    assert result.validation.brep_check_status is True
    assert result.validation.step_import_verified is True
    assert abs(result.validation.bounding_box.size_x - 100.0) < 0.1
    assert abs(result.validation.bounding_box.size_y - 60.0) < 0.1
    assert abs(result.validation.bounding_box.size_z - 20.0) < 0.1

def test_pipeline_cube_3cm():
    prompt = "Create a cube of 3 cm."
    result = asyncio.run(pipeline.run(prompt=prompt, job_id="test_pipeline_cube"))

    assert result.success is True
    assert result.validation is not None
    assert result.validation.is_valid is True
    assert abs(result.validation.volume_mm3 - 27000.0) < 0.1

def test_pipeline_iterative_modification():
    # Step 1: Create 30mm Cube
    res1 = asyncio.run(pipeline.run(prompt="Create a 30mm cube", job_id="test_iter_1"))
    assert res1.success is True
    assert abs(res1.validation.volume_mm3 - 27000.0) < 0.1
    
    # Step 2: Reduce length to 20mm
    ctx1 = {
        "previous_prompt": "Create a 30mm cube",
        "previous_code": res1.plan.python_script
    }
    res2 = asyncio.run(pipeline.run(prompt="reduce the length to 20mm", job_id="test_iter_2", context=ctx1))
    assert res2.success is True
    # Volume of 20 x 30 x 30 = 18000 mm3
    assert abs(res2.validation.volume_mm3 - 18000.0) < 1.0
    assert abs(res2.validation.bounding_box.size_x - 20.0) < 0.5

    # Step 3: Add a hole of 2mm
    ctx2 = {
        "previous_prompt": "reduce the length to 20mm",
        "previous_code": res2.plan.python_script
    }
    res3 = asyncio.run(pipeline.run(prompt="add a hole of 2mm in center", job_id="test_iter_3", context=ctx2))
    assert res3.success is True
    # Volume should decrease by hole volume (pi * 1^2 * 30 ≈ 94.2 mm3)
    assert res3.validation.volume_mm3 < 18000.0
    assert res3.validation.volume_mm3 > 17800.0
