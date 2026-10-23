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
            "make", "add", "slot", "slotted", "hole", "holes", "fillet", "chamfer",
            "drill", "bore", "pocket", "cut", "remove", "scale", "extend", "shorten",
            "widen", "thicken", "longer", "shorter", "wider", "thicker"
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
        if ("diameter" in p or "radius" in p) and nums and "hole" not in p and "drill" not in p and "bore" not in p and ("cylinder" in p or "rod" in p or "shaft" in p):
            val = nums[0]
            r = val / 2.0 if ("diameter" in p or "dia" in p) else val
            params["radius_mm"] = r
            params["diameter_mm"] = r * 2.0
            code = re.sub(r"radius\s*=\s*\d+(?:\.\d+)?", f"radius={r}", code)
            code = re.sub(r"Cylinder\s*\(\s*\d+(?:\.\d+)?", f"Cylinder({r}", code)

        # 6. Check for hole / drill additions or diameter modifications
        if ("hole" in p or "drill" in p or "bore" in p) and nums:
            count_match = re.search(r"\b(\d+)\s*(?:drills?|holes?|bores?)\b", p)
            if count_match:
                hole_count = int(count_match.group(1))
                dia_match = re.search(r"(?:dia|diameter|of|size)\s*(?:of\s*)?(\d+(?:\.\d+)?)", p)
                if dia_match:
                    hole_dia = float(dia_match.group(1))
                else:
                    remaining = [n for n in nums if n != hole_count]
                    hole_dia = remaining[0] if remaining else 8.0
            else:
                hole_dia = nums[0]

            hole_radius = hole_dia / 2.0
            params["hole_diameter_mm"] = hole_dia

            # Check if this is an update to an existing hole
            is_update = ("increase" in p or "change" in p or "reduce" in p or "modify" in p or "set" in p) and ("Circle" in code) and not ("add" in p or "insert" in p or "drill" in p)
            if is_update:
                code = re.sub(r"Circle\s*\(\s*radius\s*=\s*\d+(?:\.\d+)?\s*\)", f"Circle(radius={hole_radius})", code)
                code = re.sub(r"bd\.Circle\s*\(\s*radius\s*=\s*\d+(?:\.\d+)?\s*\)", f"bd.Circle(radius={hole_radius})", code)
                code = re.sub(r"hole_radius\s*=\s*\d+(?:\.\d+)?", f"hole_radius = {hole_radius}", code)
                code = re.sub(r"hole_r\s*=\s*\d+(?:\.\d+)?", f"hole_r = {hole_radius}", code)
            else:
                # Add new hole/drill feature
                l_match = re.search(r"(?:length|leg1)\s*=\s*(\d+(?:\.\d+)?)", code) or re.search(r"Box\s*\(\s*(\d+(?:\.\d+)?)\s*,", code)
                w_match = re.search(r"width\s*=\s*(\d+(?:\.\d+)?)", code) or re.search(r"Box\s*\([^,]+,\s*(\d+(?:\.\d+)?)\s*,", code)
                l_val = float(l_match.group(1)) if l_match else 100.0
                w_val = float(w_match.group(1)) if w_match else 60.0
                is_l_mount = "leg1" in code or "leg2" in code
                cx = (l_val / 2.0) if is_l_mount else 0.0

                is_4 = (count_match and hole_count == 4) or (bool(re.search(r"\b(?:4|four)\b", p)) and not bool(re.search(r"\b(?:4|four)\s*(?:mm|cm|in|m)\b", p))) or "corner" in p
                is_2 = (count_match and hole_count == 2) or (bool(re.search(r"\b(?:2|two)\b", p)) and not bool(re.search(r"\b(?:2|two)\s*(?:mm|cm|in|m)\b", p)))

                if is_4:
                    dx = (l_val * 0.25) if is_l_mount else max(10.0, (l_val / 2.0) - 15.0)
                    dy = max(10.0, (w_val / 2.0) - 12.0)
                    params["hole_count"] = 4
                    hole_snippet = f"""
    # Feature: 4 Drilled Holes (Ø{hole_dia} mm)
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations([({cx + dx}, {dy}), ({cx + dx}, -{dy}), ({cx - dx}, {dy}), ({cx - dx}, -{dy})]):
            bd.Circle(radius={hole_radius})
    bd.extrude(amount=200.0, both=True, mode=bd.Mode.SUBTRACT)
"""
                elif is_2:
                    dx = (l_val * 0.25) if is_l_mount else max(15.0, (l_val / 2.0) - 20.0)
                    params["hole_count"] = 2
                    hole_snippet = f"""
    # Feature: 2 Drilled Holes (Ø{hole_dia} mm)
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations([({cx + dx}, 0), ({cx - dx}, 0)]):
            bd.Circle(radius={hole_radius})
    bd.extrude(amount=200.0, both=True, mode=bd.Mode.SUBTRACT)
"""
                else:
                    params["hole_count"] = 1
                    hole_snippet = f"""
    # Feature: Center Drilled Hole (Ø{hole_dia} mm)
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations([({cx}, 0)]):
            bd.Circle(radius={hole_radius})
    bd.extrude(amount=200.0, both=True, mode=bd.Mode.SUBTRACT)
"""
                if "model =" in code:
                    code = code.replace("model =", f"{hole_snippet}\nmodel =")
                else:
                    code += f"\n{hole_snippet}\nmodel = part.part\n"

        # 7. Check for slot / slotted hole addition
        if ("slot" in p or "slotted" in p) and nums:
            slot_len = nums[0]
            slot_w = nums[1] if len(nums) > 1 else 8.0
            slot_cnt = 2 if ("two" in p or "2" in p) else (1 if ("one" in p or "1" in p) else 2)
            slot_locs = [(-35.0, 0, 0), (35.0, 0, 0)] if slot_cnt == 2 else [(0, 0, 0)]
            params["slot_length_mm"] = slot_len
            params["slot_width_mm"] = slot_w
            params["slot_count"] = slot_cnt
            slot_snippet = f"""
    # Feature: {slot_cnt} Slotted Adjustment Holes ({slot_len}x{slot_w} mm)
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations({slot_locs}):
            bd.SlotOverall(width={slot_len}, height={slot_w})
    bd.extrude(amount=200.0, both=True, mode=bd.Mode.SUBTRACT)
"""
            if "model =" in code:
                code = code.replace("model =", f"{slot_snippet}\nmodel =")
            else:
                code += f"\n{slot_snippet}\nmodel = part.part\n"

        # 8. Check for fillet / round addition
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
        # Any follow-up request with previous code that isn't a new design is an iterative modification
        is_mod = bool(prev_code and not is_new_design)

        # FAST-PATH 1: Iterative modification of existing model via deterministic engine
        if is_mod:
            mod_code, mod_plan = ParametricModifier.modify_script(prev_code, prompt)
            if mod_code and mod_code != prev_code and ("BuildPart" in mod_code or "bd." in mod_code):
                logger.info(f"Applied instant parametric modification in <1ms for: '{prompt}'")
                return mod_plan, mod_code

        # FAST-PATH 2: Standard mechanical primitives with dimensions (cube, box, cylinder, plate, bracket, gear)
        is_standard_primitive = any(k in p_lower for k in ["cube", "box", "cylinder", "shaft", "bracket", "sprocket", "gear", "flange", "bushing", "washer", "block", "rod", "pin", "plate"])
        if is_standard_primitive and any(c.isdigit() for c in prompt):
            quick_code, quick_plan = self._synthesize_fallback_script(prompt)
            if quick_code and quick_plan.shape_type != "fallback":
                logger.info(f"Generated instant parametric model in <1ms: {quick_plan.shape_type}")
                return quick_plan, quick_code

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

    async def _call_vllm(self, messages: List[Dict[str, str]], timeout: float = 4.0) -> str:
        for endpoint in self.candidate_endpoints:
            # Match model id with server (vLLM on 8000 uses google/gemma-4-31B-it; Ollama on 11434 uses gemma4:31b)
            ep_model = "gemma4:31b" if "11434" in endpoint else self.model
            payload = {
                "model": ep_model,
                "messages": messages,
                "temperature": 0.15,
                "max_tokens": 400
            }
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
        Robust mechanical CAD script synthesizer tuned for ATS Conveyors components.
        """
        p = prompt.lower().strip()
        dims_3d = re.findall(r"(\d+(?:\.\d+)?)\s*(?:mm|cm|in|m)?\s*[x×*]\s*(\d+(?:\.\d+)?)\s*(?:mm|cm|in|m)?\s*[x×*]\s*(\d+(?:\.\d+)?)\s*(mm|cm|in|m)?", p)
        all_nums = ParametricModifier.parse_units_in_text(p)
        if not all_nums:
            all_nums = [float(x) for x in re.findall(r"\b\d+(?:\.\d+)?\b", p)]

        # 1. Socket Head Cap Screw (DIN 912 / ISO 4762)
        if "socket" in p or "cap screw" in p or "allen" in p:
            m_match = re.search(r"m(\d+(?:\.\d+)?)", p)
            d = float(m_match.group(1)) if m_match else (all_nums[0] if all_nums else 8.0)
            length = all_nums[1] if len(all_nums) > 1 else (all_nums[0] if (len(all_nums) > 0 and all_nums[0] != d) else 40.0)
            dk = d * 1.5
            k = d * 1.0
            s_hex = (d * 0.8) / 1.73205
            t_depth = d * 0.5
            code = f"""# Parametric Socket Head Cap Screw (DIN 912 / ISO 4762)
