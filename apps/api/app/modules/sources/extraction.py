"""PDF I/O and conservative, provenance-preserving structural extraction."""

import re
import unicodedata
from hashlib import sha256
from io import BytesIO

from pypdf import PdfReader
from pypdf import __version__ as pypdf_version
from pypdf.errors import PdfReadError

from .contracts import ExerciseDraft, ExtractedPage, SegmentDraft

EXERCISE_HEADING = re.compile(
    r"^\s*(?:Aufgabe|Exercise|Problem)\s+"
    r"(?P<label>\d+(?:\s*[a-zA-Z](?=[\s).:\-]|$))?)"
    r"(?=[\s).:\-]|$)",
    re.IGNORECASE,
)
EXERCISE_TYPES = frozenset({"exercise_sheet", "worked_solution", "past_exam"})


def explicit_chapter_label(text: str) -> str | None:
    """Return only a numbered heading literally present at the segment start.

    No propagation to later paragraphs: without reliable structure extraction
    their chapter is unknown, rather than guessed from proximity.
    """
    match = re.match(
        r"^\s*(?:(?:Kapitel|Chapter|Abschnitt|Section)\s+(\d+(?:\.\d+)*)"
        r"|(\d+(?:\.\d+)+))(?=[\s.:]|$)",
        text,
        re.IGNORECASE,
    )
    return (match.group(1) or match.group(2)) if match else None


class PdfExtractionError(ValueError):
    """An input cannot be processed as a bounded, non-encrypted PDF."""


def text_issues(text: str) -> tuple[str, ...]:
    """Only detect known warning signs; absence of flags is no correctness proof."""
    issues: list[str] = []
    if "\ufffd" in text or re.search(r"\(cid:\d+\)", text):
        issues.append("unmapped_glyphs")
    if any(unicodedata.category(char) in {"Co", "Cc"} and char not in "\n\r\t" for char in text):
        issues.append("suspicious_characters")
    if re.search(r"[=∫∑∏√∞α-ωΑ-Ω²³]|\\(?:frac|int|sum|begin)\b|\$", text):
        issues.append("mathematical_layout_unverified")
    return tuple(issues)


class PdfExtractor:
    version = f"pypdf-{pypdf_version}-text-v1"

    def __init__(self, *, max_pages: int = 200, max_page_chars: int = 200_000):
        self.max_pages = max_pages
        self.max_page_chars = max_page_chars

    def extract(self, data: bytes) -> tuple[ExtractedPage, ...]:
        if not data.startswith(b"%PDF-"):
            raise PdfExtractionError("Expected a PDF header.")
        try:
            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise PdfExtractionError("Encrypted PDFs are not supported.")
            if not 0 < len(reader.pages) <= self.max_pages:
                raise PdfExtractionError("PDF page limit exceeded or document is empty.")
            pages: list[ExtractedPage] = []
            for index, page in enumerate(reader.pages, 1):
                try:
                    text = page.extract_text() or ""
                except Exception:
                    # A corrupt page must not turn into an apparently empty valid page.
                    pages.append(ExtractedPage(index, "", "unreadable", ("extraction_failed",)))
                    continue
                if len(text) > self.max_page_chars:
                    raise PdfExtractionError("Extracted page text limit exceeded.")
                if not text.strip():
                    # No text layer: possibly scanned, blank, or vector-only. No OCR
                    # is attempted and no text or page anchors are invented.
                    pages.append(
                        ExtractedPage(
                            index, text, "scan", ("no_text_layer", "ocr_required_or_blank")
                        )
                    )
                else:
                    pages.append(ExtractedPage(index, text, "text", text_issues(text)))
            return tuple(pages)
        except PdfExtractionError:
            raise
        except (PdfReadError, OSError, ValueError, KeyError, TypeError) as exc:
            raise PdfExtractionError("PDF structure could not be read.") from exc


def segment_pages(pages: tuple[ExtractedPage, ...]) -> tuple[SegmentDraft, ...]:
    """Split at blank lines and task/section headings, retaining exact offsets."""
    result: list[SegmentDraft] = []
    for page in pages:
        if not page.text.strip():
            continue
        start: int | None = None
        end = 0

        def emit() -> None:
            if start is None or end <= start:
                return
            text = page.text[start:end]
            key = sha256(f"{page.page_number}:{start}:{end}:".encode() + text.encode()).hexdigest()
            issues = tuple(dict.fromkeys((*page.issues, *text_issues(text))))
            result.append(SegmentDraft(key, page.page_number, start, end, text, issues))

        for line in re.finditer(r"[^\n]*(?:\n|$)", page.text):
            content = line.group().rstrip("\n\r")
            if not content.strip():
                emit()
                start = None
                continue
            is_heading = bool(EXERCISE_HEADING.match(content)) or bool(
                re.match(r"^\s*\d+(?:\.\d+)+\s+\S", content)
            )
            if is_heading and start is not None:
                emit()
                start = None
            if start is None:
                start = line.start()
            end = line.start() + len(content)
        emit()
    return tuple(result)


def identify_exercises(
    segments: tuple[SegmentDraft, ...], source_type: str
) -> tuple[ExerciseDraft, ...]:
    if source_type not in EXERCISE_TYPES:
        return ()
    result: list[ExerciseDraft] = []
    label: str | None = None
    members: list[SegmentDraft] = []

    def emit() -> None:
        if label is None or not members:
            return
        # The first heading anchors identity; adding a continuation does not
        # silently change which task the user reviewed.
        key = sha256(f"exercise:{members[0].key}:{label}".encode()).hexdigest()
        issues = tuple(dict.fromkeys(issue for segment in members for issue in segment.issues))
        result.append(ExerciseDraft(key, label, tuple(s.key for s in members), issues))

    for segment in segments:
        match = EXERCISE_HEADING.match(segment.text)
        if match:
            emit()
            # Preserve exact source numbering, including whitespace in "2 a".
            label = match.group("label")
            members = []
        if label is not None:
            members.append(segment)
    emit()
    return tuple(result)
