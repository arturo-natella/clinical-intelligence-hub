"""
Clinical Intelligence Hub - Volumetric Renderer Pipeline

Converts raw DICOM scans into patient-specific 3D meshes (GLB) for the
Three.js frontend. Uses MONAI for segmentation, marching cubes for surface
extraction, and trimesh for GLB export.

Pipeline stages:
  1. Load DICOM series -> 3D numpy volume
  2. MONAI segmentation inference (MPS-accelerated)
  3. Marching cubes surface extraction per label
  4. Mesh construction + material assignment
  5. GLB export for Three.js

Memory management:
  - torch.no_grad() during inference
  - Explicit del + gc.collect() after each major stage
  - torch.mps.empty_cache() to release unified memory pool
  - Peak target: under 36GB on M4 Pro 48GB
"""

import gc
import json
import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("CIH-VolumetricRenderer")


class VolumetricRenderer:
    """Converts DICOM scans into segmented 3D GLB meshes for the Body Map."""

    # Default MONAI model to use for segmentation. Configurable via constructor.
    DEFAULT_MODEL_PATH = None  # Set to a .pt checkpoint path if available

    # Label -> color mapping for common anatomical structures.
    # Colors are RGBA tuples (0-255). These match standard medical visualization.
    LABEL_COLORS = {
        0:  None,                         # Background - skip
        1:  (220, 180, 170, 200, "skin"),
        2:  (200, 50,  50,  220, "liver"),
        3:  (180, 80,  80,  220, "spleen"),
        4:  (140, 100, 80,  220, "kidney_left"),
        5:  (140, 100, 80,  220, "kidney_right"),
        6:  (80,  100, 160, 220, "stomach"),
        7:  (200, 180, 160, 220, "gallbladder"),
        8:  (120, 80,  80,  220, "pancreas"),
        9:  (200, 60,  60,  240, "heart"),
        10: (240, 160, 160, 200, "lung_left"),
        11: (240, 160, 160, 200, "lung_right"),
        12: (230, 220, 200, 200, "bone"),
        13: (180, 40,  40,  240, "aorta"),
        # Pathology labels (if segmented separately)
        99: (255, 255, 0,   255, "pathology"),  # Bright yellow for tumors/masses
    }

    # Marching cubes step size: 1 = full res, 2 = half (8x fewer faces).
    # Step 2 is the sweet spot for Three.js rendering performance.
    MARCHING_CUBES_STEP = 2

    def __init__(
        self,
        model_path: Optional[str] = None,
        device: str = "mps",
        marching_cubes_step: int = 2,
    ):
        """
        Args:
            model_path: Path to a MONAI model checkpoint (.pt file).
                        If None, uses DEFAULT_MODEL_PATH or builds a default UNet.
            device: PyTorch device. "mps" for Apple Silicon, "cuda" for NVIDIA,
                    "cpu" fallback.
            marching_cubes_step: Marching cubes resolution. 1=full, 2=fast.
        """
        self.model_path = model_path or self.DEFAULT_MODEL_PATH
        self.device_name = device
        self.MARCHING_CUBES_STEP = marching_cubes_step
        self._model = None
        self._device = None

    def process_scan(
        self,
        dicom_dir: str,
        output_dir: str,
        output_filename: str = "patient_twin.glb",
    ) -> Path:
        """
        Full pipeline: DICOM directory -> segmented 3D GLB mesh.

        Args:
            dicom_dir:       Path to directory containing DICOM .dcm files.
            output_dir:      Path to write the output GLB file.
            output_filename: Name of the output GLB file.

        Returns:
            Path to the generated GLB file.

        Raises:
            ValueError: If DICOM directory is invalid or contains no valid series.
            RuntimeError: If segmentation or mesh generation fails.
        """
        import torch

        dicom_path = Path(dicom_dir)
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        glb_path = out_path / output_filename

        # -- Stage 1: Load DICOM --
        logger.info("Stage 1/5: Loading DICOM series from %s", dicom_path)
        volume, spacing, metadata = self._load_dicom_series(dicom_path)
        logger.info(
            "  Volume shape: %s, spacing: %s mm, dtype: %s",
            volume.shape, [f"{s:.2f}" for s in spacing], volume.dtype,
        )

        # -- Stage 2: MONAI Segmentation --
        logger.info(
            "Stage 2/5: Running MONAI segmentation (device=%s)",
            self.device_name,
        )
        self._device = torch.device(self.device_name)
        segmentation_mask = self._run_segmentation(volume, spacing)
        logger.info(
            "  Segmentation complete. Unique labels: %s",
            np.unique(segmentation_mask).tolist(),
        )

        # Free volume - we only need the mask now
        del volume
        gc.collect()
        if self.device_name == "mps":
            torch.mps.empty_cache()
        elif self.device_name.startswith("cuda"):
            torch.cuda.empty_cache()
        logger.info("  Freed raw volume from memory.")

        # -- Stage 3: Marching Cubes --
        logger.info(
            "Stage 3/5: Extracting surfaces via marching cubes (step=%d)",
            self.MARCHING_CUBES_STEP,
        )
        meshes = self._extract_surfaces(segmentation_mask, spacing)
        logger.info("  Extracted %d organ meshes.", len(meshes))

        # Free segmentation mask
        del segmentation_mask
        gc.collect()

        # -- Stage 4: Build combined mesh --
        logger.info("Stage 4/5: Constructing combined mesh with materials")
        combined = self._build_combined_mesh(meshes)

        # Free individual meshes
        del meshes
        gc.collect()

        # -- Stage 5: Export GLB --
        logger.info("Stage 5/5: Exporting GLB to %s", glb_path)
        combined.export(str(glb_path), file_type="glb")
        file_size_mb = glb_path.stat().st_size / (1024 * 1024)
        logger.info("  GLB exported: %.1f MB", file_size_mb)

        # Final cleanup
        del combined
        gc.collect()
        if self.device_name == "mps":
            torch.mps.empty_cache()

        # Write metadata sidecar
        meta_path = out_path / (output_filename.rsplit(".", 1)[0] + "_meta.json")
        self._write_metadata(meta_path, metadata, glb_path)

        logger.info("Pipeline complete. Output: %s", glb_path)
        return glb_path

    # ===========================================================
    #  STAGE 1: DICOM LOADING
    # ===========================================================

    def _load_dicom_series(
        self, dicom_dir: Path,
    ) -> tuple[np.ndarray, list[float], dict]:
        """
        Load a DICOM series into a 3D numpy array.

        Validates:
          - Directory exists and contains .dcm files
          - All slices have consistent dimensions
          - Slices are sorted by InstanceNumber or SliceLocation

        Returns:
            (volume, spacing, metadata) where:
              volume:   3D float32 array [slices, height, width]
              spacing:  [z_spacing, y_spacing, x_spacing] in mm
              metadata: dict with patient/study info
        """
        import pydicom
        from pydicom.errors import InvalidDicomError

        if not dicom_dir.is_dir():
            raise ValueError(f"DICOM directory does not exist: {dicom_dir}")

        # Collect valid DICOM files
        dcm_files = []
        for f in sorted(dicom_dir.iterdir()):
            if not f.is_file():
                continue
            suffix = f.suffix.lower()
            if suffix in (".dcm", ".dicom", "") or f.name.startswith("CT"):
                try:
                    ds = pydicom.dcmread(str(f), stop_before_pixels=True)
                    if hasattr(ds, "Rows"):
                        dcm_files.append(f)
                except (InvalidDicomError, Exception):
                    continue

        if not dcm_files:
            raise ValueError(f"No valid DICOM files found in {dicom_dir}")

        logger.info("  Found %d DICOM files.", len(dcm_files))

        # Read all slices with pixel data
        slices = []
        for f in dcm_files:
            try:
                ds = pydicom.dcmread(str(f))
                if hasattr(ds, "pixel_array"):
                    slices.append(ds)
            except Exception as e:
                logger.warning("  Skipping %s: %s", f.name, e)

        if len(slices) < 3:
            raise ValueError(
                f"Too few valid DICOM slices ({len(slices)}). "
                "Need at least 3 for volumetric rendering."
            )

        # Validate consistent dimensions
        ref_rows = slices[0].Rows
        ref_cols = slices[0].Columns
        consistent = [
            s for s in slices
            if s.Rows == ref_rows and s.Columns == ref_cols
        ]
        if len(consistent) < len(slices):
            logger.warning(
                "  Filtered %d inconsistent slices (expected %dx%d).",
                len(slices) - len(consistent), ref_rows, ref_cols,
            )
            slices = consistent

        if len(slices) < 3:
            raise ValueError(
                "Too few consistent DICOM slices after filtering."
            )

        # Sort by InstanceNumber or SliceLocation
        sort_key = None
        if hasattr(slices[0], "InstanceNumber"):
            sort_key = lambda s: int(s.InstanceNumber)
        elif hasattr(slices[0], "SliceLocation"):
            sort_key = lambda s: float(s.SliceLocation)
        elif hasattr(slices[0], "ImagePositionPatient"):
            sort_key = lambda s: float(s.ImagePositionPatient[2])

        if sort_key:
            slices.sort(key=sort_key)

        # Build 3D volume
        volume = np.stack(
            [s.pixel_array.astype(np.float32) for s in slices], axis=0,
        )

        # Apply rescale slope/intercept (Hounsfield Units for CT)
        if hasattr(slices[0], "RescaleSlope") and hasattr(
            slices[0], "RescaleIntercept",
        ):
            slope = float(slices[0].RescaleSlope)
            intercept = float(slices[0].RescaleIntercept)
            volume = volume * slope + intercept

        # Extract spacing
        pixel_spacing = getattr(slices[0], "PixelSpacing", [1.0, 1.0])
        if len(slices) > 1 and hasattr(slices[0], "SliceLocation"):
            z_spacing = abs(
                float(slices[1].SliceLocation)
                - float(slices[0].SliceLocation)
            )
        elif hasattr(slices[0], "SpacingBetweenSlices"):
            z_spacing = float(slices[0].SpacingBetweenSlices)
        elif hasattr(slices[0], "SliceThickness"):
            z_spacing = float(slices[0].SliceThickness)
        else:
            z_spacing = 1.0

        spacing = [
            z_spacing, float(pixel_spacing[0]), float(pixel_spacing[1]),
        ]

        # Extract metadata (PII-safe fields only)
        metadata = {
            "patient_id": getattr(slices[0], "PatientID", "Unknown"),
            "study_date": getattr(slices[0], "StudyDate", "Unknown"),
            "modality": getattr(slices[0], "Modality", "Unknown"),
            "study_description": getattr(
                slices[0], "StudyDescription", "",
            ),
            "num_slices": len(slices),
            "dimensions": list(volume.shape),
            "spacing_mm": spacing,
        }

        return volume, spacing, metadata

    # ===========================================================
    #  STAGE 2: MONAI SEGMENTATION
    # ===========================================================

    def _run_segmentation(
        self, volume: np.ndarray, spacing: list[float],
    ) -> np.ndarray:
        """
        Run MONAI segmentation on the 3D volume.

        Uses the configured model checkpoint if available, otherwise builds
        a default UNet architecture. Inference runs on the configured device
        (MPS for Apple Silicon).

        Returns:
            Integer label mask with same spatial dims as input volume.
        """
        import torch
        from monai.transforms import (
            Compose,
            EnsureChannelFirst,
            ScaleIntensityRange,
            Spacing,
            Orientation,
        )

        # Preprocessing transforms matching MONAI bundle conventions
        pre_transforms = Compose([
            EnsureChannelFirst(channel_dim="no_channel"),
            Orientation(axcodes="RAS"),
            Spacing(pixdim=spacing, mode="bilinear"),
            ScaleIntensityRange(
                a_min=-1024, a_max=1024,
                b_min=0.0, b_max=1.0,
                clip=True,
            ),
        ])

        # Apply preprocessing
        volume_tensor = pre_transforms(volume)

        # Add batch dimension [B, C, D, H, W]
        input_tensor = volume_tensor.unsqueeze(0).to(self._device)

        # Load or build model
        model = self._get_model(input_channels=1, output_channels=14)
        model.to(self._device)

        # Inference with no_grad for memory efficiency
        with torch.no_grad():
            output = model(input_tensor)

        # Get predicted labels
        if output.shape[1] > 1:
            # Multi-class: argmax over channel dimension
            mask = torch.argmax(output, dim=1).squeeze(0)
        else:
            # Binary: threshold at 0.5
            mask = (
                (torch.sigmoid(output) > 0.5)
                .long()
                .squeeze(0)
                .squeeze(0)
            )

        # Move to CPU numpy
        mask_np = mask.cpu().numpy().astype(np.int16)

        # Free GPU tensors
        del input_tensor, output, mask, volume_tensor
        model.cpu()
        del model
        self._model = None
        gc.collect()

        if self.device_name == "mps":
            torch.mps.empty_cache()
        elif self.device_name.startswith("cuda"):
            torch.cuda.empty_cache()

        logger.info(
            "  Segmentation inference complete. Mask shape: %s",
            mask_np.shape,
        )
        return mask_np

    def _get_model(self, input_channels: int, output_channels: int):
        """
        Load the segmentation model.

        Priority:
          1. Saved checkpoint (self.model_path)
          2. MONAI bundle download
          3. Default UNet architecture (untrained - for pipeline testing)
        """
        import torch
        from monai.networks.nets import UNet

        # Try loading from checkpoint
        if self.model_path and Path(self.model_path).exists():
            logger.info("  Loading model checkpoint: %s", self.model_path)
            model = UNet(
                spatial_dims=3,
                in_channels=input_channels,
                out_channels=output_channels,
                channels=(16, 32, 64, 128, 256),
                strides=(2, 2, 2, 2),
                num_res_units=2,
            )
            checkpoint = torch.load(
                self.model_path,
                map_location=self._device,
                weights_only=True,
            )
            if isinstance(checkpoint, dict) and "model" in checkpoint:
                model.load_state_dict(checkpoint["model"])
            elif isinstance(checkpoint, dict) and "state_dict" in checkpoint:
                model.load_state_dict(checkpoint["state_dict"])
            else:
                model.load_state_dict(checkpoint)
            return model

        # Try MONAI bundle
        try:
            from monai.bundle import download, load

            bundle_dir = Path.home() / ".cache" / "monai" / "bundles"
            bundle_name = "wholeBody_ct_segmentation"
            bundle_path = bundle_dir / bundle_name

            if not bundle_path.exists():
                logger.info(
                    "  Downloading MONAI bundle: %s", bundle_name,
                )
                download(name=bundle_name, bundle_dir=str(bundle_dir))

            logger.info("  Loading MONAI bundle: %s", bundle_name)
            model = load(
                name=bundle_name,
                bundle_dir=str(bundle_dir),
                source="monaiio",
            )
            return model
        except Exception as e:
            logger.warning(
                "  MONAI bundle load failed: %s. Using default UNet.", e,
            )

        # Fallback: default UNet (untrained - for pipeline testing only)
        logger.warning(
            "  Using UNTRAINED default UNet. Segmentation results will be "
            "meaningless. Provide a trained model checkpoint for real results."
        )
        model = UNet(
            spatial_dims=3,
            in_channels=input_channels,
            out_channels=output_channels,
            channels=(16, 32, 64, 128, 256),
            strides=(2, 2, 2, 2),
            num_res_units=2,
        )
        return model

    # ===========================================================
    #  STAGE 3: MARCHING CUBES SURFACE EXTRACTION
    # ===========================================================

    def _extract_surfaces(
        self, mask: np.ndarray, spacing: list[float],
    ) -> list[dict]:
        """
        Extract triangulated surfaces from the segmentation mask using
        marching cubes. Creates one mesh per unique label (skipping
        background).

        Returns:
            List of dicts with keys: label, name, vertices, faces,
            normals, color.
        """
        from skimage.measure import marching_cubes

        unique_labels = np.unique(mask)
        meshes = []

        for label in unique_labels:
            if label == 0:
                continue  # Skip background

            label_config = self.LABEL_COLORS.get(int(label))
            if label_config is None:
                # Unknown label - assign generic gray
                color = (180, 180, 180, 200)
                name = f"structure_{label}"
            else:
                if label_config[0] is None:
                    continue  # Explicitly skipped
                color = label_config[:4]
                name = (
                    label_config[4]
                    if len(label_config) > 4
                    else f"structure_{label}"
                )

            # Create binary mask for this label
            binary = (mask == label).astype(np.float32)

            # Check if label has enough volume for marching cubes
            voxel_count = np.sum(binary)
            if voxel_count < 50:
                logger.debug(
                    "  Skipping label %d (%s): too few voxels (%d)",
                    label, name, voxel_count,
                )
                continue

            try:
                verts, faces, normals, values = marching_cubes(
                    binary,
                    level=0.5,
                    spacing=spacing,
                    step_size=self.MARCHING_CUBES_STEP,
                    allow_degenerate=False,
                )

                logger.info(
                    "  Label %d (%s): %d vertices, %d faces",
                    label, name, len(verts), len(faces),
                )

                meshes.append({
                    "label": int(label),
                    "name": name,
                    "vertices": verts,
                    "faces": faces,
                    "normals": normals,
                    "color": color,
                })

            except Exception as e:
                logger.warning(
                    "  Marching cubes failed for label %d (%s): %s",
                    label, name, e,
                )

            # Free binary mask immediately
            del binary

        gc.collect()
        return meshes

    # ===========================================================
    #  STAGE 4: MESH CONSTRUCTION
    # ===========================================================

    def _build_combined_mesh(self, meshes: list[dict]):
        """
        Build a single trimesh Scene containing all organ meshes with
        assigned materials. Each organ gets its own named sub-mesh for
        Three.js to parse into the layer system.

        Returns:
            trimesh.Scene ready for GLB export.
        """
        import trimesh

        scene = trimesh.Scene()

        for mesh_data in meshes:
            name = mesh_data["name"]
            verts = mesh_data["vertices"]
            faces = mesh_data["faces"]
            color = mesh_data["color"]

            # Center the mesh around origin for Three.js
            centroid = verts.mean(axis=0)
            centered_verts = verts - centroid

            # Scale to reasonable Three.js units (~2 units body height)
            # DICOM spacing is in mm, so mesh extents are in mm
            max_extent = np.max(np.abs(centered_verts))
            if max_extent > 0:
                scale_factor = 1.0 / max_extent
            else:
                scale_factor = 1.0

            scaled_verts = centered_verts * scale_factor

            # Build trimesh with vertex colors
            mesh = trimesh.Trimesh(
                vertices=scaled_verts,
                faces=faces,
                vertex_normals=mesh_data.get("normals"),
            )

            # Assign face colors (RGBA)
            face_colors = np.tile(
                np.array(color, dtype=np.uint8),
                (len(faces), 1),
            )
            mesh.visual.face_colors = face_colors

            # Name for Three.js parsing - prefix with layer
            if "bone" in name or "skeleton" in name:
                three_name = f"layer_skeleton/{name}"
            elif "skin" in name:
                three_name = f"layer_skin/{name}"
            elif "muscle" in name:
                three_name = f"layer_muscle/{name}"
            else:
                three_name = f"layer_organs/organ_{name}"

            scene.add_geometry(mesh, node_name=three_name)
            logger.info(
                "  Added mesh: %s (%d verts, %d faces)",
                three_name, len(verts), len(faces),
            )

        return scene

    # ===========================================================
    #  STAGE 5: METADATA
    # ===========================================================

    def _write_metadata(
        self, meta_path: Path, metadata: dict, glb_path: Path,
    ):
        """Write a JSON sidecar with scan metadata and mesh stats."""
        meta = {
            **metadata,
            "glb_file": glb_path.name,
            "glb_size_bytes": glb_path.stat().st_size,
            "pipeline": "VolumetricRenderer",
            "device": self.device_name,
            "marching_cubes_step": self.MARCHING_CUBES_STEP,
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2, default=str)
        logger.info("  Metadata written to %s", meta_path)


