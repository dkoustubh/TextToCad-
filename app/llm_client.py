import re
import json
import logging
import httpx
from typing import Dict, Any, Optional, Tuple, List
from app.config import settings
from app.schemas import CADPlan, HoleDefinition

logger = logging.getLogger(__name__)

GEMMA_CAD_SYSTEM_PROMPT = """You are an expert mechanical CAD designer and build123d / OpenCascade software engineer.
Your task is to convert ANY natural-language mechanical engineering request into an executable build123d Python script that produces a genuine, watertight 3D CAD solid.

RULES & CONVENTIONS:
1. ALWAYS use millimeters (mm) for all dimensions (1 cm = 10 mm, 1 m = 1000 mm, 1 in = 25.4 mm).
2. Code MUST be self-contained and assign the final solid object to `model = part.part`.
3. Do NOT invent undefined variables. Define all coordinates and parameter variables before using them.
4. Core build123d patterns to use:
   - Import: `import math\nimport build123d as bd`
   - Context: `with bd.BuildPart() as part:`
   - 3D Primitives: `bd.Box(l, w, h)`, `bd.Cylinder(radius=r, height=h)`, `bd.Sphere(radius=r)`, `bd.Cone(bottom_radius=r1, top_radius=r2, height=h)`
   - 2D Sketches on Planes: `with bd.BuildSketch(bd.Plane.XY):`, `bd.Rectangle(w, h)`, `bd.Circle(radius=r)`, `bd.SlotOverall(width=w, height=h)`
   - Extrusion: `bd.extrude(amount=d, both=True/False, mode=bd.Mode.ADD/SUBTRACT)`
   - Revolution: `bd.revolve(axis=bd.Axis.Z, mode=bd.Mode.ADD/SUBTRACT)`
   - Positioning & Hole Patterns:
     ```python
     # Example: Hole Pattern on Plate
     with bd.BuildSketch(bd.Plane.XY):
         with bd.Locations([(x1, y1), (x2, y2), (x3, y3)]):
             bd.Circle(radius=hole_r)
     bd.extrude(amount=thickness * 2, both=True, mode=bd.Mode.SUBTRACT)
     ```
     ```python
     # Example: Polar Bolt Circle Pattern
     with bd.BuildSketch(bd.Plane.XY):
         with bd.PolarLocations(radius=pcd / 2.0, count=n_holes):
             bd.Circle(radius=hole_r)
     bd.extrude(amount=thickness * 2, both=True, mode=bd.Mode.SUBTRACT)
     ```
     ```python
     # Example: Stepped Shaft (stacked along Z)
     bd.Cylinder(radius=r1, height=h1)
     with bd.Locations([(0, 0, h1/2 + h2/2)]):
         bd.Cylinder(radius=r2, height=h2)
     ```
   - Fillets / Chamfers: wrap in try/except or select specific vertical edges with `part.edges().filter_by(bd.Axis.Z)`.

5. Return your output as a strict JSON object with:
   - "explanation": Short mechanical explanation of the design
   - "parameters": Dict of all key parametric dimensions (e.g. {"length_mm": 250, "width_mm": 80, ...})
   - "shape_type": Short identifier (e.g. "conveyor_bracket", "stepped_shaft", "flange", "sprocket", "pulley", "custom")
   - "python_code": The complete, executable build123d Python script
"""

REPAIR_SYSTEM_PROMPT = """You are an expert mechanical CAD debugger for build123d / OpenCascade.
The previous CAD generation script failed to execute. Fix the syntax, variable definitions, or OpenCascade topology errors and return the corrected, working build123d Python script.

Ensure:
1. Valid build123d syntax (`import build123d as bd`, `with bd.BuildPart() as part:`, `model = part.part`).
2. Define all variables before use. Avoid referencing undefined variables or list comprehensions with missing iterables.
3. Output strict JSON with keys: "explanation", "parameters", "shape_type", "python_code".
"""

