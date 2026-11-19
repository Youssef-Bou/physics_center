from dataclasses import replace
from io import BytesIO
from uuid import UUID

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.modules.sources.contracts import (
    AnalysisSuggestions,
    EvidenceDraft,
    ExtractedPage,
    LinkDraft,
    TopicInput,
    TopicRelationDraft,
)
from app.modules.sources.extraction import PdfExtractionError, PdfExtractor
from app.modules.sources.pipeline import AnalysisPipeline

TOPIC = TopicInput(
    UUID("10000000-0000-0000-0000-000000000001"), "Drehimpuls", ("Angular momentum",)
)
OTHER_TOPIC = TopicInput(UUID("10000000-0000-0000-0000-000000000002"), "Energie")


def pdf_fixture(*pages: str | None) -> bytes:
    """Tiny deterministic text or blank PDFs, without external fixture licenses."""
    writer = PdfWriter()
    for text in pages:
        page = writer.add_blank_page(width=595, height=842)
        if text is None:
            continue
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
                NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        commands = [b"BT /F1 12 Tf 50 780 Td"]
        for line in text.splitlines():
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.extend((b"(" + escaped.encode("cp1252") + b") Tj", b"0 -16 Td"))
        commands.append(b"ET")
        stream = DecodedStreamObject()
        stream.set_data(b"\n".join(commands))
        page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class StubAnalyzer:
    version = "deterministic-test-adapter-v1"

    def __init__(self, callback):
        self.callback = callback

    def analyze(self, segments, exercises, topics, source_type):
        return self.callback(segments, exercises, topics, source_type)


def test_real_pdf_positions_and_exercise_numbers():
    result = AnalysisPipeline().run(
        pdf_fixture(
            "Uebungsblatt 7\nAufgabe 1: Drehimpuls\nUntersuchen Sie den Drehimpuls.",
            "Fortsetzung zu Aufgabe 1.\nAufgabe 2a: Energie\nDiskutieren Sie Energie.",
        ),
        (TOPIC, OTHER_TOPIC),
        "exercise_sheet",
    )
    assert [exercise.label for exercise in result.exercises] == ["1", "2a"]
    assert len(result.exercises[0].segment_keys) == 2
    assert [page.page_number for page in result.pages] == [1, 2]
    for segment in result.segments:
        page = result.pages[segment.page_number - 1]
        assert page.text[segment.start_offset : segment.end_offset] == segment.text
    for link in result.links:
        for evidence in link.evidence:
            segment = next(s for s in result.segments if s.key == evidence.segment_key)
            page = result.pages[segment.page_number - 1]
            assert page.text[evidence.start_offset : evidence.end_offset] == evidence.quote


@pytest.mark.parametrize(
    "source_type, relation",
    [
        ("exercise_sheet", "APPLIES"),
        ("worked_solution", "APPLIES"),
        ("past_exam", "EXAMINES"),
        ("lecture_notes", "EXPLAINS"),
    ],
)
def test_catalogue_match_distinguishes_document_functions(source_type, relation):
    result = AnalysisPipeline().run(
        pdf_fixture("Aufgabe 1: Angular momentum"), (TOPIC,), source_type
    )
    assert [link.relation_type for link in result.links] == [relation]
    if source_type == "lecture_notes":
        assert result.exercises == ()
        assert result.links[0].subject_kind == "segment"
    else:
        assert result.links[0].subject_kind == "exercise"
    assert result.topic_relations == ()
    assert result.links[0].score is None
    assert result.links[0].confidence_kind == "none"


def test_exercise_labels_preserve_letter_and_spacing():
    result = AnalysisPipeline().run(
        pdf_fixture("Aufgabe 2 a) Drehimpuls\nAufgabe 3b: Energie"), (TOPIC,), "past_exam"
    )
    assert [exercise.label for exercise in result.exercises] == ["2 a", "3b"]


def test_alias_match_uses_word_boundaries_and_is_not_prerequisite_inference():
    topic = replace(TOPIC, name="Impuls", aliases=())
    result = AnalysisPipeline().run(pdf_fixture("Drehimpuls"), (topic,), "lecture_notes")
    assert result.links == ()
    assert result.topic_relations == ()


def test_repeated_extraction_has_stable_identity():
    data = pdf_fixture("Aufgabe 1: Drehimpuls")
    pipeline = AnalysisPipeline()
    first = pipeline.run(data, (TOPIC,), "exercise_sheet")
    second = pipeline.run(data, (TOPIC,), "exercise_sheet")
    assert first == second
    assert first.exercises[0].segment_keys == second.exercises[0].segment_keys


def test_no_text_layer_never_invents_ocr_text_or_links():
    result = AnalysisPipeline().run(pdf_fixture(None), (TOPIC,), "past_exam")
    assert result.pages[0].kind == "scan"
    assert "no_text_layer" in result.issues
    assert result.segments == result.exercises == result.links == ()


def test_damaged_mathematical_extraction_remains_uncertain():
    result = AnalysisPipeline().run(
        pdf_fixture("Aufgabe 1: Drehimpuls = (cid:123)"), (TOPIC,), "exercise_sheet"
    )
    assert "unmapped_glyphs" in result.issues
    assert "mathematical_layout_unverified" in result.links[0].issues
    assert result.links[0].evidence[0].quote == "Drehimpuls"


def test_unicode_offsets_are_codepoints_without_formula_normalization():
    text = "1.1 Einführung\nDrehimpuls: L = r × p; α²\n"

    class Extractor:
        version = "unicode-fixture-v1"

        def extract(self, data):
            return (ExtractedPage(1, text),)

    result = AnalysisPipeline(extractor=Extractor()).run(b"fixture", (TOPIC,), "lecture_notes")
    assert result.pages[0].text == text
    assert result.segments[0].text == text.rstrip("\n")
    evidence = result.links[0].evidence[0]
    assert text[evidence.start_offset : evidence.end_offset] == evidence.quote


