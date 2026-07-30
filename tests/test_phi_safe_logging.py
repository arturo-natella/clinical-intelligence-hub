"""Regression coverage for patient-safe application logging."""

import ast
import logging
from pathlib import Path

from src.extraction.preprocessor import Preprocessor
from src.imaging.image_pipeline import ImagePipeline
from src.privacy.redactor import Redactor


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _PreprocessorDB:
    def is_duplicate(self, _sha256_hash):
        return False

    def get_file_state_by_hash(self, _sha256_hash):
        return None

    def upsert_file_state(self, **_kwargs):
        return None


def _rendered_logs(caplog, progress_events=()):
    return "\n".join(
        [record.getMessage() for record in caplog.records]
        + [str(event) for event in progress_events]
    )


def test_preprocessor_and_image_progress_do_not_log_source_filename(
    tmp_path,
    caplog,
):
    source_secret = "PATIENT_SOURCE_NAME_PHI_a6b17c.png"
    source = tmp_path / source_secret
    source.write_bytes(b"local test image")
    caplog.set_level(logging.DEBUG)

    item = Preprocessor(_PreprocessorDB()).process(source)
    progress_events = []
    ImagePipeline(
        data_dir=tmp_path,
        progress_callback=lambda *event: progress_events.append(event),
    )._collect_images([item])

    assert source_secret not in _rendered_logs(caplog, progress_events)


def test_redaction_logs_neither_source_filename_nor_original_pii(caplog):
    source_secret = "PATIENT_SOURCE_NAME_PHI_f3e89b.pdf"
    pii_secret = "212-555-0199"
    redactor = object.__new__(Redactor)
    redactor.db = None
    redactor._presidio_available = False
    caplog.set_level(logging.DEBUG, logger="CIH-Redactor")

    result = redactor.redact(
        f"Telephone: {pii_secret}",
        source_file=source_secret,
    )

    rendered = _rendered_logs(caplog)
    assert source_secret not in rendered
    assert pii_secret not in rendered
    assert "[PHONE_REDACTED]" in result


def test_logger_calls_do_not_directly_interpolate_patient_values_or_errors():
    """Keep direct PHI/error objects out of logger and progress calls.

    Counts and safe metadata remain allowed, as do ``type(error).__name__``
    values. This catches the risky forms that caused prior leaks, such as
    ``logger.debug(f"failed for {drug_name}: {e}")``.
    """
    sensitive_names = {
        "drug_name",
        "med_name",
        "dx_name",
        "diagnosis_name",
        "lab_name",
        "gene_name",
        "gene_symbol",
        "variant_id",
        "term",
        "term_name",
        "query",
        "source_file",
        "source_filename",
        "filename",
        "file_path",
        "pdf_path",
        "dicom_path",
        "image_path",
        "output_path",
        "profile_id",
        "new_name",
        "raw_text",
        "result_text",
        "response_text",
        "context",
        "e",
        "exc",
        "error",
        "exception",
    }
    sensitive_attributes = {
        "name",
        "source_file",
        "filename",
        "file_source",
        "db_path",
    }
    logging_methods = {"debug", "info", "warning", "error", "exception"}
    progress_methods = {"_log", "_progress"}
    violations = []

    def is_direct_sensitive(expression):
        if isinstance(expression, ast.Name):
            return expression.id in sensitive_names
        if isinstance(expression, ast.Attribute):
            return expression.attr in sensitive_attributes
        return False

    for path in sorted((PROJECT_ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in logging_methods | progress_methods:
                continue

            direct_values = list(node.args[1:])
            if node.args and isinstance(node.args[0], ast.JoinedStr):
                direct_values.extend(
                    part.value
                    for part in node.args[0].values
                    if isinstance(part, ast.FormattedValue)
                )
            for expression in direct_values:
                if is_direct_sensitive(expression):
                    violations.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}"
                    )

    assert violations == []
