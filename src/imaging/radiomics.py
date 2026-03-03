"""
Clinical Intelligence Hub — Deep Radiomics Feature Extraction

Quantitative image feature extraction from segmentation masks and regions
of interest. Produces numeric descriptors that feed into the Snowball
differential and generate flags when values cross clinical thresholds.

Feature categories:
  1. Intensity Statistics  — mean, std, skewness, kurtosis, entropy
  2. Shape Descriptors     — volume, sphericity, elongation, compactness
  3. GLCM Texture          — contrast, correlation, energy, homogeneity
  4. First-Order Histogram — percentiles, interquartile range, uniformity

Uses only scipy + numpy (no pyradiomics required, though it can enhance
results when available). All features are computed from numpy arrays so
they work with any imaging pipeline output.

Integration:
  - Called after MONAI segmentation produces a mask
  - Features stored in ImagingFinding.radiomic_features dict
  - Snowball consumes features as numeric findings
  - Threshold crossings generate ClinicalFlag entries
"""

import logging
import math
from typing import Optional

import numpy as np

logger = logging.getLogger("CIH-Radiomics")


# ── Clinical Thresholds ──────────────────────────────────────
# When a radiomic feature crosses these, generate a flag.
# Based on published radiomics literature for common findings.

CLINICAL_THRESHOLDS = {
    "lung_nodule": {
        "volume_mm3": {
            "warn": 500,     # > 500mm³ → suspicious
            "alert": 2000,   # > 2000mm³ → highly suspicious
            "description": "Nodule volume",
        },
        "sphericity": {
            "warn_below": 0.6,  # Irregular shape more concerning
            "description": "Nodule sphericity (1.0 = perfect sphere)",
        },
        "glcm_contrast": {
            "warn": 200,     # High contrast → heterogeneous
            "description": "Texture heterogeneity",
        },
        "intensity_entropy": {
            "warn": 4.5,     # High entropy → mixed composition
            "description": "Intensity entropy (tissue complexity)",
        },
    },
    "brain_tumor": {
        "volume_mm3": {
            "warn": 5000,
            "alert": 20000,
            "description": "Tumor volume",
        },
        "elongation": {
            "warn": 0.7,     # Elongated tumors = infiltrative
            "description": "Tumor elongation",
        },
        "intensity_skewness": {
            "warn": 1.5,
            "warn_below": -1.5,
            "description": "Intensity distribution asymmetry",
        },
    },
    "organ": {
        "volume_ml": {
            # Per-organ thresholds are context-dependent;
            # flag when volume deviates >30% from population mean
            "description": "Organ volume",
        },
    },
}


