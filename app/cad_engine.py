import os
import math
import logging
import traceback
from typing import Dict, Any, Tuple, Optional, List
import build123d as bd
from app.config import settings
from app.schemas import CADPlan, HoleDefinition, CADValidationReport
from app.cad_validator import cad_validator

# Resilient method aliases for LLM-generated build123d scripts
for cls in [bd.BuildPart, bd.BuildSketch]:
    if not hasattr(cls, "extrude"):
        setattr(cls, "extrude", staticmethod(lambda *args, **kwargs: bd.extrude(*args, **kwargs)))
    if not hasattr(cls, "revolve"):
        setattr(cls, "revolve", staticmethod(lambda *args, **kwargs: bd.revolve(*args, **kwargs)))
    if not hasattr(cls, "fillet"):
        setattr(cls, "fillet", staticmethod(lambda *args, **kwargs: bd.fillet(*args, **kwargs)))
    if not hasattr(cls, "chamfer"):
        setattr(cls, "chamfer", staticmethod(lambda *args, **kwargs: bd.chamfer(*args, **kwargs)))

if hasattr(bd, "ShapeList"):
    if not hasattr(bd.ShapeList, "filter_by_length"):
        setattr(bd.ShapeList, "filter_by_length", lambda self, length: [e for e in self if abs(getattr(e, "length", 0) - length) < 1e-2])
    if not hasattr(bd.ShapeList, "filter_by_axis"):
        setattr(bd.ShapeList, "filter_by_axis", lambda self, axis: self.filter_by(axis))

if hasattr(bd, "Vector"):
    if not hasattr(bd.Vector, "x"):
        setattr(bd.Vector, "x", property(lambda self: self.X))
    if not hasattr(bd.Vector, "y"):
        setattr(bd.Vector, "y", property(lambda self: self.Y))
    if not hasattr(bd.Vector, "z"):
        setattr(bd.Vector, "z", property(lambda self: self.Z))

_orig_rect = bd.Rectangle
_orig_circle = bd.Circle
_orig_slot = bd.SlotOverall
_orig_box = bd.Box
_orig_cylinder = bd.Cylinder
_orig_locations = bd.Locations
_orig_location = bd.Location

def _safe_location(*args, **kwargs):
    try:
        if len(args) == 2 and isinstance(args[0], (tuple, list)) and isinstance(args[1], (tuple, list)):
            return _orig_location(args[0], bd.Rotation(*args[1]))
        if len(args) == 3 and all(isinstance(x, (int, float)) for x in args):
            return _orig_location(tuple(args))
        if len(args) == 1 and isinstance(args[0], (tuple, list)) and len(args[0]) == 3:
            return _orig_location(tuple(args[0]))
        return _orig_location(*args, **kwargs)
    except Exception:
        return _orig_location((0, 0, 0))

class _PatchedLocation(_orig_location):
    def __new__(cls, *args, **kwargs):
        return _safe_location(*args, **kwargs)
    def __enter__(self):
        self._cm = _orig_locations([self])
        return self._cm.__enter__()
    def __exit__(self, *args):
        return self._cm.__exit__(*args)
def _patched_rect(width=100.0, length=None, *args, **kwargs):
    h = length if length is not None else kwargs.pop("height", width)
    loc = kwargs.pop("center", kwargs.pop("location", kwargs.pop("pos", None)))
    if loc is not None:
        with _orig_locations([loc]):
            return _orig_rect(width, h, *args, **kwargs)
    return _orig_rect(width, h, *args, **kwargs)

def _patched_circle(radius=None, *args, **kwargs):
    r = radius if radius is not None else kwargs.pop("r", kwargs.pop("radius", 5.0))
    loc = kwargs.pop("center", kwargs.pop("location", kwargs.pop("pos", None)))
    if loc is not None:
        with _orig_locations([loc]):
            return _orig_circle(radius=r, *args, **kwargs)
    return _orig_circle(radius=r, *args, **kwargs)

def _patched_slot(width=40.0, height=8.0, *args, **kwargs):
    w = kwargs.pop("length", width)
    h = kwargs.pop("width", height) if "length" in kwargs else height
    loc = kwargs.pop("center", kwargs.pop("location", kwargs.pop("pos", None)))
    if loc is not None:
        with _orig_locations([loc]):
            return _orig_slot(width=w, height=h, *args, **kwargs)
    return _orig_slot(width=w, height=h, *args, **kwargs)