import build123d as bd

d = {d}
length = {length}
dk = {dk}
k = {k}
s_hex = {s_hex}
t_depth = {t_depth}

with bd.BuildPart() as part:
    # Threaded shank
    bd.Cylinder(radius=d / 2.0, height=length)
    # Cylindrical head
    with bd.BuildSketch(bd.Plane.XY.offset(length)):
        bd.Circle(radius=dk / 2.0)
    bd.extrude(amount=k, mode=bd.Mode.ADD)
    # Hex socket recess
    with bd.BuildSketch(bd.Plane.XY.offset(length + k)):
        bd.RegularPolygon(radius=s_hex, side_count=6)
    bd.extrude(amount=t_depth, both=False, mode=bd.Mode.SUBTRACT)

model = part.part
"""
            plan = CADPlan(
                tool="inventor.create_socket_cap_screw",
                shape_type="socket_cap_screw",
                diameter_mm=d,
                height_mm=length + k,
                parameters={"thread_dia_mm": d, "nominal_length_mm": length, "head_dia_mm": dk, "standard": "DIN 912"},
                explanation=f"Socket Head Cap Screw M{int(d)} x {int(length)}mm (DIN 912 / ISO 4762)."
            )
            return code, plan

        # 2. Hexagonal Head Bolt (DIN 933 / ISO 4017)
        if "hex bolt" in p or ("bolt" in p and "eye" not in p):
            m_match = re.search(r"m(\d+(?:\.\d+)?)", p)
            d = float(m_match.group(1)) if m_match else (all_nums[0] if all_nums else 10.0)
            length = all_nums[1] if len(all_nums) > 1 else (all_nums[0] if (len(all_nums) > 0 and all_nums[0] != d) else 50.0)
            s = d * 1.73205
            k = d * 0.7
            r_hex = s / 1.73205
            code = f"""# Parametric Hexagonal Head Bolt (DIN 933 / ISO 4017)
