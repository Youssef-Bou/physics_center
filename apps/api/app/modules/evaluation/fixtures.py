"""Deterministic synthetic PDFs and fixed contexts, never database citation IDs."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from uuid import NAMESPACE_URL, uuid5

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject

from app.modules.evaluation.contracts import EvaluationCase, EvaluationDataset, SyntheticSource
from app.modules.sources.extraction import PdfExtractor, segment_pages
from app.modules.tutor.context import plain


def synthetic_pdf(pages: list[str]) -> bytes:
    """Create small ASCII fixtures. Unsupported glyphs are rejected, never replaced."""
    writer = PdfWriter()
    for text in pages:
        text.encode("ascii")
        page = writer.add_blank_page(width=595, height=842)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        commands = [b"BT /F1 12 Tf 40 780 Td 16 TL"]
        for number, line in enumerate(text.splitlines()):
            if number:
                commands.append(b"T*")
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(b"(" + escaped.encode("ascii") + b") Tj")
        commands.append(b"ET")
        stream = StreamObject()
        stream.set_data(b"\n".join(commands))
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@dataclass(frozen=True)
class FixedSource:
    source: SyntheticSource
    pdf_bytes: bytes
    sha256: str
    extractor_version: str
    passages: tuple[dict, ...]


def fixed_source(source: SyntheticSource, dataset_id: str = "physics-evaluation") -> FixedSource:
    pdf = synthetic_pdf(source.pages)
    digest = sha256(pdf).hexdigest()
    extractor = PdfExtractor()
    pages = extractor.extract(pdf)
    segments = segment_pages(pages)
    origin = f"physics-evaluation:{dataset_id}:{source.id}:{digest}"
    document_id = uuid5(NAMESPACE_URL, origin + ":document")
    version_id = uuid5(NAMESPACE_URL, origin + ":version")
    run_id = uuid5(NAMESPACE_URL, origin + ":" + extractor.version)
    passages = []
    for segment in segments:
        page = pages[segment.page_number - 1]
        if page.text[segment.start_offset : segment.end_offset] != segment.text:
            raise ValueError("Synthetic fixture position mismatch")
        segment_id = uuid5(NAMESPACE_URL, origin + ":segment:" + segment.key)
        passages.append(
            {
                "citation_id": str(segment_id),
                "segment_id": str(segment_id),
                "source_id": source.id,
                "document_id": str(document_id),
                "document_title": source.title,
                "source_type": source.source_type,
                "document_version_id": str(version_id),
                "sha256": digest,
                "analysis_run_id": str(run_id),
                "extraction_version": extractor.version,
                "page_number": segment.page_number,
                "start_offset": segment.start_offset,
                "end_offset": segment.end_offset,
                "original_text": segment.text,
                "chapter": None,
                "issues": list(segment.issues),
                "extraction_uncertain": bool(segment.issues),
                "locator_verified": True,
                "locator_origin": "synthetic_fixed_context",
                "scientific_verification": False,
                "physical_reference_status": source.physical_review.status,
                "topics": [],
                "exercises": [],
                "prerequisites": [],
            }
        )
    return FixedSource(source, pdf, digest, extractor.version, tuple(passages))


def fixed_sources(dataset: EvaluationDataset) -> dict[str, FixedSource]:
    return {source.id: fixed_source(source, dataset.id) for source in dataset.sources}


def fixed_retrieval(case: EvaluationCase, sources: dict[str, FixedSource]) -> dict:
    """Verified expected spans form an oracle context, without a retrieval ranking.

    This checks declared locators, not their scientific correctness. Sources and
    reference solutions retain their independent unvalidated physical status.
    """
    all_passages = [
        passage for source_id in case.source_ids for passage in sources[source_id].passages
    ]
    if case.expected_sources:
        selected = {}
        for expected in case.expected_sources:
            matches = [
                passage
                for passage in all_passages
                if passage["source_id"] == expected.source_id
                and passage["page_number"] == expected.page_number
                and expected.quote in passage["original_text"]
            ]
            if not matches:
                raise ValueError("The expected synthetic locator cannot be resolved.")
            for passage in matches:
                selected[passage["citation_id"]] = passage
        passages = list(selected.values())
    else:
        passages = all_passages
    return {
        "hits": passages,
        "warnings": ["synthetic_fixed_context_not_expert_validated"],
    }


def source_tracking(case: EvaluationCase, sources: dict[str, FixedSource]) -> list[dict]:
    result = []
    for source_id in case.source_ids:
        fixture = sources[source_id]
        result.append(
            {
                "source_id": source_id,
                "title": fixture.source.title,
                "sha256": fixture.sha256,
                "extractor_version": fixture.extractor_version,
                "rights_status": fixture.source.rights_status,
                "physical_review": plain(fixture.source.physical_review.model_dump()),
                "locator_origin": "synthetic_fixed_context",
                "external_use_allowed": fixture.source.external_use_allowed,
            }
        )
    return result
