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
   - Positioning & Hole Patterns:
     ```python
     # Example: Hole Pattern on Plate
     with bd.BuildSketch(bd.Plane.XY):
         with bd.Locations([(x1, y1), (x2, y2)]):
             bd.Circle(radius=hole_r)
     bd.extrude(amount=thickness * 2, both=True, mode=bd.Mode.SUBTRACT)
     ```
5. Return your output as a strict JSON object with:
   - "explanation": Short mechanical explanation of the design
   - "parameters": Dict of all key parametric dimensions (e.g. {"length_mm": 250, "width_mm": 80, ...})
   - "shape_type": Short identifier (e.g. "box_with_holes", "stepped_shaft", "flange", "sprocket", "custom")
   - "python_code": The complete, executable build123d Python script
"""

MODIFICATION_SYSTEM_PROMPT = """You are an expert mechanical CAD designer modifying an existing 3D CAD model.
You are given the PREVIOUS WORKING build123d Python script and a USER MODIFICATION REQUEST.
Your job is to update the previous Python script so that the requested changes (e.g., resizing dimensions, adding holes, changing parameters) are accurately applied to the existing solid.

RULES:
1. Preserve all existing geometry and features from the previous script unless specifically asked to change them.
2. Ensure valid build123d syntax and assign the final solid to `model = part.part`.
3. Output strict JSON with keys: "explanation", "parameters", "shape_type", "python_code".
"""

REPAIR_SYSTEM_PROMPT = """You are an expert mechanical CAD debugger for build123d / OpenCascade.
The previous CAD generation script failed to execute. Fix the syntax, variable definitions, or OpenCascade topology errors and return the corrected, working build123d Python script.

