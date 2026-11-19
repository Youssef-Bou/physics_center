"""Read validated local manifests; never silently label candidate science as gold."""

import hashlib
import json
from importlib.resources import files
from pathlib import Path

from pydantic import TypeAdapter

from app.modules.sources.extraction import PdfExtractor

from .contracts import EvaluationDataset, ExternalSourceManifest


def load_dataset(path=None):
    content = (
        Path(path).read_text()
        if path is not None
        else files("app.modules.evaluation.data").joinpath("physics_v1.json").read_text()
    )
    return EvaluationDataset.model_validate_json(content)


def dataset_fingerprint(dataset):
    value = json.dumps(
        dataset.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(value.encode()).hexdigest()


def validate_import_manifest(path):
    """Validate rights declarations, exact bytes, and readable PDFs without sending them."""
    path = Path(path)
    if path.stat().st_size > 1_000_000:
        raise ValueError("Import manifest is too large.")
    manifest = TypeAdapter(list[ExternalSourceManifest]).validate_json(path.read_text())
    if len(manifest) > 50 or len({source.source_id for source in manifest}) != len(manifest):
        raise ValueError("Import source IDs must be unique and at most 50.")
    result = []
    for source in manifest:
        source_path = (path.parent / source.path).resolve()
        if source_path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("Import PDF exceeds the local size limit.")
        data = source_path.read_bytes()
        if hashlib.sha256(data).hexdigest() != source.sha256:
            raise ValueError("Source hash does not match the manifest.")
        pages = PdfExtractor().extract(data)
        result.append(
            {
                "source_id": source.source_id,
                "title": source.title,
                "sha256": source.sha256,
                "page_count": len(pages),
                "authorization": source.authorization,
                "external_use_allowed": source.authorization == "external_allowed",
                "physical_review": "unvalidated",
            }
        )
    return result
