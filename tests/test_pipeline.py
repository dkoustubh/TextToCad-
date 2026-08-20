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
