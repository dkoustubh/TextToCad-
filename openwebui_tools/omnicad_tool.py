"""
title: OmniCAD
author: ATS Engineering AI
author_url: http://192.168.11.86:9999
description: Precision 3D CAD mechanical generator bridging OpenWebUI to the OmniCAD Workbench (192.168.11.86:9999) and Autodesk Inventor workstation (192.168.11.150:8001). Generates STEP, STL, GLB, and native Autodesk Inventor (.ipt Part, .iam Assembly) models with direct 3D WebGL viewing and download links.
version: 1.0.0
requirements: requests, pydantic
license: MIT
"""

import json
from typing import Optional, Callable, Awaitable, Any, Dict
from pydantic import BaseModel, Field
import requests


class Tools:
    class Valves(BaseModel):
        CAD_BACKEND_URL: str = Field(
            default="http://192.168.11.86:9999",
            description="URL to the Text-to-CAD Workbench backend server."
        )
        WORKSTATION_IP: str = Field(
            default="192.168.11.150",
            description="IP address of the CAD Workstation running Autodesk Inventor."
        )
        WORKSTATION_PORT: int = Field(
            default=8001,
            description="Port of the Autodesk Inventor Workstation Agent."
        )
        DEFAULT_PROJECT_ID: str = Field(
            default="proj_openwebui",
            description="Default project identifier in OmniCAD Workbench."
        )
        AUTO_PUSH_TO_INVENTOR: bool = Field(
            default=True,
            description="Automatically push and open the generated model inside Autodesk Inventor on the CAD workstation."
        )
        CREATE_ASSEMBLY: bool = Field(
            default=False,
            description="If True, converts design to a native Autodesk Inventor Assembly (.iam); if False, Part (.ipt)."
        )

    def __init__(self):
        self.valves = self.Valves()

    async def generate_cad_design(
        self,
        prompt: str,
        project_id: Optional[str] = None,
        create_assembly: Optional[bool] = None,
        __event_emitter__: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> str:
        """
        Generate a precision 3D CAD mechanical model from a natural-language engineering description.
        Creates ISO 10303 STEP files, 3D meshes (STL/GLB), Python build123d scripts, and native Autodesk Inventor Part (.ipt) / Assembly (.iam) files.
        Provides a direct 3D interactive viewer link and downloadable CAD links.

        :param prompt: Detailed description of the mechanical part (e.g. 'Mounting bracket 120x80x15 mm with four 10mm corner holes, 5mm fillet, and 30mm central bore').
        :param project_id: Optional project/workspace ID to organize design iterations. Defaults to 'proj_openwebui'.
        :param create_assembly: Optional flag to create an Assembly (.iam) instead of a Part (.ipt). Defaults to Valves setting.
        :return: Formatted markdown engineering report with 3D viewer URL, download links (.ipt, .iam, .step, .stl, .glb), validation report, and Inventor sync status.
        """
        if __event_emitter__:
            await __event_emitter__({
                "type": "status",
                "data": {
                    "description": "Connecting to OmniCAD Backend & generating 3D B-Rep geometry...",
                    "done": False,
                },
            })

        backend_url = self.valves.CAD_BACKEND_URL.rstrip("/")
        workstation_ip = self.valves.WORKSTATION_IP.strip()
        workstation_port = self.valves.WORKSTATION_PORT
        target_project_id = (project_id or self.valves.DEFAULT_PROJECT_ID).strip()
        is_assembly = create_assembly if create_assembly is not None else self.valves.CREATE_ASSEMBLY

        payload = {
            "prompt": prompt,
            "project_id": target_project_id,
            "workstation_ip": workstation_ip,
            "context": {
                "source": "openwebui",
                "create_assembly": is_assembly
            }
        }

        try:
            chat_endpoint = f"{backend_url}/api/chat"
            response = requests.post(chat_endpoint, json=payload, timeout=180)
            if response.status_code != 200:
                error_text = response.text
                if __event_emitter__:
                    await __event_emitter__({
                        "type": "status",
                        "data": {
                            "description": f"OmniCAD generation failed with HTTP {response.status_code}",
                            "done": True,
                        },
                    })
                return f"### ❌ OmniCAD Generation Failed\n\n**Backend Error (HTTP {response.status_code}):**\n```\n{error_text}\n```"

            data = response.json()

        except Exception as e:
            if __event_emitter__:
                await __event_emitter__({
                    "type": "status",
                    "data": {
                        "description": f"Connection error: {str(e)}",
                        "done": True,
                    },
                })
            return (
                f"### ❌ Unable to connect to OmniCAD Backend at `{backend_url}`\n\n"
                f"**Error Details:** `{str(e)}`\n\n"
                f"Please verify that the Text-to-CAD server is running at `{backend_url}`."
            )

        # Extract returned metadata
        p_id = data.get("project_id", target_project_id)
        v_label = data.get("version_label", "v001")
        plan = data.get("plan") or {}
        validation = data.get("validation") or {}
        step_url = data.get("step_url") or f"{backend_url}/api/projects/{p_id}/versions/{v_label}/files/model.step"
        stl_url = data.get("stl_url") or f"{backend_url}/api/projects/{p_id}/versions/{v_label}/files/model.stl"
        glb_url = data.get("glb_url") or f"{backend_url}/api/projects/{p_id}/versions/{v_label}/files/model.glb"
        py_url = data.get("py_url") or f"{backend_url}/api/projects/{p_id}/versions/{v_label}/files/model.py"
        ipt_url = data.get("ipt_url") or f"{backend_url}/api/projects/{p_id}/versions/{v_label}/files/model.ipt"
        iam_url = data.get("iam_url") or f"{backend_url}/api/projects/{p_id}/versions/{v_label}/files/model.iam"
        view_url = data.get("view_url") or f"{backend_url}/?project={p_id}&version={v_label}"

        # If auto-push to Inventor workstation is enabled, dispatch to workstation agent
        inventor_sync_msg = "Not requested"
        if self.valves.AUTO_PUSH_TO_INVENTOR and workstation_ip:
            if __event_emitter__:
                await __event_emitter__({
                    "type": "status",
                    "data": {
                        "description": f"Syncing native model to Autodesk Inventor on {workstation_ip}:{workstation_port}...",
                        "done": False,
                    },
                })

            try:
                inv_endpoint = f"http://{workstation_ip}:{workstation_port}/api/inventor/open"
                inv_payload = {
                    "step_url": step_url,
                    "part_name": f"{p_id}_{v_label}",
                    "create_assembly": is_assembly,
                    "bring_to_front": True
                }
                inv_res = requests.post(inv_endpoint, json=inv_payload, timeout=25)
                if inv_res.status_code == 200:
                    inv_data = inv_res.json()
                    inventor_sync_msg = f"✅ **Synchronized & Live in Autodesk Inventor**\n- **Target Machine:** `{workstation_ip}`\n- **Document Type:** `{inv_data.get('file_type', 'Part')}`\n- **Workstation Path:** `{inv_data.get('file_path', 'Saved')}`\n- **Inventor Version:** `{inv_data.get('inventor_version', 'Connected')}`"
                else:
                    inventor_sync_msg = f"⚠️ **Workstation sync returned HTTP {inv_res.status_code}:** {inv_res.text}"
            except Exception as e:
                inventor_sync_msg = f"ℹ️ *Workstation agent unreachable at {workstation_ip}:{workstation_port} ({str(e)}). File is available for local download below.*"

        if __event_emitter__:
            await __event_emitter__({
                "type": "status",
                "data": {
                    "description": f"CAD generation complete for {v_label}!",
                    "done": True,
                },
            })

        # Format geometry details
        shape_type = plan.get("shape_type", "Solid").capitalize()
        bbox = validation.get("bounding_box", {})
        bbox_str = f"{bbox.get('size_x', '--')} × {bbox.get('size_y', '--')} × {bbox.get('size_z', '--')} mm"
        volume_mm3 = validation.get("volume_mm3", 0)
        area_mm2 = validation.get("surface_area_mm2", 0)
        explanation = plan.get("explanation", "Mechanical 3D solid generated from geometric specification.")
        duration_ms = data.get("duration_ms", "--")

        # Holes and features
        holes_desc = ""
        holes = plan.get("holes", [])
        if holes:
            holes_desc = "\n".join([
                f"- **Hole Pattern:** {h.get('count', 1)}x Ø{h.get('diameter_mm', '--')} mm ({h.get('pattern_type', 'custom')})"
                for h in holes
            ])
        else:
            holes_desc = "- *No secondary hole patterns requested.*"

        # Build clean, rich engineering response
        report = f"""### 🛠️ OmniCAD Design Generated: `{p_id}` ({v_label})

**Design Summary:** {explanation}

---

#### 🌐 3D Interactive View
👉 **[Click here to Open Design in OmniCAD 3D Viewport]({view_url})**
*(Opens the interactive 3D WebGL inspector at `{view_url}` with orbit, pan, section analysis, and edge rendering)*

---

#### 📥 Download CAD & Native Inventor Files
- 📦 **[Download Native Autodesk Inventor Part (.ipt)]({ipt_url})**
- 🏗️ **[Download Native Autodesk Inventor Assembly (.iam)]({iam_url})**
- 📐 **[Download ISO 10303 Standard CAD Model (.step)]({step_url})**
- 🖨️ **[Download 3D Printing Mesh (.stl)]({stl_url})**
- 🌐 **[Download WebGL 3D Asset (.glb)]({glb_url})**
- 🐍 **[Download Parametric build123d Script (.py)]({py_url})**

---

#### 🔬 Physical & Geometric Properties
| Property | Value |
| :--- | :--- |
| **Shape Type** | `{shape_type}` |
| **Bounding Box (X × Y × Z)** | `{bbox_str}` |
| **Total Volume** | `{volume_mm3:,.1f} mm³` |
| **Surface Area** | `{area_mm2:,.1f} mm²` |
| **Topology (F / E / V)** | `{validation.get('face_count', '--')} faces` / `{validation.get('edge_count', '--')} edges` / `{validation.get('vertex_count', '--')} vertices` |
| **Solid Verification** | `{'✅ Valid Closed Manifold Solid' if validation.get('is_valid') else '⚠️ Unverified'}` |
| **Generation Latency** | `{duration_ms} ms` |

#### ⚙️ Feature Specifications
{holes_desc}

---

#### 🖥️ Autodesk Inventor Workstation Status
{inventor_sync_msg}
"""
        return report

    async def check_omnicad_health(
        self,
        __event_emitter__: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> str:
        """
        Check the connectivity and operational health of both the OmniCAD Workbench backend (192.168.11.86:9999)
        and the Windows CAD Workstation running Autodesk Inventor (192.168.11.150:8001).

        :return: Diagnostic status report of all OmniCAD subsystem endpoints.
        """
        backend_url = self.valves.CAD_BACKEND_URL.rstrip("/")
        workstation_ip = self.valves.WORKSTATION_IP.strip()
        workstation_port = self.valves.WORKSTATION_PORT

        backend_status = "🔴 Offline"
        workstation_status = "🔴 Offline"
        inventor_app_status = "Not Connected"

        # Check backend
        try:
            res = requests.get(f"{backend_url}/health", timeout=5)
            if res.status_code == 200:
                b_data = res.json()
                backend_status = f"🟢 Online (v{b_data.get('version', '1.0.0')})"
        except Exception as e:
            backend_status = f"🔴 Offline ({str(e)})"

        # Check workstation
        try:
            w_res = requests.get(f"http://{workstation_ip}:{workstation_port}/health", timeout=5)
            if w_res.status_code == 200:
                w_data = w_res.json()
                inv_conn = w_data.get("inventor_connected", False)
                inv_ver = w_data.get("inventor_version", "Unknown")
                workstation_status = "🟢 Online"
                inventor_app_status = f"🟢 Connected ({inv_ver})" if inv_conn else "🟡 Agent Online, Inventor Closed"
        except Exception as e:
            workstation_status = f"🔴 Unreachable ({str(e)})"

        return f"""### 🩺 OmniCAD System Health Diagnostics

| Component | Target Address | Status | Notes |
| :--- | :--- | :--- | :--- |
| **CAD Backend (Text-to-CAD)** | `{backend_url}` | {backend_status} | OpenCascade / build123d engine |
| **Workstation Agent** | `{workstation_ip}:{workstation_port}` | {workstation_status} | Windows .NET / COM automation bridge |
| **Autodesk Inventor Session** | `{workstation_ip}` | {inventor_app_status} | Live 3D CAD application |

**Active Valves Configuration:**
- `CAD_BACKEND_URL`: `{backend_url}`
- `WORKSTATION_IP`: `{workstation_ip}`
- `DEFAULT_PROJECT_ID`: `{self.valves.DEFAULT_PROJECT_ID}`
- `AUTO_PUSH_TO_INVENTOR`: `{self.valves.AUTO_PUSH_TO_INVENTOR}`
- `CREATE_ASSEMBLY`: `{self.valves.CREATE_ASSEMBLY}`
"""
