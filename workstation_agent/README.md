# Autodesk Inventor Workstation Agent

A high-speed, reliable Windows COM automation bridge for Autodesk Inventor. It listens for CAD jobs from the **Text-to-CAD Workbench**, automatically imports STEP files, and saves them as native **`.ipt`** (Part) or **`.iam`** (Assembly) files inside the engineer's active Autodesk Inventor session.

---

## 🚀 Quick Setup on Workstation (`192.168.11.150`)

### 1. Copy Files to the Workstation
Copy this `workstation_agent` folder to your Windows PC (e.g. `C:\workstation_agent`).

### 2. Run the Agent
Double-click:
```cmd
run_inventor_agent.bat
```
This automatically installs the required packages (`fastapi`, `uvicorn`, `pywin32`, `pydantic`) and starts the server on port `8001`.

### 3. Open Autodesk Inventor
Launch Autodesk Inventor on the workstation. The agent will automatically connect to the active Inventor session.

---

## 📡 API Endpoints

* `GET http://192.168.11.150:8001/health`: Checks agent connectivity and whether Inventor is running.
* `POST http://192.168.11.150:8001/api/inventor/open`:
  ```json
  {
    "step_url": "http://192.168.11.86:9999/api/export/cad_123.step",
    "part_name": "mounting_bracket",
    "create_assembly": false,
    "bring_to_front": true
  }
  ```
  * `create_assembly = false`: Converts and saves as native `.ipt` Part.
  * `create_assembly = true`: Creates a new `.iam` Assembly and places the part occurrence at origin.