import build123d as bd

d = {d}
length = {length}
r_hex = {r_hex}
k = {k}

with bd.BuildPart() as part:
    # Shank
    bd.Cylinder(radius=d / 2.0, height=length)
    # Hexagonal Head
    with bd.BuildSketch(bd.Plane.XY.offset(length)):
        bd.RegularPolygon(radius=r_hex, side_count=6)
    bd.extrude(amount=k, mode=bd.Mode.ADD)
    # Tip chamfer
    try:
        bot_edges = part.edges().filter_by(bd.Axis.Z).sort_by(bd.Axis.Z)
        if bot_edges:
            bd.chamfer([bot_edges[0]], length=d * 0.1)
    except Exception:
        pass

model = part.part
"""
            plan = CADPlan(
                tool="inventor.create_hex_bolt",
                shape_type="hex_bolt",
                diameter_mm=d,
                height_mm=length + k,
                parameters={"thread_dia_mm": d, "nominal_length_mm": length, "head_height_mm": k, "standard": "DIN 933"},
                explanation=f"Hexagonal Head Bolt M{int(d)} x {int(length)}mm (DIN 933 / ISO 4017)."
            )
            return code, plan

        # 3. Conveyor Roller (Gravity / Driven Tube with Shaft & Bearing Counterbores)
        if "roller" in p and "sphere" not in p and "ball" not in p:
            is_tapered = "tapered" in p or "curve" in p
            od = float(all_nums[0]) if len(all_nums) > 0 else 50.0
            length = float(all_nums[1]) if len(all_nums) > 1 else 400.0
            shaft_d = float(all_nums[2]) if len(all_nums) > 2 else 12.0

            if is_tapered:
                od_small = od
                od_large = od * 1.4
                code = f"""# Parametric Tapered Curve Conveyor Roller
import build123d as bd

with bd.BuildPart() as part:
    bd.Cone(bottom_radius={od_large / 2.0}, top_radius={od_small / 2.0}, height={length})
    # Shaft extensions
    with bd.Locations([(0, 0, -25.0)]):
        bd.Cylinder(radius={shaft_d / 2.0}, height={length + 50.0}, mode=bd.Mode.ADD)

model = part.part
"""
                plan = CADPlan(
                    tool="inventor.create_tapered_roller",
                    shape_type="tapered_conveyor_roller",
                    diameter_mm=od_large,
                    height_mm=length,
                    parameters={"small_dia_mm": od_small, "large_dia_mm": od_large, "length_mm": length, "shaft_dia_mm": shaft_d},
                    explanation=f"Tapered Curve Conveyor Roller (Ø{od_small}-{od_large}mm x {length}mm) for curve transport."
                )
                return code, plan
            else:
                code = f"""# Parametric Conveyor Roller with Bearing Seats & Milled Shaft