def _patched_cylinder(radius=10.0, height=20.0, *args, **kwargs):
    kwargs.pop("centered", None)
    kwargs.pop("axis", None)
    kwargs.pop("plane", None)
    if "align" in kwargs and not isinstance(kwargs["align"], (bd.Align, tuple)):
        kwargs.pop("align", None)
    loc = kwargs.pop("center", kwargs.pop("location", kwargs.pop("loc", kwargs.pop("pos", None))))
    if loc is not None:
        with _orig_locations([loc]):
            return _orig_cylinder(radius=radius, height=height, *args, **kwargs)
    return _orig_cylinder(radius=radius, height=height, *args, **kwargs)

def _patched_box(length=100.0, width=60.0, height=20.0, *args, **kwargs):
    kwargs.pop("centered", None)
    kwargs.pop("axis", None)
    kwargs.pop("plane", None)
    if "align" in kwargs and not isinstance(kwargs["align"], (bd.Align, tuple)):
        kwargs.pop("align", None)
    loc = kwargs.pop("center", kwargs.pop("location", kwargs.pop("loc", kwargs.pop("pos", None))))
    if loc is not None:
        with _orig_locations([loc]):
            return _orig_box(length, width, height, *args, **kwargs)
    return _orig_box(length, width, height, *args, **kwargs)

def _patched_locations(*args, **kwargs):
    loc_list = []
    if len(args) == 3 and all(isinstance(x, (int, float)) for x in args):
        loc_list.append(tuple(args))
    elif len(args) == 2 and all(isinstance(x, (int, float)) for x in args):
        loc_list.append((args[0], args[1], 0.0))
    else:
        for a in args:
            if isinstance(a, (_orig_locations, bd.PolarLocations, bd.GridLocations)):
                loc_list.extend(getattr(a, "locations", []))
            elif isinstance(a, bd.Rotation):
                loc_list.append(bd.Location((0, 0, 0), a))
            elif isinstance(a, (list, tuple)):
                if len(a) in (2, 3) and all(isinstance(x, (int, float)) for x in a):
                    loc_list.append(tuple(a) if len(a) == 3 else (a[0], a[1], 0.0))
                else:
                    loc_list.extend(a)
            elif isinstance(a, (int, float)):
                loc_list.append((a, 0.0, 0.0))
            else:
                loc_list.append(a)
    return _orig_locations(loc_list if loc_list else [(0, 0, 0)])

bd.Rectangle = _patched_rect
bd.Circle = _patched_circle
bd.SlotOverall = _patched_slot
bd.Slot = _patched_slot
bd.Box = _patched_box
bd.Cylinder = _patched_cylinder
bd.Locations = _patched_locations
bd.Location = _PatchedLocation