def test_missing_evidence_is_stored_as_warning_not_invented():
    analyzer = StubAnalyzer(
        lambda segments, *_: AnalysisSuggestions(
            (LinkDraft("segment", segments[0].key, TOPIC.id, "EXPLAINS", "Test proposal"),)
        )
    )
    result = AnalysisPipeline(analyzer).run(pdf_fixture("Drehimpuls"), (TOPIC,), "lecture_notes")
    assert result.links[0].evidence == ()
    assert "missing_evidence" in result.links[0].issues


def test_fabricated_quote_is_removed():
    def analyze(segments, *_):
        segment = segments[0]
        return AnalysisSuggestions(
            (
                LinkDraft(
                    "segment",
                    segment.key,
                    TOPIC.id,
                    "EXPLAINS",
                    "Test proposal",
                    (
                        EvidenceDraft(
                            segment.key, segment.start_offset, segment.end_offset, "Invented"
                        ),
                    ),
                ),
            )
        )

    result = AnalysisPipeline(StubAnalyzer(analyze)).run(
        pdf_fixture("Drehimpuls"), (TOPIC,), "lecture_notes"
    )
    assert result.links[0].evidence == ()
    assert "invalid_evidence_removed" in result.links[0].issues
    assert "missing_evidence" in result.links[0].issues


def test_other_task_evidence_cannot_support_current_task():
    def analyze(segments, exercises, *_):
        unrelated = segments[1]
        return AnalysisSuggestions(
            (
                LinkDraft(
                    "exercise",
                    exercises[0].key,
                    TOPIC.id,
                    "APPLIES",
                    "Test proposal",
                    (
                        EvidenceDraft(
                            unrelated.key,
                            unrelated.start_offset,
                            unrelated.end_offset,
                            unrelated.text,
                        ),
                    ),
                ),
            )
        )

    result = AnalysisPipeline(StubAnalyzer(analyze)).run(
        pdf_fixture("Aufgabe 1: Drehimpuls\nAufgabe 2: Energie"), (TOPIC,), "exercise_sheet"
    )
    assert result.links[0].evidence == ()
    assert "unrelated_evidence_removed" in result.links[0].issues


@pytest.mark.parametrize("basis", ["semantic_similarity", "lexical_match"])
def test_similarity_never_becomes_prerequisite(basis):
    analyzer = StubAnalyzer(
        lambda *_: AnalysisSuggestions(
            topic_relations=(
                TopicRelationDraft(
                    TOPIC.id, OTHER_TOPIC.id, "IS_PREREQUISITE_OF", "Test", basis=basis
                ),
            )
        )
    )
    with pytest.raises(ValueError, match="Similarity"):
        AnalysisPipeline(analyzer).run(
            pdf_fixture("Drehimpuls und Energie"), (TOPIC, OTHER_TOPIC), "lecture_notes"
        )


def test_explicit_prerequisite_remains_reviewable_and_keeps_exact_evidence():
    def analyze(segments, *_):
        segment = segments[0]
        return AnalysisSuggestions(
            topic_relations=(
                TopicRelationDraft(
                    TOPIC.id,
                    OTHER_TOPIC.id,
                    "IS_PREREQUISITE_OF",
                    "Explicit statement in fixture",
                    (
                        EvidenceDraft(
                            segment.key, segment.start_offset, segment.end_offset, segment.text
                        ),
                    ),
                    basis="explicit_statement",
                ),
            )
        )

    result = AnalysisPipeline(StubAnalyzer(analyze)).run(
        pdf_fixture("Synthetischer Test: Konzept A ist Voraussetzung fuer Konzept B."),
        (replace(TOPIC, name="Konzept A"), replace(OTHER_TOPIC, name="Konzept B")),
        "lecture_notes",
    )
    assert result.topic_relations[0].evidence[0].quote == result.segments[0].text


@pytest.mark.parametrize("invalid", ["topic", "segment"])
def test_unknown_analyzer_ids_are_rejected(invalid):
    def analyze(segments, *_):
        return AnalysisSuggestions(
            (
                LinkDraft(
                    "segment",
                    "unknown" if invalid == "segment" else segments[0].key,
                    OTHER_TOPIC.id if invalid == "topic" else TOPIC.id,
                    "EXPLAINS",
                    "Test",
                ),
            )
        )

    with pytest.raises(ValueError, match="unknown"):
        AnalysisPipeline(StubAnalyzer(analyze)).run(
            pdf_fixture("Drehimpuls"), (TOPIC,), "lecture_notes"
        )


@pytest.mark.parametrize(
    "score,kind", [(float("nan"), "heuristic_uncalibrated"), (0.9, "probability")]
)
def test_uncalibrated_scores_are_not_exposed_as_probability(score, kind):
    analyzer = StubAnalyzer(
        lambda segments, *_: AnalysisSuggestions(
            (
                LinkDraft(
                    "segment",
                    segments[0].key,
                    TOPIC.id,
                    "EXPLAINS",
                    "Test",
                    score=score,
                    confidence_kind=kind,
                ),
            )
        )
    )
    with pytest.raises(ValueError):
        AnalysisPipeline(analyzer).run(pdf_fixture("Drehimpuls"), (TOPIC,), "lecture_notes")


def test_rejects_invalid_pdf_and_page_limit():
    with pytest.raises(PdfExtractionError):
        PdfExtractor().extract(b"not a PDF")
    with pytest.raises(PdfExtractionError):
        PdfExtractor(max_pages=1).extract(pdf_fixture("Page 1", "Page 2"))
