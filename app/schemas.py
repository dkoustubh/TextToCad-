from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class HoleDefinition(BaseModel):
    diameter_mm: float = Field(..., description="Diameter of the hole in mm")
    x_mm: float = Field(0.0, description="Center X position relative to part center")
    y_mm: float = Field(0.0, description="Center Y position relative to part center")
    depth_mm: Optional[float] = Field(None, description="Depth of hole if blind; None if through")
    through: bool = Field(True, description="Whether hole penetrates completely through solid")
    pattern_type: str = Field("custom", description="Pattern: single, grid_4_corners, linear_row, circular_pcd")
    count: int = Field(1, description="Number of holes")
    edge_offset_x_mm: Optional[float] = Field(None, description="Distance from X edges for corner hole patterns")
    edge_offset_y_mm: Optional[float] = Field(None, description="Distance from Y edges for corner hole patterns")

class CADPlan(BaseModel):
    tool: str = Field("inventor.create_box", description="Target CAD tool or operation")
    shape_type: str = Field("box", description="Type of geometry: box, box_with_holes, cylinder, cone, bracket, compound, turntable, prb_conveyor, custom_script")
    length_mm: Optional[float] = Field(None, description="Length / X dimension in mm")
    width_mm: Optional[float] = Field(None, description="Width / Y dimension in mm")
    height_mm: Optional[float] = Field(None, description="Height / Z dimension in mm")
    diameter_mm: Optional[float] = Field(None, description="Outer diameter in mm for cylindrical solids")
    holes: List[HoleDefinition] = Field(default_factory=list, description="List of subtractive hole features")
    features: List[Dict[str, Any]] = Field(default_factory=list, description="Sub-features or compound elements")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Raw parameters dictionary")
    python_script: Optional[str] = Field(None, description="Executable build123d script if custom")
    explanation: str = Field("", description="Engineering explanation of the geometry")

class BoundingBoxInfo(BaseModel):
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    min_z: float
    max_z: float
    size_x: float
    size_y: float
    size_z: float

class CADValidationReport(BaseModel):
    is_valid: bool
    is_solid: bool
    volume_mm3: float
    surface_area_mm2: float = 0.0
    bounding_box: BoundingBoxInfo
    face_count: int
    edge_count: int
    vertex_count: int
    solid_count: int = 1
    brep_check_status: bool
    step_import_verified: bool
    step_path: str
    stl_path: Optional[str] = None
    glb_path: Optional[str] = None
    python_path: Optional[str] = None
    message: str

class PipelineResult(BaseModel):
    success: bool
    prompt: str
    plan: CADPlan
    validation: Optional[CADValidationReport] = None
    job_id: str
    workstation: str = "192.168.11.150"
    duration_ms: float = 0.0
    gemma_duration_ms: float = 0.0
    cad_build_duration_ms: float = 0.0
    validation_duration_ms: float = 0.0
    error: Optional[str] = None

class ChatRequest(BaseModel):
    prompt: str
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    session_id: Optional[str] = None
    workstation_ip: Optional[str] = None
    user_name: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    success: bool
    tool: str
    shape: str
    parameters: Dict[str, Any]
    job_id: str
    workstation_ip: str
    message: str
    project_id: Optional[str] = None
    version_id: Optional[str] = None
    version_num: int = 1
    validation: Optional[CADValidationReport] = None
    step_url: Optional[str] = None
    stl_url: Optional[str] = None
    glb_url: Optional[str] = None
    python_url: Optional[str] = None
    plan_url: Optional[str] = None
    validation_url: Optional[str] = None
    duration_ms: float = 0.0
    gemma_duration_ms: float = 0.0
    cad_build_duration_ms: float = 0.0

class VersionInfo(BaseModel):
    version_id: str
    version_num: int
    version_label: str  # e.g. "v001"
    prompt: str
    timestamp: float
    job_id: str
    step_url: str
    stl_url: Optional[str] = None
    glb_url: Optional[str] = None
    python_url: Optional[str] = None
    plan_url: Optional[str] = None
    validation_url: Optional[str] = None
    plan: Optional[CADPlan] = None
    validation: Optional[CADValidationReport] = None
    duration_ms: float = 0.0

class ProjectInfo(BaseModel):
    project_id: str
    name: str
    created_at: float
    updated_at: float
    current_version: int
    versions: List[VersionInfo] = Field(default_factory=list)