class RadiomicsEngine:
    """
    Extracts quantitative radiomic features from image arrays and masks.

    Can process:
      - 3D volumes (from CT/MRI segmentation)
      - 2D regions (from pathology or X-ray)
      - Pre-computed measurement dicts (enriches with additional features)
    """

    def __init__(self):
        self._has_scipy = self._check_scipy()
        if not self._has_scipy:
            logger.warning(
                "scipy not available — GLCM texture features disabled. "
                "Install with: pip install scipy"
            )

    # ── Public API ──────────────────────────────────────────

    def extract_features(
        self,
        image: np.ndarray,
        mask: Optional[np.ndarray] = None,
        label: int = 1,
        voxel_spacing: tuple = (1.0, 1.0, 1.0),
        context: str = "general",
    ) -> dict:
        """
        Extract all radiomic features from an image region.

        Args:
            image: The image array (2D or 3D).
            mask: Binary or label mask. If None, uses entire image.
            label: Which label value in the mask to analyze.
            voxel_spacing: Physical spacing (mm) per voxel dimension.
            context: Clinical context for threshold checking
                     ('lung_nodule', 'brain_tumor', 'organ', 'general').

        Returns:
            Dict with feature categories: intensity, shape, texture, histogram,
            plus threshold_flags list.
        """
        if image is None or image.size == 0:
            return {"error": "Empty image array"}

        # Extract the region of interest
        if mask is not None:
            roi_mask = mask == label
            roi_values = image[roi_mask].astype(float)
        else:
            roi_mask = np.ones(image.shape, dtype=bool)
            roi_values = image.flatten().astype(float)

        if roi_values.size == 0:
            return {"error": "Empty ROI — no voxels match label"}

        features = {}

        # 1. Intensity statistics
        features["intensity"] = self._compute_intensity(roi_values)

        # 2. Shape descriptors (need the mask)
        if mask is not None:
            features["shape"] = self._compute_shape(
                roi_mask, voxel_spacing
            )

        # 3. GLCM texture (need 2D slices or the full array)
        if self._has_scipy:
            features["texture"] = self._compute_glcm_texture(
                image, roi_mask
            )

        # 4. First-order histogram
        features["histogram"] = self._compute_histogram(roi_values)

        # 5. Check clinical thresholds
        features["threshold_flags"] = self._check_thresholds(
            features, context
        )

        # Flatten for easy storage
        features["summary"] = self._flatten_summary(features)

        return features

    def extract_from_measurements(
        self,
        measurements: dict,
        context: str = "general",
    ) -> dict:
        """
        Enrich existing MONAI measurements with threshold analysis.

        This is a lightweight path for when we already have measurements
        (volume, diameter) from MONAI but want threshold flagging.

        Args:
            measurements: Dict from ImagingFinding.measurements
            context: Clinical context for thresholds.

        Returns:
            Dict with threshold_flags and risk_level.
        """
        if not measurements:
            return {"threshold_flags": [], "risk_level": "unknown"}

        flags = []
        thresholds = CLINICAL_THRESHOLDS.get(context, {})

        for key, value in measurements.items():
            if not isinstance(value, (int, float)):
                continue

            # Check against known thresholds
            for threshold_key, bounds in thresholds.items():
                if threshold_key in key:
                    desc = bounds.get("description", key)

                    if "alert" in bounds and value > bounds["alert"]:
                        flags.append({
                            "feature": key,
                            "value": round(value, 2),
                            "threshold": bounds["alert"],
                            "level": "high",
                            "message": (
                                f"{desc}: {value:.1f} exceeds alert "
                                f"threshold ({bounds['alert']})"
                            ),
                        })
                    elif "warn" in bounds and value > bounds["warn"]:
                        flags.append({
                            "feature": key,
                            "value": round(value, 2),
                            "threshold": bounds["warn"],
                            "level": "moderate",
                            "message": (
                                f"{desc}: {value:.1f} exceeds warning "
                                f"threshold ({bounds['warn']})"
                            ),
                        })

                    if "warn_below" in bounds and value < bounds["warn_below"]:
                        flags.append({
                            "feature": key,
                            "value": round(value, 2),
                            "threshold": bounds["warn_below"],
                            "level": "moderate",
                            "message": (
                                f"{desc}: {value:.2f} below warning "
                                f"threshold ({bounds['warn_below']})"
                            ),
                        })

        risk_level = "low"
        if any(f["level"] == "high" for f in flags):
            risk_level = "high"
        elif any(f["level"] == "moderate" for f in flags):
            risk_level = "moderate"

        return {
            "threshold_flags": flags,
            "risk_level": risk_level,
        }

    # ── Intensity Statistics ──────────────────────────────────

    @staticmethod
    def _compute_intensity(values: np.ndarray) -> dict:
        """First-order intensity statistics of the ROI."""
        n = values.size
        if n == 0:
            return {}

        mean_val = float(np.mean(values))
        std_val = float(np.std(values))
        min_val = float(np.min(values))
        max_val = float(np.max(values))
        median_val = float(np.median(values))

        # Skewness
        if std_val > 0:
            skewness = float(np.mean(((values - mean_val) / std_val) ** 3))
        else:
            skewness = 0.0

        # Kurtosis (excess kurtosis, so normal = 0)
        if std_val > 0:
            kurtosis = float(
                np.mean(((values - mean_val) / std_val) ** 4) - 3.0
            )
        else:
            kurtosis = 0.0

        # Entropy (discretized)
        hist, _ = np.histogram(values, bins=64, density=True)
        hist = hist[hist > 0]
        bin_width = (max_val - min_val) / 64 if max_val > min_val else 1.0
        probs = hist * bin_width
        probs = probs[probs > 0]
        entropy = float(-np.sum(probs * np.log2(probs))) if len(probs) > 0 else 0.0

        # Energy (sum of squared values, normalized)
        energy = float(np.sum(values ** 2)) / n

        return {
            "mean": round(mean_val, 3),
            "std": round(std_val, 3),
            "min": round(min_val, 3),
            "max": round(max_val, 3),
            "median": round(median_val, 3),
            "skewness": round(skewness, 4),
            "kurtosis": round(kurtosis, 4),
            "entropy": round(entropy, 4),
            "energy": round(energy, 3),
            "range": round(max_val - min_val, 3),
            "voxel_count": n,
        }

    # ── Shape Descriptors ─────────────────────────────────────

    @staticmethod
    def _compute_shape(
        binary_mask: np.ndarray,
        voxel_spacing: tuple = (1.0, 1.0, 1.0),
    ) -> dict:
        """Geometric shape features from a binary mask."""
        voxel_count = int(np.sum(binary_mask))
        if voxel_count == 0:
            return {}

        # Volume
        voxel_vol = 1.0
        for s in voxel_spacing:
            voxel_vol *= s
        volume_mm3 = voxel_count * voxel_vol

        # Bounding box dimensions
        coords = np.argwhere(binary_mask)
        bbox_min = coords.min(axis=0)
        bbox_max = coords.max(axis=0)
        bbox_size = (bbox_max - bbox_min + 1).astype(float)

        # Physical bounding box (mm)
        physical_bbox = bbox_size * np.array(voxel_spacing[:len(bbox_size)])

        # Elongation (ratio of two largest axes)
        sorted_dims = np.sort(physical_bbox)[::-1]
        if len(sorted_dims) >= 2 and sorted_dims[0] > 0:
            elongation = float(sorted_dims[1] / sorted_dims[0])
        else:
            elongation = 1.0

        # Flatness (ratio of smallest to largest axis)
        if len(sorted_dims) >= 3 and sorted_dims[0] > 0:
            flatness = float(sorted_dims[2] / sorted_dims[0])
        else:
            flatness = elongation

        # Surface area estimate (count boundary voxels)
        # A voxel is on the surface if any neighbor is outside the mask
        surface_voxels = _count_surface_voxels(binary_mask)
        surface_area_mm2 = surface_voxels * (voxel_vol ** (2.0 / 3.0))

        # Sphericity = (π^(1/3) * (6V)^(2/3)) / A
        if surface_area_mm2 > 0:
            sphericity = (
                (math.pi ** (1.0 / 3.0))
                * ((6.0 * volume_mm3) ** (2.0 / 3.0))
                / surface_area_mm2
            )
            sphericity = min(sphericity, 1.0)  # Clamp to [0, 1]
        else:
            sphericity = 0.0

        # Compactness = V / (bbox volume)
        bbox_volume = float(np.prod(physical_bbox))
        compactness = volume_mm3 / bbox_volume if bbox_volume > 0 else 0.0

        # Max diameter (longest axis of the region)
        max_diameter_mm = float(np.max(physical_bbox))

        result = {
            "volume_mm3": round(volume_mm3, 2),
            "volume_ml": round(volume_mm3 / 1000.0, 3),
            "surface_area_mm2": round(surface_area_mm2, 2),
            "sphericity": round(sphericity, 4),
            "elongation": round(elongation, 4),
            "flatness": round(flatness, 4),
            "compactness": round(compactness, 4),
            "max_diameter_mm": round(max_diameter_mm, 2),
            "voxel_count": voxel_count,
        }

        if len(physical_bbox) >= 3:
            result["bbox_mm"] = [round(d, 1) for d in physical_bbox.tolist()]

        return result

    # ── GLCM Texture Features ─────────────────────────────────

    def _compute_glcm_texture(
        self,
        image: np.ndarray,
        mask: np.ndarray,
    ) -> dict:
        """
        Gray-Level Co-occurrence Matrix texture features.

        Computes on the largest 2D slice through the ROI to keep
        computation fast. For 3D, selects the axial slice with the
        most ROI voxels.
        """
        if not self._has_scipy:
            return {}

        # Get the best 2D slice
        if image.ndim == 3:
            # Find the axial slice with the most mask voxels
            slice_counts = np.sum(mask, axis=(1, 2)) if mask.ndim == 3 else np.sum(mask, axis=1)
            best_slice = int(np.argmax(slice_counts))
            img_2d = image[best_slice].astype(float)
            mask_2d = mask[best_slice] if mask.ndim == 3 else mask
        elif image.ndim == 2:
            img_2d = image.astype(float)
            mask_2d = mask if mask.ndim == 2 else mask.reshape(image.shape)
        else:
            return {}

        # Quantize to 32 gray levels for GLCM
        roi_vals = img_2d[mask_2d > 0]
        if roi_vals.size < 4:
            return {}

        vmin, vmax = float(roi_vals.min()), float(roi_vals.max())
        if vmax <= vmin:
            return {}

        levels = 32
        quantized = np.clip(
            ((img_2d - vmin) / (vmax - vmin) * (levels - 1)).astype(int),
            0, levels - 1,
        )

        # Build GLCM for 4 directions, distance=1
        glcm = _build_glcm(quantized, mask_2d, levels=levels, distances=[1])

        if glcm is None or glcm.sum() == 0:
            return {}

        # Normalize
        glcm_norm = glcm.astype(float) / glcm.sum()

        # Features
        i_indices, j_indices = np.meshgrid(
            np.arange(levels), np.arange(levels), indexing="ij"
        )

        # Contrast: sum of (i-j)^2 * P(i,j)
        contrast = float(np.sum((i_indices - j_indices) ** 2 * glcm_norm))

        # Homogeneity (Inverse Difference Moment)
        homogeneity = float(
            np.sum(glcm_norm / (1.0 + (i_indices - j_indices) ** 2))
        )

        # Energy (Angular Second Moment)
        energy = float(np.sum(glcm_norm ** 2))

        # Correlation
        mu_i = float(np.sum(i_indices * glcm_norm))
        mu_j = float(np.sum(j_indices * glcm_norm))
        sigma_i = float(np.sqrt(np.sum((i_indices - mu_i) ** 2 * glcm_norm)))
        sigma_j = float(np.sqrt(np.sum((j_indices - mu_j) ** 2 * glcm_norm)))

        if sigma_i > 0 and sigma_j > 0:
            correlation = float(
                np.sum(
                    (i_indices - mu_i) * (j_indices - mu_j) * glcm_norm
                ) / (sigma_i * sigma_j)
            )
        else:
            correlation = 0.0

        # Entropy
        nonzero = glcm_norm[glcm_norm > 0]
        glcm_entropy = float(-np.sum(nonzero * np.log2(nonzero)))

        # Dissimilarity
        dissimilarity = float(
            np.sum(np.abs(i_indices - j_indices) * glcm_norm)
        )

        return {
            "glcm_contrast": round(contrast, 4),
            "glcm_homogeneity": round(homogeneity, 4),
            "glcm_energy": round(energy, 6),
            "glcm_correlation": round(correlation, 4),
            "glcm_entropy": round(glcm_entropy, 4),
            "glcm_dissimilarity": round(dissimilarity, 4),
            "quantization_levels": levels,
        }

    # ── Histogram Features ────────────────────────────────────

    @staticmethod
    def _compute_histogram(values: np.ndarray) -> dict:
        """First-order histogram features."""
        if values.size == 0:
            return {}

        p10 = float(np.percentile(values, 10))
        p25 = float(np.percentile(values, 25))
        p75 = float(np.percentile(values, 75))
        p90 = float(np.percentile(values, 90))
        iqr = p75 - p25

        # Mean absolute deviation
        mad = float(np.mean(np.abs(values - np.mean(values))))

        # Coefficient of variation
        mean_val = float(np.mean(values))
        std_val = float(np.std(values))
        cv = std_val / abs(mean_val) if abs(mean_val) > 1e-10 else 0.0

        # Uniformity (sum of squared histogram probabilities)
        hist, _ = np.histogram(values, bins=64, density=True)
        bin_width = (float(np.max(values)) - float(np.min(values))) / 64
        if bin_width > 0:
            probs = hist * bin_width
            uniformity = float(np.sum(probs ** 2))
        else:
            uniformity = 1.0

        return {
            "p10": round(p10, 3),
            "p25": round(p25, 3),
            "p75": round(p75, 3),
            "p90": round(p90, 3),
            "iqr": round(iqr, 3),
            "mean_absolute_deviation": round(mad, 3),
            "coefficient_of_variation": round(cv, 4),
            "uniformity": round(uniformity, 6),
        }

    # ── Threshold Checking ────────────────────────────────────

    def _check_thresholds(self, features: dict, context: str) -> list:
        """Check extracted features against clinical thresholds."""
        thresholds = CLINICAL_THRESHOLDS.get(context, {})
        flags = []

        # Flatten all features for comparison
        flat = {}
        for category, cat_features in features.items():
            if isinstance(cat_features, dict):
                for key, value in cat_features.items():
                    if isinstance(value, (int, float)):
                        flat[key] = value

        for threshold_key, bounds in thresholds.items():
            desc = bounds.get("description", threshold_key)

            # Find matching feature (partial match)
            for feat_key, feat_value in flat.items():
                if threshold_key not in feat_key:
                    continue

                if "alert" in bounds and feat_value > bounds["alert"]:
                    flags.append({
                        "feature": feat_key,
                        "value": round(feat_value, 2),
                        "threshold": bounds["alert"],
                        "level": "high",
                        "message": (
                            f"{desc}: {feat_value:.2f} exceeds alert "
                            f"threshold ({bounds['alert']})"
                        ),
                    })
                elif "warn" in bounds and feat_value > bounds["warn"]:
                    flags.append({
                        "feature": feat_key,
                        "value": round(feat_value, 2),
                        "threshold": bounds["warn"],
                        "level": "moderate",
                        "message": (
                            f"{desc}: {feat_value:.2f} exceeds warning "
                            f"threshold ({bounds['warn']})"
                        ),
                    })

                if "warn_below" in bounds and feat_value < bounds["warn_below"]:
                    flags.append({
                        "feature": feat_key,
                        "value": round(feat_value, 2),
                        "threshold": bounds["warn_below"],
                        "level": "moderate",
                        "message": (
                            f"{desc}: {feat_value:.2f} below warning "
                            f"threshold ({bounds['warn_below']})"
                        ),
                    })

        return flags

    # ── Summary Flattening ────────────────────────────────────

    @staticmethod
    def _flatten_summary(features: dict) -> dict:
        """Flatten nested features into a single dict for storage."""
        flat = {}
        for category in ("intensity", "shape", "texture", "histogram"):
            cat_dict = features.get(category, {})
            if isinstance(cat_dict, dict):
                for key, value in cat_dict.items():
                    if isinstance(value, (int, float)):
                        flat[f"{category}_{key}"] = value
        return flat

    # ── Dependency Checks ─────────────────────────────────────

    @staticmethod
    def _check_scipy() -> bool:
        """Check if scipy is available."""
        try:
            from scipy import ndimage  # noqa: F401
            return True
        except ImportError:
            return False


