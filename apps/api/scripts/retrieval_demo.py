"""Reproducible synthetic import -> selected sources -> search -> citation recovery.

Run against the local API with the project's development dependencies installed.
No scientific assertions, external models, or private documents are used.
"""

from __future__ import annotations

import argparse
from io import BytesIO

import httpx
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject


def synthetic_pdf(text: str) -> bytes:
    writer = PdfWriter()
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
    operations = [b"BT /F1 12 Tf 40 780 Td 16 TL"]
    for index, line in enumerate(text.splitlines()):
        if index:
            operations.append(b"T*")
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        operations.append(b"(" + escaped.encode("ascii") + b") Tj")
    operations.append(b"ET")
    stream = StreamObject()
    stream.set_data(b"\n".join(operations))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=60) as client:

        def checked(response):
            response.raise_for_status()
            return response.json()

        project = checked(
            client.post("/api/v1/projects", json={"title": "Synthetischer Retrieval-Durchlauf"})
        )
        base = "/api/v1/projects/" + project["id"]
        active = synthetic_pdf("2.1 Drehimpuls\nSynthetic named-concept fixture: Drehimpuls.")
        uploads = []
        for title, content in (
            ("Skript A", active),
            (
                "Skript B",
                synthetic_pdf("Drehimpuls is also named in this inactive synthetic fixture."),
            ),
        ):
            upload = checked(
                client.post(
                    base + "/documents",
                    data={"title": title, "source_type": "lecture_notes"},
                    files={"file": ("synthetic.pdf", content, "application/pdf")},
                )
            )
            checked(client.post(base + "/document-versions/" + upload["version_id"] + "/analyses"))
            uploads.append(upload)
        scope = checked(
            client.post(base + "/retrieval/scopes", json={"name": "Explizit ausgewaehlte Quellen"})
        )
        scope = checked(
            client.put(
                base + "/retrieval/scopes/" + scope["id"] + "/sources",
                json={
                    "expected_revision": scope["revision"],
                    "document_version_ids": [uploads[0]["version_id"]],
                    "confirmed": True,
                },
            )
        )
        request = {
            "scope_id": scope["id"],
            "scope_revision": scope["revision"],
            "query": "Drehimpuls",
            "k": 3,
            "filters": {
                "source_instruction": "Verwende nur Skript A",
                "page_start": 1,
                "page_end": 1,
            },
        }
        result = checked(client.post(base + "/retrieval/context", json=request))
        assert result["hits"] and all(
            hit["document_id"] == uploads[0]["document_id"] for hit in result["hits"]
        )
        hit = result["hits"][0]
        verified = checked(
            client.post(
                base + "/retrieval/citations/verify",
                json={**result["citation_constraints"], "segment_id": hit["segment_id"]},
            )
        )
        page = PdfReader(BytesIO(active)).pages[verified["page_number"] - 1].extract_text()
        assert page[verified["start_offset"] : verified["end_offset"]] == verified["original_text"]
        conflict = client.post(
            base + "/retrieval/search",
            json={**request, "filters": {"document_ids": [uploads[1]["document_id"]]}},
        )
        assert conflict.status_code == 409 and conflict.json()["code"] == "source_conflict"
        print(
            "Synthetic demo passed: import, activation, narrowing, retrieval, exact citation recovery, inactive-source conflict."
        )
        print(
            "Project:",
            project["id"],
            "| page:",
            verified["page_number"],
            "| chapter:",
            verified["chapter"],
        )
        print(
            "Locator checked:",
            verified["locator_verified"],
            "| scientific verification:",
            verified["scientific_verification"],
        )


if __name__ == "__main__":
    main()