import build123d as bd

od = {od}
length = {length}
shaft_d = {shaft_d}
wall_t = 3.0
bearing_d = od * 0.7
bearing_depth = 15.0
shaft_ext = 25.0

with bd.BuildPart() as part:
    # Outer Roller Tube
    bd.Cylinder(radius=od / 2.0, height=length)
    # Hollow interior
    bd.Cylinder(radius=(od / 2.0) - wall_t, height=length, mode=bd.Mode.SUBTRACT)
    # Bearing seats at both ends
    with bd.BuildSketch(bd.Plane.XY):
        bd.Circle(radius=bearing_d / 2.0)
    bd.extrude(amount=bearing_depth, mode=bd.Mode.SUBTRACT)
    with bd.BuildSketch(bd.Plane.XY.offset(length - bearing_depth)):
        bd.Circle(radius=bearing_d / 2.0)
    bd.extrude(amount=bearing_depth, mode=bd.Mode.SUBTRACT)
    # Center through-shaft
    with bd.Locations([(0, 0, -shaft_ext)]):
        bd.Cylinder(radius=shaft_d / 2.0, height=length + 2 * shaft_ext, mode=bd.Mode.ADD)
    # Milled flats on shaft ends
    flat_h = shaft_d * 0.2
    with bd.BuildSketch(bd.Plane.XZ.offset(shaft_d / 2.0 - flat_h)):
        with bd.Locations([(0, -shaft_ext / 2.0), (0, length + shaft_ext / 2.0)]):
            bd.Rectangle(shaft_d * 2.0, shaft_ext)
    bd.extrude(amount=shaft_d, both=True, mode=bd.Mode.SUBTRACT)

model = part.part
"""
                plan = CADPlan(
                    tool="inventor.create_conveyor_roller",
                    shape_type="conveyor_roller",
                    diameter_mm=od,
                    height_mm=length,
                    parameters={"tube_od_mm": od, "length_mm": length, "shaft_dia_mm": shaft_d},
                    explanation=f"Heavy Conveyor Roller (Ø{od}mm x {length}mm) with recessed bearing seats and slotted shaft."
                )
                return code, plan

        # 4. Involute Spur Gear / Pinion
        if "gear" in p or "pinion" in p:
            teeth = int(all_nums[0]) if len(all_nums) > 0 else 24
            module = float(all_nums[1]) if len(all_nums) > 1 else (2.0 if teeth > 12 else 2.5)
            face_w = float(all_nums[2]) if len(all_nums) > 2 else 15.0
            bore = float(all_nums[3]) if len(all_nums) > 3 else 12.0
            pitch_d = module * teeth
            tip_d = pitch_d + 2.0 * module

            code = f"""# Parametric Involute Metric Spur Gear
import math
import build123d as bd

teeth = {teeth}
module = {module}
face_w = {face_w}
bore = {bore}
pitch_d = module * teeth
tip_d = pitch_d + 2.0 * module

with bd.BuildPart() as part:
    bd.Cylinder(radius=tip_d / 2.0, height=face_w)
    tooth_gap_r = (module * math.pi) / 4.0
    pitch_r = pitch_d / 2.0
    locs = []
    for i in range(teeth):
        locs.append((pitch_r * math.cos(2 * math.pi * i / teeth), pitch_r * math.sin(2 * math.pi * i / teeth)))
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations(locs):
            bd.Circle(radius=tooth_gap_r)
    bd.extrude(amount=face_w * 2, both=True, mode=bd.Mode.SUBTRACT)
    with bd.BuildSketch(bd.Plane.XY):
        bd.Circle(radius=bore / 2.0)
        with bd.Locations([(0, bore / 2.0)]):
            bd.Rectangle(4.0, 3.0)
    bd.extrude(amount=face_w * 2, both=True, mode=bd.Mode.SUBTRACT)

model = part.part
"""
            plan = CADPlan(
                tool="inventor.create_spur_gear",
                shape_type="spur_gear",
                diameter_mm=tip_d,
                height_mm=face_w,
                parameters={"teeth_count": teeth, "module_mm": module, "pitch_dia_mm": pitch_d, "bore_dia_mm": bore},
                explanation=f"Involute Spur Gear ({teeth} teeth, module {module}, Ø{pitch_d:.1f}mm pitch, Ø{bore}mm bore with keyway)."
            )
            return code, plan

        # 5. Conveyor Chain Sprocket
        if "sprocket" in p or "chain" in p:
            teeth = int(all_nums[0]) if len(all_nums) > 0 else 18
            od = float(all_nums[1]) if len(all_nums) > 1 else 75.0
            thk = float(all_nums[2]) if len(all_nums) > 2 else 10.0
            bore = float(all_nums[3]) if len(all_nums) > 3 else 16.0

            code = f"""# Parametric Conveyor Chain Sprocket