# ── Module-Level Helpers ──────────────────────────────────────

def _count_surface_voxels(mask: np.ndarray) -> int:
    """Count voxels on the surface of a binary mask."""
    surface_count = 0
    ndim = mask.ndim

    for axis in range(ndim):
        # Shift forward and backward along each axis
        slices_fwd = [slice(None)] * ndim
        slices_bwd = [slice(None)] * ndim

        slices_fwd[axis] = slice(1, None)
        slices_bwd[axis] = slice(None, -1)

        # A voxel is on the surface if it differs from its neighbor
        diff_fwd = mask[tuple(slices_bwd)] != mask[tuple(slices_fwd)]
        surface_count += int(np.sum(diff_fwd & mask[tuple(slices_bwd)]))
        surface_count += int(np.sum(diff_fwd & mask[tuple(slices_fwd)]))

    # Also count edge voxels (touching array boundary)
    for axis in range(ndim):
        slices_start = [slice(None)] * ndim
        slices_end = [slice(None)] * ndim
        slices_start[axis] = 0
        slices_end[axis] = -1
        surface_count += int(np.sum(mask[tuple(slices_start)]))
        surface_count += int(np.sum(mask[tuple(slices_end)]))

    return surface_count


def _build_glcm(
    quantized: np.ndarray,
    mask: np.ndarray,
    levels: int = 32,
    distances: list = None,
) -> Optional[np.ndarray]:
    """
    Build a Gray-Level Co-occurrence Matrix from a 2D quantized image.

    Averages over 4 directions (0°, 45°, 90°, 135°) at each distance.
    """
    if distances is None:
        distances = [1]

    glcm = np.zeros((levels, levels), dtype=np.int64)

    # Direction offsets: (dy, dx) for 0°, 45°, 90°, 135°
    directions = [(0, 1), (-1, 1), (-1, 0), (-1, -1)]

    rows, cols = quantized.shape

    for d in distances:
        for dy, dx in directions:
            for y in range(max(0, -dy * d), min(rows, rows - dy * d)):
                for x in range(max(0, -dx * d), min(cols, cols - dx * d)):
                    ny, nx = y + dy * d, x + dx * d

                    # Both pixels must be in the ROI
                    if mask[y, x] and mask[ny, nx]:
                        i = quantized[y, x]
                        j = quantized[ny, nx]
                        if 0 <= i < levels and 0 <= j < levels:
                            glcm[i, j] += 1
                            glcm[j, i] += 1  # Symmetric

    return glcm if glcm.sum() > 0 else None