Ensure:
1. Valid build123d syntax (`import build123d as bd`, `with bd.BuildPart() as part:`, `model = part.part`).
2. Define all variables before use.
3. Output strict JSON with keys: "explanation", "parameters", "shape_type", "python_code".
"""

class ParametricModifier:
    """
    High-precision deterministic CAD code transformer.
    Directly updates parametric dimensions, primitives, and features on existing build123d scripts.
    """
    @staticmethod
    def is_modification_request(prompt: str) -> bool:
        p = prompt.lower().strip()
        keywords = [
            "reduce", "increase", "decrease", "change", "modify", "update", "set",
            "make length", "make width", "make height", "make diameter", "make size",
            "add hole", "add a hole", "add holes", "add 4 holes", "add fillet", "add chamfer",
            "add slot", "drill", "remove", "scale", "extend", "shorten", "widen"
        ]
        return any(k in p for k in keywords)

    @staticmethod
    def parse_units_in_text(p: str) -> List[float]:
        matches = re.findall(r"(\d+(?:\.\d+)?)\s*(mm|cm|inch|in|m)?\b", p.lower())
        nums = []
        for val_str, unit in matches:
            v = float(val_str)
            if unit == "cm":
                v *= 10.0
            elif unit in ("in", "inch"):
                v *= 25.4
            elif unit == "m":
                v *= 1000.0
            nums.append(v)
        return nums

    @staticmethod
    def modify_script(prev_code: str, prompt: str) -> Tuple[str, CADPlan]:
        p = prompt.lower().strip()
        code = prev_code
        nums = ParametricModifier.parse_units_in_text(p)
        
        explanation = f"Modified design according to: '{prompt}'"
        params: Dict[str, Any] = {}

        # 1. Check for 3-axis dimension replacement (e.g., "reduce to 20x30x30" or "make it 200 x 100 x 50")
        dims_match = re.findall(r"(\d+(?:\.\d+)?)\s*(?:mm|cm|in|m)?\s*[x×*]\s*(\d+(?:\.\d+)?)\s*(?:mm|cm|in|m)?\s*[x×*]\s*(\d+(?:\.\d+)?)", p)
        if dims_match:
            l, w, h = float(dims_match[0][0]), float(dims_match[0][1]), float(dims_match[0][2])
            code = re.sub(r"bd\.Box\s*\([^)]*\)", f"bd.Box({l}, {w}, {h})", code)
            code = re.sub(r"Box\s*\([^)]*\)", f"Box({l}, {w}, {h})", code)
            params.update({"length_mm": l, "width_mm": w, "height_mm": h})

        # 2. Check for length / X modifications
        if ("length" in p or "long" in p) and nums:
            val = nums[0]
            params["length_mm"] = val
            if re.search(r"length\s*=\s*\d+(?:\.\d+)?", code):
                code = re.sub(r"length\s*=\s*\d+(?:\.\d+)?", f"length = {val}", code)
            elif re.search(r"bd\.Box\s*\(\s*\d+(?:\.\d+)?\s*,", code):
                code = re.sub(r"bd\.Box\s*\(\s*\d+(?:\.\d+)?\s*,", f"bd.Box({val},", code)
            elif re.search(r"Box\s*\(\s*\d+(?:\.\d+)?\s*,", code):
                code = re.sub(r"Box\s*\(\s*\d+(?:\.\d+)?\s*,", f"Box({val},", code)

        # 3. Check for width / Y modifications
        if ("width" in p or "wide" in p) and nums:
            val = nums[0]
            params["width_mm"] = val
            if re.search(r"width\s*=\s*\d+(?:\.\d+)?", code):
                code = re.sub(r"width\s*=\s*\d+(?:\.\d+)?", f"width = {val}", code)
            else:
                code = re.sub(r"(bd\.Box\s*\(\s*[^,]+\s*,\s*)\d+(?:\.\d+)?", rf"\g<1>{val}", code)
                code = re.sub(r"(Box\s*\(\s*[^,]+\s*,\s*)\d+(?:\.\d+)?", rf"\g<1>{val}", code)

        # 4. Check for height / thickness / Z modifications
        if ("height" in p or "thick" in p or "depth" in p) and nums:
            val = nums[0]
            params["height_mm"] = val
            if re.search(r"(?:height|thickness)\s*=\s*\d+(?:\.\d+)?", code):
                code = re.sub(r"(?:height|thickness)\s*=\s*\d+(?:\.\d+)?", f"height = {val}", code)
            else:
                code = re.sub(r"(bd\.Box\s*\(\s*[^,]+,\s*[^,]+,\s*)\d+(?:\.\d+)?", rf"\g<1>{val}", code)
                code = re.sub(r"(Box\s*\(\s*[^,]+,\s*[^,]+,\s*)\d+(?:\.\d+)?", rf"\g<1>{val}", code)

        # 5. Check for cylinder diameter / radius
        if ("diameter" in p or "radius" in p) and nums and "hole" not in p:
            val = nums[0]
            r = val / 2.0 if ("diameter" in p or "dia" in p) else val
            params["radius_mm"] = r
            params["diameter_mm"] = r * 2.0
            code = re.sub(r"radius\s*=\s*\d+(?:\.\d+)?", f"radius={r}", code)
            code = re.sub(r"Cylinder\s*\(\s*\d+(?:\.\d+)?", f"Cylinder({r}", code)

        # 6. Check for hole additions or diameter modifications
        if "hole" in p and nums:
            hole_dia = nums[0]
            hole_radius = hole_dia / 2.0
            params["hole_diameter_mm"] = hole_dia

            # Check if this is an update to an existing hole
            is_update = ("increase" in p or "change" in p or "reduce" in p or "modify" in p or "set" in p) and ("Circle" in code)
            if is_update:
                code = re.sub(r"Circle\s*\(\s*radius\s*=\s*\d+(?:\.\d+)?\s*\)", f"Circle(radius={hole_radius})", code)
                code = re.sub(r"bd\.Circle\s*\(\s*radius\s*=\s*\d+(?:\.\d+)?\s*\)", f"bd.Circle(radius={hole_radius})", code)
                code = re.sub(r"hole_radius\s*=\s*\d+(?:\.\d+)?", f"hole_radius = {hole_radius}", code)
                code = re.sub(r"hole_r\s*=\s*\d+(?:\.\d+)?", f"hole_r = {hole_radius}", code)
            else:
                # Add new hole feature
                hole_snippet = f"""
    # Feature: Through Hole (Ø{hole_dia} mm)
    with bd.BuildSketch(bd.Plane.XY):
        bd.Circle(radius={hole_radius})
    bd.extrude(amount=200.0, both=True, mode=bd.Mode.SUBTRACT)