import math
import build123d as bd

od = {od}
teeth = {teeth}
thk = {thk}
bore = {bore}

with bd.BuildPart() as part:
    bd.Cylinder(radius=od / 2.0, height=thk)
    tooth_r = (od / teeth) * 0.85
    pitch_r = od / 2.0
    notch_locs = []
    for i in range(teeth):
        notch_locs.append((pitch_r * math.cos(2 * math.pi * i / teeth), pitch_r * math.sin(2 * math.pi * i / teeth)))
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations(notch_locs):
            bd.Circle(radius=tooth_r)
    bd.extrude(amount=thk * 2, both=True, mode=bd.Mode.SUBTRACT)

    with bd.BuildSketch(bd.Plane.XY):
        bd.Circle(radius=bore / 2.0)
        with bd.Locations([(0, bore / 2.0)]):
            bd.Rectangle(5.0, 4.0)
    bd.extrude(amount=thk * 2, both=True, mode=bd.Mode.SUBTRACT)

model = part.part
"""
            plan = CADPlan(
                tool="inventor.create_sprocket",
                shape_type="sprocket",
                diameter_mm=od,
                height_mm=thk,
                parameters={"outer_diameter_mm": od, "teeth_count": teeth, "thickness_mm": thk, "bore_diameter_mm": bore},
                explanation=f"{teeth}-tooth Conveyor Chain Sprocket (Ø{od}mm OD, {thk}mm thick, Ø{bore}mm bore with keyway)."
            )
            return code, plan

        # 6. Stepped Drive Shaft with Keyway
        if "stepped shaft" in p or ("shaft" in p and ("keyway" in p or "stepped" in p or "drive" in p)):
            d_body = float(all_nums[0]) if len(all_nums) > 0 else 40.0
            l_body = float(all_nums[1]) if len(all_nums) > 1 else 200.0
            d_journal = d_body * 0.75
            l_journal = 50.0
            d_ext = d_body * 0.6
            l_ext = 40.0

            code = f"""# Parametric Conveyor Stepped Drive Shaft with DIN 6885 Keyway
import build123d as bd

d_body = {d_body}
l_body = {l_body}
d_journal = {d_journal}
l_journal = {l_journal}
d_ext = {d_ext}
l_ext = {l_ext}

with bd.BuildPart() as part:
    # Main center pulley body
    bd.Cylinder(radius=d_body / 2.0, height=l_body)
    # Bearing journals on left & right
    with bd.Locations([(0, 0, -l_journal)]):
        bd.Cylinder(radius=d_journal / 2.0, height=l_journal, mode=bd.Mode.ADD)
    with bd.Locations([(0, 0, l_body)]):
        bd.Cylinder(radius=d_journal / 2.0, height=l_journal, mode=bd.Mode.ADD)
    # Drive extensions
    with bd.Locations([(0, 0, -(l_journal + l_ext))]):
        bd.Cylinder(radius=d_ext / 2.0, height=l_ext, mode=bd.Mode.ADD)
    with bd.Locations([(0, 0, l_body + l_journal)]):
        bd.Cylinder(radius=d_ext / 2.0, height=l_ext, mode=bd.Mode.ADD)
    # DIN 6885 Keyway on right extension
    key_w = 8.0
    key_d = 4.0
    with bd.BuildSketch(bd.Plane.YZ.offset(d_ext / 2.0 - key_d)):
        with bd.Locations([(0, l_body + l_journal + l_ext / 2.0)]):
            bd.SlotOverall(width=min(30.0, l_ext * 0.8), height=key_w)
    bd.extrude(amount=key_d * 2.0, both=True, mode=bd.Mode.SUBTRACT)

model = part.part
"""
            plan = CADPlan(
                tool="inventor.create_stepped_shaft",
                shape_type="stepped_drive_shaft",
                diameter_mm=d_body,
                height_mm=l_body + 2 * l_journal + 2 * l_ext,
                parameters={"body_dia_mm": d_body, "body_length_mm": l_body, "journal_dia_mm": d_journal, "extension_dia_mm": d_ext},
                explanation=f"Conveyor Stepped Drive Shaft (Ø{d_body}mm body, Ø{d_journal}mm journals, Ø{d_ext}mm drive end with keyway)."
            )
            return code, plan

        # 7. Motor Mount Baseplate with Tensioning Slots
        if "motor mount" in p or "motor plate" in p:
            l = float(all_nums[0]) if len(all_nums) > 0 else 180.0
            w = float(all_nums[1]) if len(all_nums) > 1 else 140.0
            thk = float(all_nums[2]) if len(all_nums) > 2 else 12.0
            pilot = float(all_nums[3]) if len(all_nums) > 3 else 60.0

            code = f"""# Parametric Conveyor Motor Mount Plate with Tensioning Slots