class LLMClient:
    def __init__(self):
        self.api_base = settings.VLLM_API_BASE.rstrip("/")
        self.model = settings.VLLM_MODEL

    async def generate_cad_code(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[CADPlan, str]:
        """
        Invokes Gemma to reason about mechanical requirements and synthesize
        a parametric build123d Python script.
        """
        user_content = prompt

        # If modifying an existing version, provide previous context
        if context and context.get("previous_prompt"):
            prev_prompt = context.get("previous_prompt")
            prev_code = context.get("previous_code", "")
            prev_section = f"Previous Working Python Script:\n```python\n{prev_code}\n```\n" if prev_code else ""
            user_content = f"""PREVIOUS CAD DESIGN:
Prompt: "{prev_prompt}"
{prev_section}
USER MODIFICATION REQUEST:
"{prompt}"

Please update and modify the existing parametric design to incorporate the user's requested changes while preserving the existing features."""

        messages = [
            {"role": "system", "content": GEMMA_CAD_SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ]

        raw_response = await self._call_vllm(messages)
        return self._parse_llm_cad_response(raw_response, prompt)

    async def repair_cad_code(
        self,
        prompt: str,
        failed_code: str,
        error_traceback: str
    ) -> Tuple[CADPlan, str]:
        """
        Sends the failed CAD script and OpenCascade traceback back to Gemma
        for automatic iterative repair.
        """
        user_content = f"""ORIGINAL USER PROMPT:
"{prompt}"

FAILED BUILD123D PYTHON SCRIPT:
```python
{failed_code}
```

EXECUTION ERROR / TRACEBACK:
{error_traceback}

Please analyze the error and provide a corrected, working build123d Python script that fulfills the original prompt."""

        messages = [
            {"role": "system", "content": REPAIR_SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ]

        raw_response = await self._call_vllm(messages)
        return self._parse_llm_cad_response(raw_response, prompt)

    async def _call_vllm(self, messages: List[Dict[str, str]], timeout: float = 35.0) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.15,
            "max_tokens": 1200
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self.api_base}/chat/completions",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    logger.info(f"Gemma inference response received ({len(content)} chars)")
                    return content
                else:
                    logger.warning(f"vLLM API returned status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.warning(f"vLLM API call failed ({e}); falling back to deterministic generator.")
        return ""

    def _parse_llm_cad_response(self, raw_text: str, original_prompt: str) -> Tuple[CADPlan, str]:
        """
        Extracts JSON metadata and executable build123d python code from LLM output.
        """
        py_code = ""
        explanation = f"Generated CAD solid from prompt: {original_prompt}"
        parameters = {}
        shape_type = "custom_solid"
        tool = "build123d.script"

        # 1. Try parsing JSON
        if raw_text:
            try:
                # Find JSON block
                json_match = re.search(r"\{[\s\S]*\}", raw_text)
                if json_match:
                    data = json.loads(json_match.group(0))
                    explanation = data.get("explanation", explanation)
                    parameters = data.get("parameters", parameters)
                    shape_type = data.get("shape_type", shape_type)
                    py_code = data.get("python_code", "")
            except Exception as e:
                logger.debug(f"JSON parse error in LLM response: {e}")

            # 2. Extract python code block if not in JSON or enclosed in markdown
            if not py_code:
                code_match = re.search(r"```(?:python|py)?\s*([\s\S]*?)\s*```", raw_text)
                if code_match:
                    py_code = code_match.group(1).strip()

        # 3. If LLM provided valid code, format and return
        if py_code and ("BuildPart" in py_code or "BuildSketch" in py_code or "bd." in py_code):
            # Ensure model assignment is present
            if "model =" not in py_code:
                py_code += "\nmodel = part.part\n"

            plan = CADPlan(
                tool=tool,
                shape_type=shape_type,
                parameters=parameters,
                explanation=explanation,
                python_script=py_code
            )
            return plan, py_code

        # 4. Fallback: Dynamic mechanical script generator for known patterns
        py_code, plan = self._synthesize_fallback_script(original_prompt)
        return plan, py_code

    def _synthesize_fallback_script(self, prompt: str) -> Tuple[str, CADPlan]:
        """
        Robust dynamic CAD script synthesizer for when LLM is unavailable.
        """
        p = prompt.lower().strip()

        # Extract numerical dimensions
        dims_3d = re.findall(r"(\d+(?:\.\d+)?)\s*(?:mm|cm|in|m)?\s*[x×*]\s*(\d+(?:\.\d+)?)\s*(?:mm|cm|in|m)?\s*[x×*]\s*(\d+(?:\.\d+)?)\s*(mm|cm|in|m)?", p)
        all_nums = [float(x) for x in re.findall(r"\b\d+(?:\.\d+)?\b", p)]

        # Conveyor bracket / Bracket with slots and holes
        if "bracket" in p or "conveyor" in p or "slot" in p:
            l = float(dims_3d[0][0]) if dims_3d else (all_nums[0] if len(all_nums) > 0 else 250.0)
            w = float(dims_3d[0][1]) if dims_3d else (all_nums[1] if len(all_nums) > 1 else 80.0)
            h = float(dims_3d[0][2]) if dims_3d else (all_nums[2] if len(all_nums) > 2 else 10.0)

            code = f"""# Parametric Conveyor Bracket Solid
import build123d as bd

length = {l}
width = {w}
thickness = {h}

with bd.BuildPart() as part:
    # Base plate
    bd.Box(length, width, thickness)

    # 6 M8 Mounting holes in 2 rows of 3
    hole_positions = [
        ({l} * 0.2 - length/2, {w} * 0.25 - width/2, 0),
        (0, {w} * 0.25 - width/2, 0),
        ({l} * 0.8 - length/2, {w} * 0.25 - width/2, 0),
        ({l} * 0.2 - length/2, {w} * 0.75 - width/2, 0),
        (0, {w} * 0.75 - width/2, 0),
        ({l} * 0.8 - length/2, {w} * 0.75 - width/2, 0)
    ]
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations(hole_positions):
            bd.Circle(radius=4.0)
    bd.extrude(amount=thickness * 2, both=True, mode=bd.Mode.SUBTRACT)

    # 2 Slots (40mm x 8mm)
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations([({l} * 0.35 - length/2, 0, 0), ({l} * 0.65 - length/2, 0, 0)]):
            bd.SlotOverall(width=min(40.0, {l} * 0.2), height=8.0)
    bd.extrude(amount=thickness * 2, both=True, mode=bd.Mode.SUBTRACT)

    # 3mm Outer Corner Fillets
    try:
        vert_edges = part.edges().filter_by(bd.Axis.Z)
        if vert_edges:
            bd.fillet(vert_edges, radius=3.0)
    except Exception:
        pass

model = part.part
"""
            plan = CADPlan(
                tool="inventor.create_bracket",
                shape_type="conveyor_bracket",
                length_mm=l,
                width_mm=w,
                height_mm=h,
                parameters={"length_mm": l, "width_mm": w, "thickness_mm": h, "hole_count": 6, "slot_count": 2},
                explanation=f"Conveyor side bracket ({l}x{w}x{h}mm) with 6 M8 holes, 2 slots, and 3mm corner fillets."
            )
            return code, plan

        # Sprocket / Gear
        if "sprocket" in p or "gear" in p or "teeth" in p:
            teeth = int(all_nums[0]) if len(all_nums) > 0 else 16
            od = float(all_nums[1]) if len(all_nums) > 1 else 60.0
            thk = float(all_nums[2]) if len(all_nums) > 2 else 10.0
            bore = float(all_nums[3]) if len(all_nums) > 3 else 15.0

            code = f"""# Parametric Sprocket Gear Solid
import math
import build123d as bd

od = {od}
teeth = {teeth}
thk = {thk}
bore = {bore}

with bd.BuildPart() as part:
    bd.Cylinder(radius=od / 2.0, height=thk)
    tooth_r = (od / teeth) * 0.8
    pitch_r = od / 2.0
    notch_locs = [
        (pitch_r * math.cos(2 * math.pi * i / teeth), pitch_r * math.sin(2 * math.pi * i / teeth))
        for i in range(teeth)
    ]
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations(notch_locs):
            bd.Circle(radius=tooth_r)
    bd.extrude(amount=thk * 2, both=True, mode=bd.Mode.SUBTRACT)

    with bd.BuildSketch(bd.Plane.XY):
        bd.Circle(radius=bore / 2.0)
    bd.extrude(amount=thk * 2, both=True, mode=bd.Mode.SUBTRACT)

model = part.part
"""
            plan = CADPlan(
                tool="inventor.create_sprocket",
                shape_type="sprocket",
                diameter_mm=od,
                height_mm=thk,
                parameters={"outer_diameter_mm": od, "teeth_count": teeth, "thickness_mm": thk, "bore_diameter_mm": bore},
                explanation=f"{teeth}-tooth sprocket gear (Ø{od}mm OD, {thk}mm thick, Ø{bore}mm bore)."
            )
            return code, plan

        # Stepped Shaft with Keyway
        if "shaft" in p or "keyway" in p or "stepped" in p:
            l = all_nums[0] if len(all_nums) > 0 else 200.0
            d1 = all_nums[1] if len(all_nums) > 1 else 30.0
            d2 = all_nums[2] if len(all_nums) > 2 else 25.0
            d3 = all_nums[3] if len(all_nums) > 3 else 20.0

            code = f"""# Parametric Stepped Shaft with Keyway
import build123d as bd

with bd.BuildPart() as part:
    # Main center section (Ø{d1}mm x {l * 0.6}mm)
    bd.Cylinder(radius={d1 / 2.0}, height={l * 0.6})
    # Step 1 (Ø{d2}mm x {l * 0.2}mm)
    with bd.Locations([(0, 0, {l * 0.3 + l * 0.1})]):
        bd.Cylinder(radius={d2 / 2.0}, height={l * 0.2})
    # Step 2 (Ø{d3}mm x {l * 0.2}mm)
    with bd.Locations([(0, 0, -{l * 0.3 + l * 0.1})]):
        bd.Cylinder(radius={d3 / 2.0}, height={l * 0.2})
    # 6mm Keyway slot
    with bd.BuildSketch(bd.Plane.XZ):
        with bd.Locations([(0, {d1 / 2.0})]):
            bd.Rectangle({l * 0.25}, 6.0)
    bd.extrude(amount=6.0, both=True, mode=bd.Mode.SUBTRACT)

model = part.part
"""
            plan = CADPlan(
                tool="inventor.create_stepped_shaft",
                shape_type="stepped_shaft",
                length_mm=l,
                diameter_mm=d1,
                parameters={"length_mm": l, "main_dia_mm": d1, "step1_dia_mm": d2, "step2_dia_mm": d3, "keyway_mm": 6.0},
                explanation=f"Stepped shaft ({l}mm long, Ø{d1}/Ø{d2}/Ø{d3}mm sections with 6mm keyway)."
            )
            return code, plan

        # Flange with Bolt Circle
        if "flange" in p or "bolt circle" in p or "pcd" in p:
            od = all_nums[0] if len(all_nums) > 0 else 120.0
            bore = all_nums[1] if len(all_nums) > 1 else 50.0
            holes_cnt = int(all_nums[2]) if len(all_nums) > 2 else 8
            pcd = all_nums[3] if len(all_nums) > 3 else 90.0
            thk = all_nums[4] if len(all_nums) > 4 else 5.0

            code = f"""# Parametric Mounting Flange with Bolt Circle
import build123d as bd

with bd.BuildPart() as part:
    bd.Cylinder(radius={od / 2.0}, height={thk})
    # Center bore
    with bd.BuildSketch(bd.Plane.XY):
        bd.Circle(radius={bore / 2.0})
    bd.extrude(amount={thk * 2}, both=True, mode=bd.Mode.SUBTRACT)
    # Bolt circle
    with bd.BuildSketch(bd.Plane.XY):
        with bd.PolarLocations(radius={pcd / 2.0}, count={holes_cnt}):
            bd.Circle(radius=5.0)
    bd.extrude(amount={thk * 2}, both=True, mode=bd.Mode.SUBTRACT)

model = part.part
"""
            plan = CADPlan(
                tool="inventor.create_flange",
                shape_type="flange",
                diameter_mm=od,
                height_mm=thk,
                parameters={"outer_diameter_mm": od, "bore_mm": bore, "bolt_circle_pcd_mm": pcd, "hole_count": holes_cnt, "thickness_mm": thk},
                explanation=f"Mounting flange (Ø{od}mm OD, Ø{bore}mm bore, {holes_cnt} M10 holes on {pcd}mm PCD)."
            )
            return code, plan

        # Default Prismatic Box
        l = float(dims_3d[0][0]) if dims_3d else (all_nums[0] if len(all_nums) > 0 else 100.0)
        w = float(dims_3d[0][1]) if dims_3d else (all_nums[1] if len(all_nums) > 1 else 60.0)
        h = float(dims_3d[0][2]) if dims_3d else (all_nums[2] if len(all_nums) > 2 else 20.0)

        code = f"""# Parametric Prismatic CAD Block
import build123d as bd

with bd.BuildPart() as part:
    bd.Box({l}, {w}, {h})
    # 4 Corner mounting holes
    off_x = min(15.0, {l} * 0.15)
    off_y = min(12.0, {w} * 0.15)
    hx = ({l} / 2.0) - off_x
    hy = ({w} / 2.0) - off_y
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations([(hx, hy), (hx, -hy), (-hx, hy), (-hx, -hy)]):
            bd.Circle(radius=4.0)
    bd.extrude(amount={h * 2}, both=True, mode=bd.Mode.SUBTRACT)

model = part.part
"""
        plan = CADPlan(
            tool="inventor.create_box_with_holes",
            shape_type="box_with_holes",
            length_mm=l,
            width_mm=w,
            height_mm=h,
            parameters={"length_mm": l, "width_mm": w, "height_mm": h, "hole_count": 4},
            explanation=f"Prismatic CAD mounting plate ({l}x{w}x{h}mm with four 8mm corner holes)."
        )
        return code, plan

llm_client = LLMClient()
