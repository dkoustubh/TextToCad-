# OmniCAD — OpenWebUI Tool Integration Guide

This guide details how to install and configure the **OmniCAD** tool in OpenWebUI (`http://192.168.11.86:8081/workspace/tools`).

---

## 1. Quick Installation in OpenWebUI

1. Open your browser and navigate to OpenWebUI Tools workspace:
   `http://192.168.11.86:8081/workspace/tools`
2. Click the **`+ New Tool`** button in the top right.
3. Fill in the tool metadata:
   - **Name:** `OmniCAD`
   - **ID:** `omnicad`
   - **Description:** `AI-powered Mechanical Design and 3D CAD generator. Generates ISO STEP, STL, GLB, and native Autodesk Inventor (.ipt/.iam) files with interactive 3D WebGL viewing and workstation synchronization.`
4. In the code box, paste the complete contents of [`openwebui_tools/omnicad_tool.py`](file:///Users/admin/Desktop/CAD/openwebui_tools/omnicad_tool.py).
5. Click **Save** in the bottom right corner.

---

## 2. Tool Valves (Configuration)

OpenWebUI automatically detects the `Valves` model from the code. You can configure:

| Valve | Default Value | Description |
| :--- | :--- | :--- |
| `CAD_BACKEND_URL` | `http://192.168.11.86:9999` | Text-to-CAD Workbench backend server URL |
| `WORKSTATION_IP` | `192.168.11.150` | Windows CAD workstation running Autodesk Inventor |
| `WORKSTATION_PORT` | `8001` | Workstation agent port |
| `DEFAULT_PROJECT_ID` | `proj_openwebui` | Workspace/project ID in OmniCAD |
| `AUTO_PUSH_TO_INVENTOR` | `True` | Automatically open & focus model in Inventor |
| `CREATE_ASSEMBLY` | `False` | Create `.iam` (Assembly) if True, `.ipt` (Part) if False |

---

## 3. How to Use in OpenWebUI Chat

1. In OpenWebUI, open any chat.
2. Under the prompt box, click the **Tools icon (🛠️)** and toggle **OmniCAD ON**.
3. Type any mechanical engineering design request, for example:
   > *"Create a mounting bracket 120 mm length, 80 mm width, 15 mm thickness with four 8 mm corner mounting holes and a 30 mm center hole."*
   >
   > *"Create a 60 mm diameter cylinder with 100 mm height and a central 25 mm bore."*
   >
   > *"Check OmniCAD system health and Inventor connectivity."*

4. OmniCAD will generate the geometry and respond with:
   - **🌐 3D Interactive View Link:** `http://192.168.11.86:9999/?project=proj_openwebui&version=v001` (Opens directly into the 3D WebGL viewer).
   - **📦 Download Native Autodesk Inventor Part (`.ipt`)**
   - **🏗️ Download Native Autodesk Inventor Assembly (`.iam`)**
   - **📐 Download ISO STEP (`.step`)**
   - **🖨️ Download Mesh (`.stl`)**
   - **🌐 Download WebGL (`.glb`)**
   - **🐍 Download build123d Script (`.py`)**
   - **🔬 Physical Properties Table:** Volume, surface area, bounding box, face/edge counts.
   - **🖥️ Autodesk Inventor Status:** Confirmation that the model was opened and saved in Inventor on `192.168.11.150`.