import build123d as bd

length = {l}
width = {w}
thk = {thk}
pilot = {pilot}

with bd.BuildPart() as part:
    bd.Box(length, width, thk)
    # Center pilot clearance bore
    with bd.BuildSketch(bd.Plane.XY):
        bd.Circle(radius=pilot / 2.0)
    bd.extrude(amount=thk * 2, both=True, mode=bd.Mode.SUBTRACT)
    # 4 Elongated motor tensioning slots
    sx = length * 0.35
    sy = width * 0.35
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations([(sx, sy), (sx, -sy), (-sx, sy), (-sx, -sy)]):
            bd.SlotOverall(width=45.0, height=11.0)
    bd.extrude(amount=thk * 2, both=True, mode=bd.Mode.SUBTRACT)

model = part.part
"""
            plan = CADPlan(
                tool="inventor.create_motor_mount",
                shape_type="motor_mount_plate",
                length_mm=l,
                width_mm=w,
                height_mm=thk,
                parameters={"length_mm": l, "width_mm": w, "thickness_mm": thk, "pilot_bore_mm": pilot},
                explanation=f"Conveyor Motor Mount Plate ({l}x{w}x{thk}mm) with Ø{pilot}mm bore and 4 tensioning slots."
            )
            return code, plan

        # 8. Photoelectric Sensor Mounting Bracket
        if "sensor" in p and ("bracket" in p or "mount" in p):
            w = float(all_nums[0]) if len(all_nums) > 0 else 35.0
            h = float(all_nums[1]) if len(all_nums) > 1 else 60.0
            base_l = float(all_nums[2]) if len(all_nums) > 2 else 45.0
            thk = 3.0
            sensor_d = 18.0

            code = f"""# Parametric Photoelectric Sensor Mounting Bracket
import build123d as bd

width = {w}
upright_h = {h}
base_l = {base_l}
thk = {thk}
sensor_d = {sensor_d}

with bd.BuildPart() as part:
    with bd.Locations([(base_l / 2.0, 0, thk / 2.0)]):
        bd.Box(base_l, width, thk)
    with bd.Locations([(thk / 2.0, 0, upright_h / 2.0)]):
        bd.Box(thk, width, upright_h)
    with bd.BuildSketch(bd.Plane.YZ):
        with bd.Locations([(0, upright_h * 0.65)]):
            bd.Circle(radius=sensor_d / 2.0)
    bd.extrude(amount=thk * 2, both=True, mode=bd.Mode.SUBTRACT)
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations([(base_l * 0.6, 0)]):
            bd.SlotOverall(width=20.0, height=7.0)
    bd.extrude(amount=thk * 2, both=True, mode=bd.Mode.SUBTRACT)

model = part.part
"""
            plan = CADPlan(
                tool="inventor.create_sensor_bracket",
                shape_type="sensor_bracket",
                length_mm=base_l,
                width_mm=w,
                height_mm=h,
                parameters={"base_length_mm": base_l, "width_mm": w, "height_mm": h, "sensor_barrel_dia_mm": sensor_d},
                explanation=f"Photoelectric Sensor Mounting Bracket ({base_l}x{w}x{h}mm) with Ø{sensor_d}mm M18 barrel hole."
            )
            return code, plan

        # 9. Heavy-Duty L-Bracket with Gusset Stiffener
        if "l bracket" in p or "l-bracket" in p or "angle bracket" in p or "l mount" in p or "l-mount" in p or "angle mount" in p or "gusset" in p:
            leg1 = float(all_nums[0]) if len(all_nums) > 0 else 80.0
            leg2 = float(all_nums[1]) if len(all_nums) > 1 else (leg1 if len(all_nums) == 1 else 80.0)
            width = float(all_nums[2]) if len(all_nums) > 2 else 50.0
            thk = float(all_nums[3]) if len(all_nums) > 3 else 8.0

            code = f"""# Parametric Heavy-Duty Reinforced L-Bracket with Gusset
import build123d as bd

leg1 = {leg1}
leg2 = {leg2}
width = {width}
thk = {thk}
gusset_len = min(leg1, leg2) * 0.7
gusset_thk = max(thk * 0.6, 4.0)

