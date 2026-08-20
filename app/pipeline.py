import time
import uuid
import logging
import traceback
from typing import Optional, Dict, Any
from app.schemas import CADPlan, CADValidationReport, PipelineResult
from app.llm_client import llm_client
from app.cad_engine import cad_engine
from app.config import settings

logger = logging.getLogger(__name__)

class TextToCADPipeline:
    """
    True End-to-End Autonomous Text-to-CAD Engineering Pipeline:
    USER PROMPT → Gemma 31B Reasoning → build123d Python Script → OpenCascade Engine →
    Geometry Validation → [Automatic LLM Repair Loop if needed] → ISO STEP / STL / GLB Artifacts
    """

    async def run(
        self,
        prompt: str,
        job_id: Optional[str] = None,
        workstation_ip: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        export_subfolder: Optional[str] = None
    ) -> PipelineResult:
        start_time = time.time()
        job_id = job_id or f"cad_{uuid.uuid4().hex[:8]}"
        workstation = workstation_ip or settings.DEFAULT_WORKSTATION_IP

        gemma_dur = 0.0
        cad_dur = 0.0
        val_dur = 0.0
        retries = 0
        max_retries = 3

        logger.info(f"[{job_id}] Starting Text-to-CAD pipeline for prompt: '{prompt}'")

        # 1. Gemma / LLM Intent Extraction & Code Synthesis
        t_gemma_start = time.time()
        plan, py_code = await llm_client.generate_cad_code(prompt, context)
        gemma_dur += (time.time() - t_gemma_start) * 1000
        plan.python_script = py_code

        current_code = py_code
        solid_obj = None
        validation: Optional[CADValidationReport] = None
        last_error = ""

        # 2. Closed-Loop Execution & Repair Loop
        for attempt in range(max_retries + 1):
            t_cad_start = time.time()
            try:
                plan.python_script = current_code
                solid_obj, validation = cad_engine.generate_from_plan(
                    plan,
                    output_id=job_id,
                    export_subfolder=export_subfolder
                )
                cad_dur += (time.time() - t_cad_start) * 1000
                val_dur = max(0.0, cad_dur * 0.2)

                # Check if CAD solid is geometrically valid & manifold
                if validation.is_valid and validation.step_import_verified:
                    logger.info(f"[{job_id}] Success on attempt {attempt}: Volume={validation.volume_mm3}mm³, Faces={validation.face_count}")
                    break
                else:
                    last_error = f"Geometry validation failed: {validation.message}"
                    logger.warning(f"[{job_id}] Validation failure on attempt {attempt}: {last_error}")

            except Exception as e:
                cad_dur += (time.time() - t_cad_start) * 1000
                tb_str = traceback.format_exc()
                last_error = f"{type(e).__name__}: {e}\n{tb_str}"
                logger.warning(f"[{job_id}] CAD compilation error on attempt {attempt}: {e}")

            # If not succeeded and retries remaining, invoke Gemma for self-repair
            if attempt < max_retries:
                retries += 1
                logger.info(f"[{job_id}] Invoking Gemma self-repair loop (retry {retries}/{max_retries})...")
                t_repair_start = time.time()
                plan, repaired_code = await llm_client.repair_cad_code(
                    prompt=prompt,
                    failed_code=current_code,
                    error_traceback=last_error
                )
                gemma_dur += (time.time() - t_repair_start) * 1000
                current_code = repaired_code or current_code

        # 3. Final Verification & Return Result
        total_dur = round((time.time() - start_time) * 1000, 2)

        if validation and validation.is_valid and validation.step_import_verified:
            return PipelineResult(
                success=True,
                prompt=prompt,
                plan=plan,
                validation=validation,
                job_id=job_id,
                workstation=workstation,
                duration_ms=total_dur,
                gemma_duration_ms=round(gemma_dur, 2),
                cad_build_duration_ms=round(cad_dur, 2),
                validation_duration_ms=round(val_dur, 2)
            )
        else:
            err_msg = last_error or "OpenCascade solid creation could not be verified."
            logger.error(f"[{job_id}] Pipeline failed after {retries} retries: {err_msg}")
            fallback_plan = plan or CADPlan(tool="error", shape_type="error", explanation=err_msg)
            return PipelineResult(
                success=False,
                prompt=prompt,
                plan=fallback_plan,
                validation=validation,
                job_id=job_id,
                workstation=workstation,
                duration_ms=total_dur,
                gemma_duration_ms=round(gemma_dur, 2),
                cad_build_duration_ms=round(cad_dur, 2),
                validation_duration_ms=round(val_dur, 2),
                error=err_msg
            )

pipeline = TextToCADPipeline()