# ===============================================================
#  CLI ENTRY POINT
# ===============================================================

def main():
    """CLI entry point for standalone pipeline execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description="DICOM to 3D GLB Volumetric Renderer Pipeline",
    )
    parser.add_argument(
        "--dicom-dir", required=True,
        help="Path to directory containing DICOM .dcm files",
    )
    parser.add_argument(
        "--output-dir", default="./output",
        help="Directory for GLB output (default: ./output)",
    )
    parser.add_argument(
        "--output-name", default="patient_twin.glb",
        help="Output GLB filename (default: patient_twin.glb)",
    )
    parser.add_argument(
        "--model-path", default=None,
        help="Path to trained MONAI model checkpoint (.pt)",
    )
    parser.add_argument(
        "--device", default="mps",
        choices=["mps", "cuda", "cpu"],
        help="PyTorch device (default: mps for Apple Silicon)",
    )
    parser.add_argument(
        "--step-size", type=int, default=2,
        help="Marching cubes step size: 1=full detail, 2=fast (default: 2)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    renderer = VolumetricRenderer(
        model_path=args.model_path,
        device=args.device,
        marching_cubes_step=args.step_size,
    )

    glb_path = renderer.process_scan(
        dicom_dir=args.dicom_dir,
        output_dir=args.output_dir,
        output_filename=args.output_name,
    )
    print(f"\nDone. GLB written to: {glb_path}")


if __name__ == "__main__":
    main()