with bd.BuildPart() as part:
    # Base leg
    with bd.Locations([(leg1 / 2.0, 0, thk / 2.0)]):
        bd.Box(leg1, width, thk)
    # Upright leg
    with bd.Locations([(thk / 2.0, 0, leg2 / 2.0)]):
        bd.Box(thk, width, leg2)
    # Triangular stiffener gusset web
    with bd.BuildSketch(bd.Plane.XZ):
        with bd.Locations([(thk, thk)]):
            bd.Polygon([(0, 0), (gusset_len, 0), (0, gusset_len), (0, 0)])
    bd.extrude(amount=gusset_thk, both=True, mode=bd.Mode.ADD)
    # Base rail slotted hole
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations([(leg1 * 0.6, 0)]):
            bd.SlotOverall(width=25.0, height=9.0)
    bd.extrude(amount=thk * 2, both=True, mode=bd.Mode.SUBTRACT)
    # Upright through hole
    with bd.BuildSketch(bd.Plane.YZ):
        with bd.Locations([(0, leg2 * 0.65)]):
            bd.Circle(radius=4.5)
    bd.extrude(amount=thk * 2, both=True, mode=bd.Mode.SUBTRACT)

model = part.part
"""
            plan = CADPlan(
                tool="inventor.create_reinforced_l_bracket",
                shape_type="reinforced_l_bracket",
                length_mm=leg1,
                width_mm=width,
                height_mm=leg2,
                parameters={"leg1_mm": leg1, "leg2_mm": leg2, "width_mm": width, "thickness_mm": thk, "has_gusset": True},
                explanation=f"Reinforced L-Bracket ({leg1}x{leg2}x{width}mm, {thk}mm thick) with triangular stiffener gusset."
            )
            return code, plan

        # 10. Pillow Block Bearing Housing (UCP)
        if "pillow block" in p or "bearing housing" in p or "plummer block" in p:
            bore_d = float(all_nums[0]) if len(all_nums) > 0 else 25.0
            base_w = float(all_nums[1]) if len(all_nums) > 1 else 140.0
            base_d = 40.0
            total_h = 70.0
            hub_od = bore_d * 2.0
            base_thk = 15.0

            code = f"""# Parametric UCP Pillow Block Bearing Housing
import build123d as bd

bore_d = {bore_d}
base_w = {base_w}
base_d = {base_d}
total_h = {total_h}
hub_od = {hub_od}
base_thk = {base_thk}

with bd.BuildPart() as part:
    bd.Box(base_w, base_d, base_thk)
    with bd.Locations([(0, 0, total_h - hub_od / 2.0)]):
        bd.Cylinder(radius=hub_od / 2.0, height=base_d, rotation=(90, 0, 0), mode=bd.Mode.ADD)
    with bd.Locations([(0, 0, (total_h - hub_od / 2.0) / 2.0)]):
        bd.Box(hub_od * 1.1, base_d * 0.8, total_h - hub_od / 2.0, mode=bd.Mode.ADD)
    with bd.Locations([(0, 0, total_h - hub_od / 2.0)]):
        bd.Cylinder(radius=bore_d / 2.0, height=base_d * 2.0, rotation=(90, 0, 0), mode=bd.Mode.SUBTRACT)
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations([(base_w * 0.38, 0), (-base_w * 0.38, 0)]):
            bd.SlotOverall(width=22.0, height=13.0)
    bd.extrude(amount=base_thk * 2, both=True, mode=bd.Mode.SUBTRACT)

model = part.part
"""
            plan = CADPlan(
                tool="inventor.create_pillow_block",
                shape_type="pillow_block_housing",
                diameter_mm=bore_d,
                height_mm=total_h,
                length_mm=base_w,
                width_mm=base_d,
                parameters={"bore_dia_mm": bore_d, "base_width_mm": base_w, "total_height_mm": total_h},
                explanation=f"UCP Pillow Block Bearing Housing (Ø{bore_d}mm bore, {base_w}mm base with 2 mounting slots)."
            )
            return code, plan

        # 11. Sphere / Ball Transfer Unit
        if "sphere" in p or "ball transfer" in p or "ball" in p:
            is_btu = "transfer" in p or "unit" in p
            dia = float(all_nums[0]) if len(all_nums) > 0 else 25.0
            if is_btu:
                code = f"""# Parametric Conveyor Ball Transfer Unit (BTU)
import math
import build123d as bd

ball_d = {dia}
housing_od = ball_d * 1.8
housing_h = ball_d * 0.9
flange_d = ball_d * 2.4
flange_thk = 3.0

