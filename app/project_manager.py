import os
import json
import time
import shutil
import logging
from typing import List, Optional, Dict, Any
from app.config import settings
from app.schemas import ProjectInfo, VersionInfo, CADPlan, CADValidationReport

logger = logging.getLogger(__name__)

class ProjectManager:
    """
    Manages CAD projects and version history.
    Stores project metadata and version artifacts in exports/projects/<project_id>/
    """

    def __init__(self):
        self.base_dir = os.path.join(settings.EXPORT_DIR, "projects")
        os.makedirs(self.base_dir, exist_ok=True)
        self._ensure_default_project()

    def _ensure_default_project(self):
        projects = self.list_projects()
        if not projects:
            self.create_project("Mechanical Part", "proj_default")

    def _project_meta_path(self, project_id: str) -> str:
        return os.path.join(self.base_dir, project_id, "project.json")

    def list_projects(self) -> List[ProjectInfo]:
        results = []
        if not os.path.exists(self.base_dir):
            return results

        for p_id in os.listdir(self.base_dir):
            p_dir = os.path.join(self.base_dir, p_id)
            if not os.path.isdir(p_dir):
                continue
            meta_path = self._project_meta_path(p_id)
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        results.append(ProjectInfo(**data))
                except Exception as e:
                    logger.warning(f"Error reading project metadata {meta_path}: {e}")
        
        # Sort by updated_at descending
        results.sort(key=lambda p: p.updated_at, reverse=True)
        return results

    def get_project(self, project_id: str) -> Optional[ProjectInfo]:
        meta_path = self._project_meta_path(project_id)
        if not os.path.exists(meta_path):
            return None
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return ProjectInfo(**json.load(f))
        except Exception as e:
            logger.error(f"Error reading project {project_id}: {e}")
            return None

    def create_project(self, name: str = "New Part", project_id: Optional[str] = None) -> ProjectInfo:
        p_id = project_id or f"proj_{int(time.time())}"
        p_dir = os.path.join(self.base_dir, p_id)
        os.makedirs(p_dir, exist_ok=True)

        now = time.time()
        info = ProjectInfo(
            project_id=p_id,
            name=name,
            created_at=now,
            updated_at=now,
            current_version=0,
            versions=[]
        )
        self._save_project(info)
        return info

    def _save_project(self, project: ProjectInfo):
        p_dir = os.path.join(self.base_dir, project.project_id)
        os.makedirs(p_dir, exist_ok=True)
        meta_path = self._project_meta_path(project.project_id)
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(project.model_dump_json(indent=2))

    def add_version(
        self,
        project_id: str,
        prompt: str,
        job_id: str,
        plan: CADPlan,
        validation: CADValidationReport,
        duration_ms: float = 0.0
    ) -> VersionInfo:
        project = self.get_project(project_id)
        if not project:
            project = self.create_project(name="Mechanical Part", project_id=project_id)

        next_v_num = project.current_version + 1
        v_label = f"v{next_v_num:03d}"
        v_id = f"ver_{project_id}_{v_label}"

        # Copy exported files into project version dir: projects/<project_id>/<v_label>/
        v_dir = os.path.join(self.base_dir, project_id, v_label)
        os.makedirs(v_dir, exist_ok=True)

        # Standard file names
        step_name = f"{job_id}.step"
        stl_name = f"{job_id}.stl"
        glb_name = f"{job_id}.glb"
        py_name = f"{job_id}.py"

        # Also store version-specific copies as model.step, model.stl, model.glb, model.py, plan.json, validation.json
        src_step = os.path.join(settings.EXPORT_DIR, step_name)
        if os.path.exists(src_step):
            shutil.copy2(src_step, os.path.join(v_dir, "model.step"))
            shutil.copy2(src_step, os.path.join(v_dir, step_name))

        src_stl = os.path.join(settings.EXPORT_DIR, stl_name)
        if os.path.exists(src_stl):
            shutil.copy2(src_stl, os.path.join(v_dir, "model.stl"))
            shutil.copy2(src_stl, os.path.join(v_dir, stl_name))

        src_glb = os.path.join(settings.EXPORT_DIR, glb_name)
        if os.path.exists(src_glb):
            shutil.copy2(src_glb, os.path.join(v_dir, "model.glb"))
            shutil.copy2(src_glb, os.path.join(v_dir, glb_name))

        src_py = os.path.join(settings.EXPORT_DIR, py_name)
        if os.path.exists(src_py):
            shutil.copy2(src_py, os.path.join(v_dir, "model.py"))
            shutil.copy2(src_py, os.path.join(v_dir, py_name))

        # Save plan.json and validation.json
        with open(os.path.join(v_dir, "plan.json"), "w", encoding="utf-8") as f:
            f.write(plan.model_dump_json(indent=2))

        with open(os.path.join(v_dir, "validation.json"), "w", encoding="utf-8") as f:
            f.write(validation.model_dump_json(indent=2))

        base_file_url = f"/api/projects/{project_id}/versions/{v_label}/files"

        v_info = VersionInfo(
            version_id=v_id,
            version_num=next_v_num,
            version_label=v_label,
            prompt=prompt,
            timestamp=time.time(),
            job_id=job_id,
            step_url=f"{base_file_url}/model.step",
            stl_url=f"{base_file_url}/model.stl" if os.path.exists(os.path.join(v_dir, "model.stl")) else None,
            glb_url=f"{base_file_url}/model.glb" if os.path.exists(os.path.join(v_dir, "model.glb")) else None,
            python_url=f"{base_file_url}/model.py" if os.path.exists(os.path.join(v_dir, "model.py")) else None,
            plan_url=f"{base_file_url}/plan.json",
            validation_url=f"{base_file_url}/validation.json",
            plan=plan,
            validation=validation,
            duration_ms=duration_ms
        )

        project.versions.append(v_info)
        project.current_version = next_v_num
        project.updated_at = time.time()
        self._save_project(project)
        return v_info

    def get_version_file_path(self, project_id: str, version_label: str, file_name: str) -> Optional[str]:
        p_dir = os.path.join(self.base_dir, project_id, version_label)
        file_path = os.path.join(p_dir, file_name)
        if os.path.exists(file_path):
            return file_path
        return None

    def restore_version(self, project_id: str, version_label: str) -> Optional[VersionInfo]:
        project = self.get_project(project_id)
        if not project:
            return None
        target_v = next((v for v in project.versions if v.version_label == version_label), None)
        if not target_v:
            return None

        # Create a new version that clones target_v
        if target_v.plan and target_v.validation:
            return self.add_version(
                project_id=project_id,
                prompt=f"Restored from {version_label}: {target_v.prompt}",
                job_id=f"restore_{int(time.time())}",
                plan=target_v.plan,
                validation=target_v.validation,
                duration_ms=target_v.duration_ms
            )
        return None

    def delete_version(self, project_id: str, version_label: str) -> bool:
        project = self.get_project(project_id)
        if not project:
            return False
        v_idx = next((i for i, v in enumerate(project.versions) if v.version_label == version_label), -1)
        if v_idx == -1:
            return False

        project.versions.pop(v_idx)
        v_dir = os.path.join(self.base_dir, project_id, version_label)
        if os.path.exists(v_dir):
            try:
                shutil.rmtree(v_dir)
            except Exception as e:
                logger.warning(f"Error removing {v_dir}: {e}")

        if project.versions:
            project.current_version = max(v.version_num for v in project.versions)
        else:
            project.current_version = 0

        project.updated_at = time.time()
        self._save_project(project)
        return True

project_manager = ProjectManager()
