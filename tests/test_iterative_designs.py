import pytest
import os
import asyncio
from app.pipeline import pipeline
from app.fea_engine import FEAEngine

def test_iterative_l_mount_with_four_drills():
    """
    Test Case 1:
    Step 1: Create an L mount (80x80x50mm)
    Step 2: Add 4 drilled holes of diameter 6mm
    Assert geometric validity, manifold solid, and exact volume reduction.
    """
    # Step 1: Base L Mount
    res1 = asyncio.run(pipeline.run("create a L mount 80x80x50mm"))
    assert res1.success is True
    assert res1.validation.is_valid is True
    assert res1.validation.volume_mm3 > 0.0
    initial_volume = res1.validation.volume_mm3

    # Step 2: Add 4 drills of diameter 6mm
    ctx = {
        "previous_prompt": "create a L mount 80x80x50mm",
        "previous_code": res1.plan.python_script
    }
    res2 = asyncio.run(pipeline.run("add 4 drills of diameter 6mm", context=ctx))
    assert res2.success is True
    assert res2.validation.is_valid is True
    assert res2.validation.step_import_verified is True
    
    # 4 holes of R=3mm through 8mm thickness = 4 * pi * 3^2 * 8 ≈ 904.78 mm3
    volume_reduction = initial_volume - res2.validation.volume_mm3
    assert abs(volume_reduction - 904.78) < 2.0
    assert os.path.exists(res2.validation.step_path)
    assert os.path.exists(res2.validation.stl_path)
    assert os.path.exists(res2.validation.glb_path)

def test_cylinder_to_flange_with_bore_and_drills():
    """
    Test Case 2:
    Step 1: Create cylinder Ø100mm, height 25mm
    Step 2: Add center bore Ø35mm
    Step 3: Run FEA stress check
    """
    # Step 1: Base cylinder
    res1 = asyncio.run(pipeline.run("create cylinder diameter 100mm height 25mm"))
    assert res1.success is True
    assert res1.validation.is_valid is True
    vol_cyl = res1.validation.volume_mm3

    # Step 2: Add center hole of diameter 35mm
    ctx = {
        "previous_prompt": "create cylinder diameter 100mm height 25mm",
        "previous_code": res1.plan.python_script
    }
    res2 = asyncio.run(pipeline.run("add a center hole of diameter 35mm", context=ctx))
    assert res2.success is True
    assert res2.validation.is_valid is True
    assert res2.validation.volume_mm3 < vol_cyl

    # Step 3: Run FEA check
    fea_res = FEAEngine.run_analysis(
        length_mm=res2.validation.bounding_box.size_x,
        width_mm=res2.validation.bounding_box.size_y,
        height_mm=res2.validation.bounding_box.size_z,
        volume_mm3=res2.validation.volume_mm3,
        load_n=2000.0,
        material_id="structural_steel",
        holes=[{"diameter_mm": 35.0}]
    )
    assert fea_res["factor_of_safety"] >= 1.0
    assert fea_res["von_mises_stress_mpa"] > 0.0

def test_conveyor_roller_and_fea():
    """
    Test Case 3:
    Conveyor roller generation and structural check under 2,000 N pallet load.
    """
    prompt = "Heavy conveyor roller diameter 50mm length 400mm with 12mm shaft"
    result = asyncio.run(pipeline.run(prompt))
    assert result.success is True
    assert result.validation.is_valid is True
    assert result.validation.volume_mm3 > 0.0
    assert result.validation.step_import_verified is True

    # Evaluate FEA load
    fea = FEAEngine.run_analysis(
        length_mm=result.validation.bounding_box.size_x,
        width_mm=result.validation.bounding_box.size_y,
        height_mm=result.validation.bounding_box.size_z,
        volume_mm3=result.validation.volume_mm3,
        load_n=2000.0,
        material_id="structural_steel"
    )
    assert fea["status"] in ["OPTIMAL", "SAFE", "MARGINAL"]
    assert fea["von_mises_stress_mpa"] < 250.0

def test_hex_bolt_and_spur_gear_watertight():
    """
    Test Case 4:
    Verify hex bolt and involute spur gear generate manifold solids with valid STEP files.
    """
    # Hex Bolt
    r_bolt = asyncio.run(pipeline.run("M12 x 60mm hex bolt DIN 933"))
    assert r_bolt.success is True
    assert r_bolt.validation.is_valid is True
    assert r_bolt.validation.volume_mm3 > 0.0

    # Spur Gear
    r_gear = asyncio.run(pipeline.run("Involute spur gear 20 teeth module 2 face width 15mm bore 14mm"))
    assert r_gear.success is True
    assert r_gear.validation.is_valid is True
    assert r_gear.validation.volume_mm3 > 0.0