class CADEngine:
    """
    OpenCascade & build123d CAD solid generation engine.
    Transforms high-level structured CAD plans into accurate, topological 3D solids,
    and exports them to ISO-standard STEP (.step) and STL (.stl) files.
    """

    def __init__(self):
        self.export_dir = settings.EXPORT_DIR
        os.makedirs(self.export_dir, exist_ok=True)

    def generate_from_plan(self, plan: CADPlan, output_id: str = "cad_model", export_subfolder: Optional[str] = None) -> Tuple[Any, CADValidationReport]:
        target_dir = os.path.join(self.export_dir, export_subfolder) if export_subfolder else self.export_dir
        os.makedirs(target_dir, exist_ok=True)

        step_path = os.path.join(target_dir, f"{output_id}.step")
        stl_path = os.path.join(target_dir, f"{output_id}.stl")
        glb_path = os.path.join(target_dir, f"{output_id}.glb")
        python_path = os.path.join(target_dir, f"{output_id}.py")

        if plan.python_script:
            solid_obj = self._execute_python_script(plan.python_script)
            py_code = plan.python_script
        elif plan.shape_type in ["box", "box_with_holes"]:
            solid_obj = self._build_box_with_holes(plan)
            py_code = self._generate_box_code(plan)
        elif plan.shape_type == "cylinder":
            solid_obj = self._build_cylinder(plan)
            py_code = self._generate_cylinder_code(plan)
        elif plan.shape_type == "bracket":
            solid_obj = self._build_bracket(plan)
            py_code = self._generate_bracket_code(plan)
        elif plan.shape_type == "valve_body":
            solid_obj = self._build_valve_body(plan)
            py_code = self._generate_valve_code(plan)
        elif plan.shape_type == "compound":
            solid_obj = self._build_compound(plan)
            py_code = self._generate_compound_code(plan)
        elif plan.shape_type == "sprocket":
            solid_obj = self._build_sprocket(plan)
            py_code = self._generate_sprocket_code(plan)
        elif plan.shape_type == "turntable":
            solid_obj = self._build_turntable(plan)
            py_code = self._generate_turntable_code(plan)
        elif plan.shape_type == "prb_conveyor":
            solid_obj = self._build_prb_conveyor(plan)
            py_code = self._generate_conveyor_code(plan)
        else:
            solid_obj = self._build_box_with_holes(plan)
            py_code = self._generate_box_code(plan)

        # 1. Export STEP
        bd.export_step(solid_obj, step_path)

        # 2. Export STL
        try:
            bd.export_stl(solid_obj, stl_path)
        except Exception as e:
            logger.warning(f"STL export warning: {e}")
            stl_path = None

        # 3. Export GLB (for fast browser WebGL CAD rendering)
        try:
            bd.export_gltf(solid_obj, glb_path, binary=True)
        except Exception as e:
            logger.warning(f"GLB export warning: {e}")
            glb_path = None

        # 4. Export Python Script
        try:
            with open(python_path, "w", encoding="utf-8") as f:
                f.write(py_code)
        except Exception as e:
            logger.warning(f"Python script save warning: {e}")
            python_path = None

        # 5. Verify solid geometry & STEP file
        report = cad_validator.validate_solid_and_step(
            solid_obj=solid_obj,
            step_path=step_path,
            stl_path=stl_path,
            glb_path=glb_path,
            python_path=python_path
        )
        return solid_obj, report

    def _generate_box_code(self, plan: CADPlan) -> str:
        length = float(plan.length_mm or plan.parameters.get("length_mm") or 100.0)
        width = float(plan.width_mm or plan.parameters.get("width_mm") or 60.0)
        height = float(plan.height_mm or plan.parameters.get("height_mm") or 20.0)
        
        all_holes = [h for h in plan.holes if h.diameter_mm > 0.0]
        if not all_holes and "hole_diameter_mm" in plan.parameters:
            h_dia = float(plan.parameters.get("hole_diameter_mm", 0.0))
            if h_dia > 0:
                h_cnt = int(plan.parameters.get("hole_count", 1))
                all_holes.append(HoleDefinition(
                    diameter_mm=h_dia,
                    pattern_type="grid_4_corners" if h_cnt == 4 else "single",
                    count=h_cnt,
                    edge_offset_x_mm=plan.parameters.get("edge_offset_x_mm", min(15.0, length * 0.15)),
                    edge_offset_y_mm=plan.parameters.get("edge_offset_y_mm", min(12.0, width * 0.15))
                ))

        code = f"""# ATS Engineering AI — Generated CAD Model
# Description: {plan.explanation}
import build123d as bd

with bd.BuildPart() as part:
    # Base Box ({length} x {width} x {height} mm)
    bd.Box({length}, {width}, {height})
"""
        for hole in all_holes:
            if hole.diameter_mm <= 0: continue
            if hole.pattern_type == "grid_4_corners" or hole.count == 4:
                off_x = hole.edge_offset_x_mm if hole.edge_offset_x_mm is not None else min(15.0, length * 0.15)
                off_y = hole.edge_offset_y_mm if hole.edge_offset_y_mm is not None else min(12.0, width * 0.15)
                hx = (length / 2.0) - off_x
                hy = (width / 2.0) - off_y
                code += f"""
    # 4 Corner Holes (Ø{hole.diameter_mm} mm)
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations([({hx}, {hy}), ({hx}, -{hy}), (-{hx}, {hy}), (-{hx}, -{hy})]):
            bd.Circle(radius={hole.diameter_mm / 2.0})
    bd.extrude(amount={height * 2.0}, both=True, mode=bd.Mode.SUBTRACT)
"""
            else:
                code += f"""
    # Center / Offset Hole (Ø{hole.diameter_mm} mm at ({hole.x_mm}, {hole.y_mm}))
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations([({hole.x_mm}, {hole.y_mm})]):
            bd.Circle(radius={hole.diameter_mm / 2.0})
    bd.extrude(amount={height * 2.0}, both=True, mode=bd.Mode.SUBTRACT)
"""
        code += "\nmodel = part.part\n"
        return code

    def _generate_cylinder_code(self, plan: CADPlan) -> str:
        dia = float(plan.diameter_mm or plan.parameters.get("diameter_mm") or 20.0)
        height = float(plan.height_mm or plan.parameters.get("height_mm") or 50.0)
        bore = float(plan.parameters.get("bore_diameter_mm", 0.0))
        return f"""# ATS Engineering AI — Generated Cylinder
import build123d as bd

with bd.BuildPart() as part:
    bd.Cylinder(radius={dia / 2.0}, height={height})
    {f'''with bd.BuildSketch(bd.Plane.XY):
        bd.Circle(radius={bore / 2.0})
    bd.extrude(amount={height * 2.0}, both=True, mode=bd.Mode.SUBTRACT)''' if bore > 0 else ''}

model = part.part
"""

    def _generate_bracket_code(self, plan: CADPlan) -> str:
        return f"""# ATS Engineering AI — Generated Bracket
import build123d as bd

with bd.BuildPart() as part:
    bd.Box(80, 70, 10)
    with bd.Locations([(35, 0, 22.5)]):
        bd.Box(10, 70, 55)
    with bd.Locations([(0, 0, 13.75)]):
        bd.Box(70, 10, 27.5)
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations([(-20, 17.5), (-20, -17.5)]):
            bd.Circle(radius=5.0)
    bd.extrude(amount=20, both=True, mode=bd.Mode.SUBTRACT)

model = part.part
"""

    def _generate_valve_code(self, plan: CADPlan) -> str:
        return f"""# ATS Engineering AI — Generated Valve Body
import build123d as bd

with bd.BuildPart() as part:
    with bd.Locations([(0, 0, -40)]):
        bd.Box(120, 120, 10)
    bd.Box(80, 80, 70)
    with bd.Locations([(0, 0, 40)]):
        bd.Box(120, 120, 10)
    with bd.BuildSketch(bd.Plane.XY):
        bd.Circle(radius=25)
    bd.extrude(amount=180, both=True, mode=bd.Mode.SUBTRACT)

model = part.part
"""

    def _generate_compound_code(self, plan: CADPlan) -> str:
        return f"""# ATS Engineering AI — Compound CAD Solid
import build123d as bd

with bd.BuildPart() as part:
    bd.Box(100, 60, 20)
model = part.part
"""

    def _generate_sprocket_code(self, plan: CADPlan) -> str:
        od = float(plan.parameters.get("outer_diameter_mm") or plan.diameter_mm or 60.0)
        teeth = int(plan.parameters.get("teeth_count") or 16)
        bore = float(plan.parameters.get("bore_diameter_mm") or 15.0)
        thk = float(plan.parameters.get("thickness_mm") or plan.height_mm or 10.0)
        return f"""# ATS Engineering AI — Sprocket Solid
import math
import build123d as bd

with bd.BuildPart() as part:
    bd.Cylinder(radius={od / 2.0}, height={thk})
    tooth_r = ({od} / {teeth}) * 0.8
    pitch_r = {od} / 2.0
    notch_locs = [
        (pitch_r * math.cos(2 * math.pi * i / {teeth}), pitch_r * math.sin(2 * math.pi * i / {teeth}))
        for i in range({teeth})
    ]
    with bd.BuildSketch(bd.Plane.XY):
        with bd.Locations(notch_locs):
            bd.Circle(radius=tooth_r)
    bd.extrude(amount={thk * 2.0}, both=True, mode=bd.Mode.SUBTRACT)

    with bd.BuildSketch(bd.Plane.XY):
        bd.Circle(radius={bore / 2.0})
    bd.extrude(amount={thk * 2.0}, both=True, mode=bd.Mode.SUBTRACT)

model = part.part
"""

    def _generate_turntable_code(self, plan: CADPlan) -> str:
        return f"""# ATS Engineering AI — Turntable
import build123d as bd

with bd.BuildPart() as part:
    bd.Box(1000, 1000, 80)
    with bd.Locations([(0, 0, 50)]):
        bd.Cylinder(radius=450, height=40)

model = part.part
"""

    def _generate_conveyor_code(self, plan: CADPlan) -> str:
        return f"""# ATS Engineering AI — PRB Conveyor
import build123d as bd

with bd.BuildPart() as part:
    with bd.Locations([(0, 205, 0)]):
        bd.Box(2000, 40, 100)
    with bd.Locations([(0, -205, 0)]):
        bd.Box(2000, 40, 100)
    with bd.Locations([(0, 0, -30)]):
        bd.Box(200, 370, 40)

model = part.part
"""


    def _execute_python_script(self, code: str) -> Any:
        def _safe_rect(width, length=None, *args, **kwargs):
            h = length if length is not None else kwargs.pop("height", width)
            loc = kwargs.pop("center", kwargs.pop("location", kwargs.pop("pos", None)))
            if loc is not None:
                with bd.Locations([loc]):
                    return bd.Rectangle(width, h, *args, **kwargs)
            return bd.Rectangle(width, h, *args, **kwargs)

        def _safe_circle(radius=None, *args, **kwargs):
            r = radius if radius is not None else kwargs.pop("r", kwargs.pop("radius", 5.0))
            loc = kwargs.pop("center", kwargs.pop("location", kwargs.pop("pos", None)))
            if loc is not None:
                with bd.Locations([loc]):
                    return bd.Circle(radius=r, *args, **kwargs)
            return bd.Circle(radius=r, *args, **kwargs)

        def _safe_slot(width=40.0, height=8.0, *args, **kwargs):
            w = kwargs.pop("length", width)
            h = kwargs.pop("width", height) if "length" in kwargs else height
            loc = kwargs.pop("center", kwargs.pop("location", kwargs.pop("pos", None)))
            if loc is not None:
                with bd.Locations([loc]):
                    return bd.SlotOverall(width=w, height=h, *args, **kwargs)
            return bd.SlotOverall(width=w, height=h, *args, **kwargs)

        def _safe_fillet(objects, radius, *args, **kwargs):
            try:
                return bd.fillet(objects, radius, *args, **kwargs)
            except Exception as e:
                logger.debug(f"Non-critical fillet skipped: {e}")
                return objects

        def _safe_locations(*args, **kwargs):
            loc_list = []
            for a in args:
                if isinstance(a, (_orig_locations, bd.PolarLocations, bd.GridLocations)):
                    loc_list.extend(getattr(a, "locations", []))
                elif isinstance(a, bd.Rotation):
                    loc_list.append(bd.Location((0, 0, 0), a))
                elif isinstance(a, (list, tuple)):
                    loc_list.extend(a)
                else:
                    loc_list.append(a)
            return bd.Locations(loc_list if loc_list else [(0, 0, 0)])

        class _SafeRotation:
            def __init__(self, *args, **kwargs):
                self.rot = bd.Rotation(*args, **kwargs)
            def __enter__(self):
                self._cm = bd.Locations(bd.Location((0, 0, 0), self.rot))
                return self._cm.__enter__()
            def __exit__(self, *args):
                return self._cm.__exit__(*args)

        def _safe_cylinder(radius=10.0, height=20.0, *args, **kwargs):
            kwargs.pop("centered", None)
            kwargs.pop("axis", None)
            return bd.Cylinder(radius=radius, height=height, *args, **kwargs)

        def _safe_box(length=100.0, width=60.0, height=20.0, *args, **kwargs):
            kwargs.pop("centered", None)
            return bd.Box(length, width, height, *args, **kwargs)

        def _safe_extrude(amount=10.0, *args, **kwargs):
            try:
                if isinstance(amount, (int, float)):
                    return bd.extrude(amount=amount, *args, **kwargs)
                elif args and isinstance(args[0], (int, float)):
                    return bd.extrude(amount=args[0], **kwargs)
                return bd.extrude(amount=amount, *args, **kwargs)
            except Exception:
                if isinstance(amount, (int, float)):
                    return bd.extrude(amount=amount, **kwargs)
                raise

        global_scope = {
            "bd": bd,
            "math": math,
            "BuildPart": bd.BuildPart,
            "BuildSketch": bd.BuildSketch,
            "BuildLine": bd.BuildLine,
            "Box": _safe_box,
            "Cylinder": _safe_cylinder,
            "Sphere": bd.Sphere,
            "Cone": bd.Cone,
            "Torus": bd.Torus,
            "Rectangle": _safe_rect,
            "Circle": _safe_circle,
            "SlotOverall": _safe_slot,
            "Slot": _safe_slot,
            "RegularPolygon": bd.RegularPolygon,
            "Polygon": bd.Polygon,
            "Locations": _safe_locations,
            "GridLocations": bd.GridLocations,
            "PolarLocations": bd.PolarLocations,
            "Rotation": _SafeRotation,
            "extrude": _safe_extrude,
            "revolve": bd.revolve,
            "fillet": _safe_fillet,
            "chamfer": bd.chamfer,
            "offset": bd.offset,
            "Plane": bd.Plane,
            "Axis": bd.Axis,
            "Mode": bd.Mode,
        }
        local_scope: Dict[str, Any] = {}
        exec(code, global_scope, local_scope)

        # Check explicit output variables first
        for key in ["model", "result", "part", "solid"]:
            if key in local_scope:
                val = local_scope[key]
                if isinstance(val, (bd.Part, bd.Compound, bd.Solid, bd.Shape)):
                    return val
                if hasattr(val, "part") and isinstance(val.part, (bd.Part, bd.Compound, bd.Solid, bd.Shape)):
                    return val.part
                if hasattr(val, "solid") and isinstance(val.solid, (bd.Part, bd.Compound, bd.Solid, bd.Shape)):
                    return val.solid
                if hasattr(val, "wrapped") and not callable(val):
                    return val

        for var_name, var_val in local_scope.items():
            if isinstance(var_val, (bd.Part, bd.Compound, bd.Solid, bd.Shape)):
                return var_val
            if hasattr(var_val, "part") and isinstance(var_val.part, (bd.Part, bd.Compound, bd.Solid, bd.Shape)):
                return var_val.part
            if hasattr(var_val, "solid") and isinstance(var_val.solid, (bd.Part, bd.Compound, bd.Solid, bd.Shape)):
                return var_val.solid
        raise ValueError("No valid build123d Part/Solid found in executed script.")

    def _build_box_with_holes(self, plan: CADPlan) -> Any:
        length = float(plan.length_mm or plan.parameters.get("length_mm") or 100.0)
        width = float(plan.width_mm or plan.parameters.get("width_mm") or 60.0)
        height = float(plan.height_mm or plan.parameters.get("height_mm") or 20.0)

        with bd.BuildPart() as part:
            bd.Box(length, width, height)

            # Apply holes if any
            all_holes = [h for h in plan.holes if h.diameter_mm > 0.0]

            # Check parameters for hole definitions
            if not all_holes and "hole_diameter_mm" in plan.parameters:
                h_dia = float(plan.parameters.get("hole_diameter_mm", 0.0))
                h_cnt = int(plan.parameters.get("hole_count", 0))
                if h_dia > 0.0:
                    if h_cnt == 4 or plan.parameters.get("pattern") == "4_corners":
                        all_holes.append(HoleDefinition(
                            diameter_mm=h_dia,
                            pattern_type="grid_4_corners",
                            count=4,
                            edge_offset_x_mm=plan.parameters.get("edge_offset_x_mm", min(15.0, length * 0.15)),
                            edge_offset_y_mm=plan.parameters.get("edge_offset_y_mm", min(12.0, width * 0.15))
                        ))
                    else:
                        all_holes.append(HoleDefinition(diameter_mm=h_dia, x_mm=0.0, y_mm=0.0, through=True))

            for hole in all_holes:
                if hole.diameter_mm <= 0.0:
                    continue

                if hole.pattern_type == "grid_4_corners" or hole.count == 4:
                    off_x = hole.edge_offset_x_mm if hole.edge_offset_x_mm is not None else min(15.0, length * 0.15)
                    off_y = hole.edge_offset_y_mm if hole.edge_offset_y_mm is not None else min(12.0, width * 0.15)
                    hx = (length / 2.0) - off_x
                    hy = (width / 2.0) - off_y
                    hole_locs = [(hx, hy), (hx, -hy), (-hx, hy), (-hx, -hy)]
                elif hole.pattern_type == "circular_pcd":
                    pcd = float(plan.parameters.get("pcd_mm", min(length, width) * 0.6))
                    hole_locs = [
                        (pcd / 2.0 * math.cos(2 * math.pi * i / hole.count),
                         pcd / 2.0 * math.sin(2 * math.pi * i / hole.count))
                        for i in range(hole.count)
                    ]
                else:
                    hole_locs = [(hole.x_mm, hole.y_mm)]

                with bd.BuildSketch(bd.Plane.XY) as s:
                    with bd.Locations(hole_locs):
                        bd.Circle(radius=hole.diameter_mm / 2.0)

                cut_depth = float(hole.depth_mm) if (hole.depth_mm and not hole.through) else height * 2.0
                bd.extrude(amount=cut_depth, both=True, mode=bd.Mode.SUBTRACT)

        return part.part

    def _build_cylinder(self, plan: CADPlan) -> Any:
        dia = float(plan.diameter_mm or plan.parameters.get("diameter_mm") or (plan.parameters.get("radius_mm", 10.0) * 2.0))
        height = float(plan.height_mm or plan.parameters.get("height_mm") or 50.0)
        bore = float(plan.parameters.get("bore_diameter_mm", 0.0))

        with bd.BuildPart() as part:
            bd.Cylinder(radius=dia / 2.0, height=height)
            if bore > 0.0:
                with bd.BuildSketch(bd.Plane.XY) as s:
                    bd.Circle(radius=bore / 2.0)
                bd.extrude(amount=height * 2.0, both=True, mode=bd.Mode.SUBTRACT)

        return part.part

    def _build_bracket(self, plan: CADPlan) -> Any:
        l = float(plan.parameters.get("length_mm", 80.0))
        w = float(plan.parameters.get("width_mm", 70.0))
        h = float(plan.parameters.get("height_mm", 55.0))
        t = float(plan.parameters.get("flange_thickness_mm", 10.0))
        rib_t = float(plan.parameters.get("rib_thickness_mm", 10.0))
        boss_d = float(plan.parameters.get("boss_diameter_mm", 30.0))
        bore_d = float(plan.parameters.get("bore_diameter_mm", 15.0))
        hole_d = float(plan.parameters.get("hole_diameter_mm", 10.0))

        with bd.BuildPart() as part:
            # Base plate
            bd.Box(l, w, t)
            # Vertical wall
            with bd.Locations([(l / 2.0 - t / 2.0, 0, h / 2.0 - t / 2.0)]):
                bd.Box(t, w, h)
            # Stiffener rib
            with bd.Locations([(0, 0, h / 4.0)]):
                bd.Box(l - t, rib_t, h / 2.0)
            # Base mounting holes
            with bd.BuildSketch(bd.Plane.XY) as s:
                with bd.Locations([(-l / 4.0, w / 4.0), (-l / 4.0, -w / 4.0)]):
                    bd.Circle(radius=hole_d / 2.0)
            bd.extrude(amount=t * 2.0, both=True, mode=bd.Mode.SUBTRACT)

        return part.part

    def _build_valve_body(self, plan: CADPlan) -> Any:
        f_size = float(plan.parameters.get("flange_size_mm", 120.0))
        f_thk = float(plan.parameters.get("flange_thickness_mm", 10.0))
        b_size = float(plan.parameters.get("body_size_mm", 80.0))
        hgt = float(plan.parameters.get("height_mm", 90.0))
        bore_d = float(plan.parameters.get("bore_diameter_mm", 50.0))

        with bd.BuildPart() as part:
            # Bottom flange
            with bd.Locations([(0, 0, -hgt / 2.0 + f_thk / 2.0)]):
                bd.Box(f_size, f_size, f_thk)
            # Central column
            bd.Box(b_size, b_size, hgt - 2 * f_thk)
            # Top flange
            with bd.Locations([(0, 0, hgt / 2.0 - f_thk / 2.0)]):
                bd.Box(f_size, f_size, f_thk)
            # Through bore
            with bd.BuildSketch(bd.Plane.XY) as s:
                bd.Circle(radius=bore_d / 2.0)
            bd.extrude(amount=hgt * 2.0, both=True, mode=bd.Mode.SUBTRACT)

        return part.part

    def _build_compound(self, plan: CADPlan) -> Any:
        base_l = float(plan.length_mm or plan.parameters.get("length_mm", 10.0))
        base_w = float(plan.width_mm or plan.parameters.get("width_mm", 10.0))
        base_h = float(plan.height_mm or plan.parameters.get("height_mm", 10.0))

        with bd.BuildPart() as part:
            bd.Box(base_l, base_w, base_h)

            for feat in plan.features or plan.parameters.get("features", []):
                f_type = feat.get("type", "box")
                f_l = float(feat.get("length_mm", 10.0))
                f_w = float(feat.get("width_mm", 10.0))
                f_h = float(feat.get("height_mm", 10.0))
                ox = float(feat.get("offset_x_mm", 0.0))
                oy = float(feat.get("offset_y_mm", 0.0))
                oz = float(feat.get("offset_z_mm", 0.0))

                with bd.Locations([(ox, oy, oz)]):
                    if f_type == "box":
                        bd.Box(f_l, f_w, f_h)
                    elif f_type == "cylinder":
                        bd.Cylinder(radius=f_l / 2.0, height=f_h)
                    elif f_type == "cone":
                        bd.Cone(bottom_radius=f_l / 2.0, top_radius=0.1, height=f_h)

            # Top feature support
            top = plan.parameters.get("top_feature")
            if top:
                t_type = top.get("type", "box")
                t_size = float(top.get("size_mm", 5.0))
                with bd.Locations([(0, 0, base_h / 2.0 + t_size / 2.0)]):
                    if t_type == "cone":
                        bd.Cone(bottom_radius=t_size, top_radius=0.1, height=t_size)
                    elif t_type == "cylinder":
                        bd.Cylinder(radius=t_size / 2.0, height=t_size)
                    else:
                        bd.Box(t_size, t_size, t_size)

        return part.part

    def _build_sprocket(self, plan: CADPlan) -> Any:
        od = float(plan.parameters.get("outer_diameter_mm") or plan.diameter_mm or 60.0)
        teeth = int(plan.parameters.get("teeth_count") or 16)
        bore = float(plan.parameters.get("bore_diameter_mm") or 15.0)
        thk = float(plan.parameters.get("thickness_mm") or plan.height_mm or 10.0)

        with bd.BuildPart() as part:
            bd.Cylinder(radius=od / 2.0, height=thk)
            # Subtract teeth notches
            tooth_r = (od / teeth) * 0.8
            pitch_r = od / 2.0
            notch_locs = [
                (pitch_r * math.cos(2 * math.pi * i / teeth), pitch_r * math.sin(2 * math.pi * i / teeth))
                for i in range(teeth)
            ]
            with bd.BuildSketch(bd.Plane.XY) as s:
                with bd.Locations(notch_locs):
                    bd.Circle(radius=tooth_r)
            bd.extrude(amount=thk * 2.0, both=True, mode=bd.Mode.SUBTRACT)

            # Bore
            with bd.BuildSketch(bd.Plane.XY) as s:
                bd.Circle(radius=bore / 2.0)
            bd.extrude(amount=thk * 2.0, both=True, mode=bd.Mode.SUBTRACT)

        return part.part

    def _build_turntable(self, plan: CADPlan) -> Any:
        bl = float(plan.parameters.get("bed_length_mm", 1000.0))
        bw = float(plan.parameters.get("bed_width_mm", 1000.0))
        h = float(plan.parameters.get("height_mm", 550.0))

        with bd.BuildPart() as part:
            # Base table solid
            bd.Box(bl, bw, 80.0)
            # Turntable rotary ring
            with bd.Locations([(0, 0, 50.0)]):
                bd.Cylinder(radius=min(bl, bw) * 0.45, height=40.0)
            # Rollers carriage
            with bd.Locations([(0, 0, 90.0)]):
                bd.Box(bl * 0.95, bw * 0.95, 30.0)

        return part.part

    def _build_prb_conveyor(self, plan: CADPlan) -> Any:
        l = float(plan.parameters.get("length_mm", 2000.0))
        w = float(plan.parameters.get("width_mm", 450.0))
        h = float(plan.parameters.get("height_mm", 350.0))

        with bd.BuildPart() as part:
            # Left frame rail
            with bd.Locations([(0, w / 2.0 - 20.0, 0)]):
                bd.Box(l, 40.0, 100.0)
            # Right frame rail
            with bd.Locations([(0, -w / 2.0 + 20.0, 0)]):
                bd.Box(l, 40.0, 100.0)
            # Cross beams
            with bd.Locations([(0, 0, -30.0)]):
                bd.Box(200.0, w - 80.0, 40.0)

        return part.part

cad_engine = CADEngine()