"""
                if "model =" in code:
                    code = code.replace("model =", f"{hole_snippet}\nmodel =")
                else:
                    code += f"\n{hole_snippet}\nmodel = part.part\n"

        # 7. Check for fillet / round addition
        if ("fillet" in p or "round" in p) and nums:
            fillet_r = nums[0]
            params["fillet_mm"] = fillet_r
            fillet_snippet = f"""
    # Feature: Corner Fillets ({fillet_r} mm)
    try:
        vert_edges = part.edges().filter_by(bd.Axis.Z)
        if vert_edges:
            bd.fillet(vert_edges, radius={fillet_r})
    except Exception:
        pass
"""
            if "model =" in code:
                code = code.replace("model =", f"{fillet_snippet}\nmodel =")
            else:
                code += f"\n{fillet_snippet}\nmodel = part.part\n"

        # Clean and normalize script indentation
        code = ParametricModifier.clean_script(code)

        plan = CADPlan(
            tool="build123d.script",
            shape_type="modified_solid",
            parameters=params,
            explanation=explanation,
            python_script=code
        )
        return code, plan

    @staticmethod
    def clean_script(code: str) -> str:
        if not code or not code.strip():
            return code

        c = code.strip()
        if c.startswith("```python"):
            c = c[len("```python"):].strip()
        elif c.startswith("```"):
            c = c[len("```"):].strip()
        if c.endswith("```"):
            c = c[:-3].strip()

        # If already syntactically valid, return cleanly
        try:
            compile(c, "<string>", "exec")
            return c
        except (SyntaxError, IndentationError):
            pass

        # If compilation failed, reconstruct indentation using block logic
        lines = c.split("\n")
        fixed_lines = []
        indent = 0
        for line in lines:
            s = line.strip()
            if not s:
                continue
            if s.startswith(("elif ", "else:", "except", "finally:")):
                lvl = max(0, indent - 1)
            else:
                lvl = indent
            fixed_lines.append("    " * lvl + s)
            if s.endswith(":"):
                indent = lvl + 1

        rebuilt = "\n".join(fixed_lines)
        if "import build123d" not in rebuilt and "import bd" not in rebuilt:
            rebuilt = "import math\nimport build123d as bd\n\n" + rebuilt
        if "model =" not in rebuilt and "part" in rebuilt:
            rebuilt += "\nmodel = part.part if hasattr(part, 'part') else part\n"

        try:
            compile(rebuilt, "<string>", "exec")
            return rebuilt
        except Exception:
            return code

class LLMClient:
    def __init__(self):
        self.api_base = settings.VLLM_API_BASE.rstrip("/")
        self.model = settings.VLLM_MODEL
        self.candidate_endpoints = [self.api_base] + [ep.rstrip("/") for ep in settings.FALLBACK_VLLM_ENDPOINTS if ep.rstrip("/") != self.api_base]

    async def generate_cad_code(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[CADPlan, str]:
        """
        Invokes local AI model to reason about mechanical requirements and synthesize/modify
        a parametric build123d Python script.
        """
        user_content = prompt
        sys_prompt = GEMMA_CAD_SYSTEM_PROMPT

        prev_code = ""
        prev_prompt = ""
        if context:
            prev_prompt = context.get("previous_prompt", "")
            prev_code = context.get("previous_code", "")

        p_lower = prompt.lower().strip()
        is_new_design = p_lower.startswith(("create", "generate", "build a new", "design", "make a new"))
        is_mod = bool(
            prev_code
            and not is_new_design
            and (ParametricModifier.is_modification_request(prompt) or (context and context.get("force_modification")))
        )

        if is_mod:
            sys_prompt = MODIFICATION_SYSTEM_PROMPT
            user_content = f"""PREVIOUS CAD DESIGN:
Prompt: "{prev_prompt}"
Previous Working Python Script:
```python
{prev_code}
```

USER MODIFICATION REQUEST:
"{prompt}"

Please modify and update the existing Python script so that the requested changes are accurately applied while preserving all other geometry."""

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_content}
        ]

        raw_response = await self._call_vllm(messages)
        plan, py_code = self._parse_llm_cad_response(raw_response, prompt)

        # If LLM didn't return valid code or this was a modification request that needs fallback
        if not py_code or ("BuildPart" not in py_code and "bd." not in py_code):
            if is_mod:
                logger.info(f"Applying parametric modifier for prompt: '{prompt}'")
                py_code, plan = ParametricModifier.modify_script(prev_code, prompt)
            else:
                py_code, plan = self._synthesize_fallback_script(prompt)

        return plan, py_code

    async def repair_cad_code(
        self,
        prompt: str,
        failed_code: str,
        error_traceback: str
    ) -> Tuple[CADPlan, str]:
        """
        Sends the failed CAD script and OpenCascade traceback back to the LLM
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

    async def _call_vllm(self, messages: List[Dict[str, str]], timeout: float = 30.0) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.15,
            "max_tokens": 1500
        }

        for endpoint in self.candidate_endpoints:
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(
                        f"{endpoint}/chat/completions",
                        json=payload,
                        headers={"Content-Type": "application/json"}
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        choice = data["choices"][0]["message"]
                        content = choice.get("content", "")
                        # Handle models that put output in reasoning
                        if not content and "reasoning" in choice:
                            content = choice["reasoning"]
                        elif "reasoning" in choice and "```python" in choice["reasoning"] and "```python" not in content:
                            content = choice["reasoning"]

                        if content:
                            logger.info(f"AI inference response received from {endpoint} ({len(content)} chars)")
                            return content
            except Exception as e:
                logger.debug(f"Endpoint {endpoint} failed ({e}), trying next candidate...")

        logger.warning("All configured LLM endpoints were unreachable or timed out; using deterministic synthesizer.")
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

        if raw_text:
            # 1. Try parsing JSON
            try:
                json_match = re.search(r"\{[\s\S]*\}", raw_text)
                if json_match:
                    data = json.loads(json_match.group(0))
                    explanation = data.get("explanation", explanation)
                    parameters = data.get("parameters", parameters)
                    shape_type = data.get("shape_type", shape_type)
                    py_code = data.get("python_code", "")
            except Exception:
                pass

            # 2. Extract python code block if not in JSON
            if not py_code:
                code_match = re.search(r"```(?:python|py)?\s*([\s\S]*?)\s*```", raw_text)
                if code_match:
                    py_code = code_match.group(1).strip()

        if py_code and ("BuildPart" in py_code or "BuildSketch" in py_code or "bd." in py_code):
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

        return CADPlan(tool=tool, shape_type="fallback", explanation=explanation), ""

    def _synthesize_fallback_script(self, prompt: str) -> Tuple[str, CADPlan]:
        """
        Robust dynamic CAD script synthesizer for when LLM is offline.
        """
        p = prompt.lower().strip()
        dims_3d = re.findall(r"(\d+(?:\.\d+)?)\s*(?:mm|cm|in|m)?\s*[x×*]\s*(\d+(?:\.\d+)?)\s*(?:mm|cm|in|m)?\s*[x×*]\s*(\d+(?:\.\d+)?)\s*(mm|cm|in|m)?", p)
        all_nums = ParametricModifier.parse_units_in_text(p)
        if not all_nums:
            all_nums = [float(x) for x in re.findall(r"\b\d+(?:\.\d+)?\b", p)]

        # Conveyor bracket / Bracket with slots
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

    # 6 M8 Mounting holes
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

    # Corner Fillets
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
                explanation=f"Conveyor bracket ({l}x{w}x{h}mm) with 6 holes, 2 slots, and corner fillets."
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
                explanation=f"{teeth}-tooth sprocket (Ø{od}mm OD, {thk}mm thick, Ø{bore}mm bore)."
            )
            return code, plan

        # Cylinder / Shaft
        if ("cylinder" in p or "shaft" in p or "rod" in p) and "bracket" not in p:
            dia = all_nums[0] if len(all_nums) > 0 else 30.0
            h = all_nums[1] if len(all_nums) > 1 else 60.0
            code = f"""# Parametric Cylinder Solid
import build123d as bd

with bd.BuildPart() as part:
    bd.Cylinder(radius={dia / 2.0}, height={h})

model = part.part
"""
            plan = CADPlan(
                tool="inventor.create_cylinder",
                shape_type="cylinder",
                diameter_mm=dia,
                height_mm=h,
                parameters={"diameter_mm": dia, "height_mm": h},
                explanation=f"Cylinder (Ø{dia}mm x {h}mm)."
            )
            return code, plan

        # Default Prismatic Box / Cube
        if "cube" in p and all_nums:
            size = all_nums[0]
            l, w, h = size, size, size
        else:
            l = float(dims_3d[0][0]) if dims_3d else (all_nums[0] if len(all_nums) > 0 else 100.0)
            w = float(dims_3d[0][1]) if dims_3d else (all_nums[1] if len(all_nums) > 1 else (l if "cube" in p else 60.0))
            h = float(dims_3d[0][2]) if dims_3d else (all_nums[2] if len(all_nums) > 2 else (l if "cube" in p else 20.0))

        holes_snippet = ""
        holes_def = []
        if "hole" in p:
            h_dia = 8.0
            for n in all_nums:
                if n not in (l, w, h) and n < min(l, w):
                    h_dia = n
                    break
            if "four" in p or "4" in p or "corner" in p:
                off_x = min(15.0, l * 0.15)
                off_y = min(12.0, w * 0.15)
                hx = (l / 2.0) - off_x
                hy = (w / 2.0) - off_y
                holes_snippet = f"""
    # 4 Corner Through Holes (Ø{h_dia} mm)
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations([({hx}, {hy}), ({hx}, -{hy}), (-{hx}, {hy}), (-{hx}, -{hy})]):
            bd.Circle(radius={h_dia / 2.0})
    bd.extrude(amount={h * 2.0}, both=True, mode=bd.Mode.SUBTRACT)
"""
                holes_def.append(HoleDefinition(diameter_mm=h_dia, pattern_type="grid_4_corners", count=4, edge_offset_x_mm=off_x, edge_offset_y_mm=off_y))
            else:
                holes_snippet = f"""
    # Center Through Hole (Ø{h_dia} mm)
    with bd.BuildSketch(bd.Plane.XY):
        bd.Circle(radius={h_dia / 2.0})
    bd.extrude(amount={h * 2.0}, both=True, mode=bd.Mode.SUBTRACT)
"""
                holes_def.append(HoleDefinition(diameter_mm=h_dia, pattern_type="single", count=1))

        code = f"""# Parametric Prismatic CAD Block
import build123d as bd

with bd.BuildPart() as part:
    bd.Box({l}, {w}, {h})
{holes_snippet}
model = part.part
"""
        plan = CADPlan(
            tool="inventor.create_box",
            shape_type="box_with_holes" if holes_def else "box",
            length_mm=l,
            width_mm=w,
            height_mm=h,
            holes=holes_def,
            parameters={"length_mm": l, "width_mm": w, "height_mm": h, "hole_count": len(holes_def)},
            explanation=f"Prismatic solid ({l}x{w}x{h}mm)" + (f" with holes" if holes_def else ".")
        )
        return code, plan

llm_client = LLMClient()