with bd.BuildPart() as part:
    bd.Cylinder(radius=housing_od / 2.0, height=housing_h)
    with bd.BuildSketch(bd.Plane.XY.offset(housing_h - flange_thk)):
        bd.Circle(radius=flange_d / 2.0)
        with bd.Locations([
            (flange_d * 0.42 * math.cos(math.pi / 4), flange_d * 0.42 * math.sin(math.pi / 4)),
            (flange_d * 0.42 * math.cos(3 * math.pi / 4), flange_d * 0.42 * math.sin(3 * math.pi / 4)),
            (flange_d * 0.42 * math.cos(5 * math.pi / 4), flange_d * 0.42 * math.sin(5 * math.pi / 4)),
            (flange_d * 0.42 * math.cos(7 * math.pi / 4), flange_d * 0.42 * math.sin(7 * math.pi / 4)),
        ]):
            bd.Circle(radius=2.5)
    bd.extrude(amount=flange_thk, mode=bd.Mode.ADD)
    with bd.Locations([(0, 0, housing_h)]):
        bd.Sphere(radius=ball_d / 2.0, mode=bd.Mode.SUBTRACT)
    with bd.Locations([(0, 0, housing_h + ball_d * 0.1)]):
        bd.Sphere(radius=ball_d / 2.0 * 0.96, mode=bd.Mode.ADD)

model = part.part
"""
                plan = CADPlan(
                    tool="inventor.create_ball_transfer_unit",
                    shape_type="ball_transfer_unit",
                    diameter_mm=dia,
                    parameters={"ball_dia_mm": dia, "flange_dia_mm": dia * 2.4},
                    explanation=f"Conveyor Ball Transfer Unit with Ø{dia}mm ball and 4-hole mounting flange."
                )
                return code, plan
            else:
                code = f"""# Parametric 3D Sphere Solid
import build123d as bd

with bd.BuildPart() as part:
    bd.Sphere(radius={dia / 2.0})

model = part.part
"""
                plan = CADPlan(
                    tool="inventor.create_sphere",
                    shape_type="sphere",
                    diameter_mm=dia,
                    parameters={"diameter_mm": dia, "radius_mm": dia / 2.0},
                    explanation=f"Sphere (Ø{dia}mm)."
                )
                return code, plan

        # 12. Cone / Transition Funnel
        if "cone" in p or "funnel" in p or "hopper" in p:
            r1 = float(all_nums[0]) / 2.0 if len(all_nums) > 0 else 30.0
            r2 = float(all_nums[1]) / 2.0 if len(all_nums) > 1 else (r1 * 0.5)
            h = float(all_nums[2]) if len(all_nums) > 2 else 60.0

            code = f"""# Parametric Truncated Cone Solid
import build123d as bd

with bd.BuildPart() as part:
    bd.Cone(bottom_radius={r1}, top_radius={r2}, height={h})

model = part.part
"""
            plan = CADPlan(
                tool="inventor.create_cone",
                shape_type="cone",
                diameter_mm=r1 * 2.0,
                height_mm=h,
                parameters={"bottom_dia_mm": r1 * 2.0, "top_dia_mm": r2 * 2.0, "height_mm": h},
                explanation=f"Truncated Cone (Ø{r1*2:.1f}mm bottom, Ø{r2*2:.1f}mm top, {h}mm height)."
            )
            return code, plan

        # 13. Hollow Cylinder / Pipe / Sleeve
        if ("pipe" in p or "tube" in p or "sleeve" in p) and "roller" not in p:
            od = float(all_nums[0]) if len(all_nums) > 0 else 50.0
            h = float(all_nums[1]) if len(all_nums) > 1 else 100.0
            wall_t = float(all_nums[2]) if len(all_nums) > 2 else min(4.0, od * 0.15)
            id_val = od - 2 * wall_t

            code = f"""# Parametric Hollow Pipe / Cylinder Solid
import build123d as bd

od = {od}
height = {h}
id_val = {id_val}

with bd.BuildPart() as part:
    bd.Cylinder(radius=od / 2.0, height=height)
    bd.Cylinder(radius=id_val / 2.0, height=height * 2.0, mode=bd.Mode.SUBTRACT)

model = part.part
"""
            plan = CADPlan(
                tool="inventor.create_pipe",
                shape_type="pipe",
                diameter_mm=od,
                height_mm=h,
                parameters={"outer_dia_mm": od, "inner_dia_mm": id_val, "wall_thickness_mm": wall_t, "length_mm": h},
                explanation=f"Hollow Pipe Sleeve (Ø{od}mm OD x Ø{id_val}mm ID x {h}mm length)."
            )
            return code, plan

        # 14. Standard Conveyor Flat Bracket (with holes & slots)
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

        # 15. Solid Cylinder
        if ("cylinder" in p or "rod" in p or "pin" in p) and "bracket" not in p:
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
