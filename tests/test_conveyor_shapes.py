import pytest
import os
import asyncio
from app.llm_client import llm_client
from app.cad_engine import cad_engine
from app.pipeline import pipeline

TEST_PROMPTS = [
    ("hex_bolt", "M10 x 50mm hex bolt DIN 933"),
    ("socket_cap_screw", "M8 x 40mm socket head cap screw DIN 912"),
    ("conveyor_roller", "Heavy conveyor roller diameter 50mm length 400mm with 12mm shaft"),
    ("tapered_roller", "Tapered curve conveyor roller diameter 60mm length 350mm"),
    ("spur_gear", "Involute spur gear 24 teeth module 2 face width 15mm bore 12mm"),
    ("sprocket", "Conveyor chain sprocket 18 teeth outer diameter 75mm thickness 10mm bore 16mm"),
    ("stepped_shaft", "Stepped drive shaft diameter 40mm length 200mm with keyway"),
    ("motor_mount", "Conveyor motor mount plate 180x140x12mm with tensioning slots and 60mm pilot bore"),
    ("sensor_bracket", "Photoelectric sensor mounting bracket 35x60x45mm with M18 barrel hole"),
    ("reinforced_l_bracket", "Heavy duty reinforced L-bracket 80x80x50mm with triangular stiffener gusset"),
    ("pillow_block", "UCP pillow block bearing housing 25mm bore"),
    ("ball_transfer_unit", "Conveyor ball transfer unit with 25mm ball"),
    ("sphere", "3D solid sphere diameter 40mm"),
    ("cone", "Truncated cone 60mm bottom diameter 30mm top diameter 80mm height"),
    ("pipe", "Hollow pipe sleeve outer diameter 50mm length 100mm wall thickness 4mm"),
]

@pytest.mark.parametrize("shape_name,prompt", TEST_PROMPTS)
def test_fallback_synthesizer_generates_valid_solid(shape_name, prompt):
    code, plan = llm_client._synthesize_fallback_script(prompt)
    assert code is not None and len(code) > 0
    assert "with bd.BuildPart() as part:" in code
    assert "model = part.part" in code

    # Execute solid through CADEngine
    solid_obj = cad_engine._execute_python_script(code)
    assert solid_obj is not None
    assert solid_obj.is_valid
    assert solid_obj.volume > 0.0

@pytest.mark.parametrize("shape_name,prompt", [
    ("hex_bolt", "M10 x 50mm hex bolt DIN 933"),
    ("conveyor_roller", "Heavy conveyor roller diameter 50mm length 300mm with 12mm shaft"),
    ("spur_gear", "Spur gear 20 teeth module 2 face width 12mm bore 10mm"),
    ("reinforced_l_bracket", "Reinforced L-bracket 70x70x40mm with gusset"),
    ("pillow_block", "Pillow block bearing housing 20mm bore"),
])
def test_pipeline_end_to_end_conveyor_shapes(shape_name, prompt):
    result = asyncio.run(pipeline.run(prompt=prompt))
    assert result.success is True
    assert result.validation.is_valid is True
    assert result.validation.step_import_verified is True
    assert result.validation.volume_mm3 > 0.0
    assert os.path.exists(result.validation.step_path)
    assert os.path.exists(result.validation.stl_path)
    assert os.path.exists(result.validation.glb_path)
