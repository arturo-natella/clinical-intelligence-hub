"""Contract for wiring VolumetricRenderer into the imaging pass.

VolumetricRenderer turns a DICOM series into a patient-specific GLB mesh
for the Body Map. It shipped fully orphaned — nothing imported it.

The gating matters more than the wiring. VolumetricRenderer._get_model
falls back to an *untrained* UNet when no checkpoint is available, and
warns that "segmentation results will be meaningless". Rendering that as
the patient's own anatomy would be worse than showing nothing, so twin
generation runs only with a real trained checkpoint, and is opt-in
because a full-volume MONAI inference is expensive and must not collide
with the pipeline's sequential model loading.
"""

from pathlib import Path

import pytest

from src.imaging import volumetric_twin as twin


class FakeRenderer:
    """Stands in for VolumetricRenderer so tests need no torch/MONAI."""

    def __init__(self, *args, **kwargs):
        FakeRenderer.constructed += 1
        self.kwargs = kwargs

    def process_scan(self, dicom_dir, output_dir, output_filename="patient_twin.glb"):
        FakeRenderer.calls.append((dicom_dir, output_dir, output_filename))
        out = Path(output_dir) / output_filename
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"glTF-fake")
        return out

    @classmethod
    def reset(cls):
        cls.constructed = 0
        cls.calls = []


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    FakeRenderer.reset()
    monkeypatch.delenv("MEDPREP_VOLUMETRIC_TWIN", raising=False)
    monkeypatch.delenv("MEDPREP_VOLUMETRIC_MODEL", raising=False)


def _dicom_items(tmp_path):
    scan = tmp_path / "scan"
    scan.mkdir(exist_ok=True)
    slice_file = scan / "slice1.dcm"
    slice_file.write_bytes(b"DICM")
    return [{
        "file_type": "dicom",
        "filepath": str(slice_file),
        "filename": "slice1.dcm",
    }]


def _checkpoint(tmp_path):
    ckpt = tmp_path / "seg_model.pt"
    ckpt.write_bytes(b"weights")
    return ckpt


def test_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDPREP_VOLUMETRIC_MODEL", str(_checkpoint(tmp_path)))
    result = twin.maybe_generate_twin(
        _dicom_items(tmp_path), tmp_path / "out", renderer_factory=FakeRenderer,
    )
    assert result is None
    assert FakeRenderer.constructed == 0


def test_untrained_model_never_produces_a_patient_mesh(tmp_path, monkeypatch):
    """The safety gate: no trained checkpoint means no mesh at all."""
    monkeypatch.setenv("MEDPREP_VOLUMETRIC_TWIN", "1")
    result = twin.maybe_generate_twin(
        _dicom_items(tmp_path), tmp_path / "out", renderer_factory=FakeRenderer,
    )
    assert result is None
    assert FakeRenderer.constructed == 0, (
        "renderer must not run without a trained checkpoint — an untrained "
        "UNet yields meaningless anatomy"
    )


def test_checkpoint_pointing_at_a_missing_file_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDPREP_VOLUMETRIC_TWIN", "1")
    monkeypatch.setenv("MEDPREP_VOLUMETRIC_MODEL", str(tmp_path / "absent.pt"))
    assert twin.maybe_generate_twin(
        _dicom_items(tmp_path), tmp_path / "out", renderer_factory=FakeRenderer,
    ) is None
    assert FakeRenderer.constructed == 0


def test_no_dicom_input_means_no_work(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDPREP_VOLUMETRIC_TWIN", "1")
    monkeypatch.setenv("MEDPREP_VOLUMETRIC_MODEL", str(_checkpoint(tmp_path)))
    items = [{"file_type": "pdf_text", "filepath": "/tmp/x.pdf", "filename": "x.pdf"}]
    assert twin.maybe_generate_twin(
        items, tmp_path / "out", renderer_factory=FakeRenderer,
    ) is None
    assert FakeRenderer.constructed == 0


def test_generates_mesh_when_fully_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDPREP_VOLUMETRIC_TWIN", "1")
    ckpt = _checkpoint(tmp_path)
    monkeypatch.setenv("MEDPREP_VOLUMETRIC_MODEL", str(ckpt))
    out_dir = tmp_path / "out"

    result = twin.maybe_generate_twin(
        _dicom_items(tmp_path), out_dir, renderer_factory=FakeRenderer,
    )

    assert result is not None
    assert FakeRenderer.constructed == 1
    assert Path(result["path"]).exists()
    # Served through the existing /models/<path> route.
    assert result["url"].startswith("/models/")
    assert result["generated_at"]
    # The renderer receives the DICOM *directory*, not one slice file.
    dicom_dir, _, _ = FakeRenderer.calls[0]
    assert Path(dicom_dir).is_dir()
    assert FakeRenderer.constructed == 1


def test_renderer_failure_never_breaks_the_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDPREP_VOLUMETRIC_TWIN", "1")
    monkeypatch.setenv("MEDPREP_VOLUMETRIC_MODEL", str(_checkpoint(tmp_path)))

    class Exploding(FakeRenderer):
        def process_scan(self, *a, **k):
            raise RuntimeError("MPS out of memory")

    assert twin.maybe_generate_twin(
        _dicom_items(tmp_path), tmp_path / "out", renderer_factory=Exploding,
    ) is None


def test_no_torch_import_when_disabled(tmp_path, monkeypatch):
    """Gating must be cheap: the default path pulls in no heavy deps."""
    import sys

    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setitem(sys.modules, "monai", None)
    # Would raise if the module imported torch/monai at call time.
    assert twin.maybe_generate_twin([], tmp_path / "out") is None


def test_pipeline_calls_the_twin_pass():
    """The wiring itself: the imaging pass must invoke twin generation."""
    source = Path("src/ui/pipeline.py").read_text(encoding="utf-8")
    assert "_pass_volumetric_twin" in source
    assert source.count("_pass_volumetric_twin") >= 2, (
        "twin pass must be defined and called"
    )
    assert "maybe_generate_twin" in source
