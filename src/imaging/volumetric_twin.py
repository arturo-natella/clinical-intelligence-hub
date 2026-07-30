"""Pipeline glue for patient-specific 3D meshes (Pass 1c).

Turns a DICOM series into a GLB the Body Map can load, by driving
:class:`~src.imaging.volumetric_renderer.VolumetricRenderer`.

Two gates guard this, and both default to closed:

* **A trained checkpoint is mandatory.** Without one the renderer falls
  back to an untrained UNet whose segmentation is meaningless. Showing
  that to a patient as their own anatomy is worse than showing nothing,
  so no checkpoint means no mesh.
* **Opt-in.** Full-volume MONAI inference costs minutes and gigabytes,
  and the pipeline loads large models strictly one at a time.

Nothing here may raise into the pipeline: a failed twin degrades to
"no 3D model", never to a failed analysis run.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("CIH-VolumetricTwin")

ENABLE_ENV = "MEDPREP_VOLUMETRIC_TWIN"
MODEL_ENV = "MEDPREP_VOLUMETRIC_MODEL"

# Written under static/models/ so the existing /models/<path> route serves
# it. That directory is gitignored, which keeps patient-derived geometry
# out of version control.
OUTPUT_SUBDIR = "patient"
OUTPUT_FILENAME = "patient_twin.glb"


def twin_enabled() -> bool:
    value = os.environ.get(ENABLE_ENV, "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


def resolve_checkpoint() -> Optional[Path]:
    """Return the trained checkpoint path, or None if unusable."""
    configured = os.environ.get(MODEL_ENV, "").strip()
    if not configured:
        return None
    path = Path(configured).expanduser()
    return path if path.is_file() else None


def _dicom_directories(preprocessed: list) -> list[Path]:
    """DICOM series live as sibling slices; the renderer wants the dir."""
    directories = []
    for item in preprocessed or []:
        if not isinstance(item, dict) or item.get("file_type") != "dicom":
            continue
        filepath = item.get("filepath")
        if not filepath:
            continue
        parent = Path(filepath).parent
        if parent.is_dir() and parent not in directories:
            directories.append(parent)
    return directories


def maybe_generate_twin(
    preprocessed: list,
    output_dir,
    *,
    renderer_factory=None,
) -> Optional[dict]:
    """Generate a patient mesh when every precondition holds.

    Args:
        preprocessed: Pass 0 file records.
        output_dir: static/models directory to write into.
        renderer_factory: Injection point for tests; defaults to the real
            VolumetricRenderer (imported lazily so the disabled path
            never pulls in torch/MONAI).

    Returns:
        A manifest dict (path, url, generated_at, source_dicom_dir), or
        None when skipped or failed.
    """
    if not twin_enabled():
        return None

    checkpoint = resolve_checkpoint()
    if checkpoint is None:
        logger.info(
            "Volumetric twin enabled but no trained checkpoint at %s — "
            "skipping (an untrained model would produce meaningless anatomy)",
            MODEL_ENV,
        )
        return None

    dicom_dirs = _dicom_directories(preprocessed)
    if not dicom_dirs:
        logger.info("Volumetric twin: no DICOM series in this batch — skipping")
        return None

    if len(dicom_dirs) > 1:
        logger.info(
            "Volumetric twin: %d DICOM series present, rendering the first",
            len(dicom_dirs),
        )
    source_dir = dicom_dirs[0]

    try:
        if renderer_factory is None:
            from src.imaging.volumetric_renderer import VolumetricRenderer

            renderer_factory = VolumetricRenderer

        target_dir = Path(output_dir) / OUTPUT_SUBDIR
        renderer = renderer_factory(model_path=str(checkpoint))
        glb_path = renderer.process_scan(
            str(source_dir), str(target_dir), OUTPUT_FILENAME,
        )
    except Exception as exc:
        # Includes ImportError (torch/MONAI absent) and OOM during inference.
        logger.warning(
            "Volumetric twin generation failed (error_type=%s)",
            type(exc).__name__,
        )
        return None

    return {
        "path": str(glb_path),
        "url": f"/models/{OUTPUT_SUBDIR}/{OUTPUT_FILENAME}",
        "generated_at": datetime.now().isoformat(),
        "source_dicom_dir": str(source_dir),
    }
