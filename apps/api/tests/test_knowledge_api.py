"""Behavioral tests for provenance, review persistence and PostgreSQL integrity."""

from io import BytesIO
from uuid import UUID

import pytest
from pypdf import PdfReader
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import get_actor
from app.infrastructure.models import SourceLink, TopicRelation
from app.modules.sources.analysis import CatalogueAnalyzer
from app.modules.sources.contracts import (
    AnalysisSuggestions,
    ExtractedPage,
    LinkDraft,
)
from app.modules.sources.pipeline import AnalysisPipeline

BASE = "/api/v1/projects"


def successful(response):
    assert response.status_code in {200, 201}, response.text
    return response.json()


def project(client, title="Mechanik"):
    return successful(client.post(BASE, json={"title": title}))["id"]


def topic(client, project_id, name="Drehimpuls", aliases=None):
    return successful(
        client.post(
            f"{BASE}/{project_id}/topics",
            json={"name": name, "aliases": aliases or []},
        )
    )["id"]


def upload(client, project_id, content, source_type="exercise_sheet", title="Blatt 7"):
    return successful(
        client.post(
            f"{BASE}/{project_id}/documents",
            data={"title": title, "source_type": source_type},
            files={"file": ("controlled.pdf", content, "application/pdf")},
        )
    )


def analyze(client, project_id, version_id):
    return successful(client.post(f"{BASE}/{project_id}/document-versions/{version_id}/analyses"))


def links(client, project_id):
    return successful(client.get(f"{BASE}/{project_id}/links"))


def review(client, project_id, link, decision, *, kind="links", evidence_checked=True):
    return client.post(
        f"{BASE}/{project_id}/{kind}/{link['id']}/review",
        json={
            "decision": decision,
            "expected_revision": link["revision"],
            "reason": "Checked against the controlled original fixture.",
            "evidence_checked": evidence_checked,
        },
    )


class NewVersionAnalyzer(CatalogueAnalyzer):
    version = "catalogue-test-v2"


def test_source_positions_and_task_numbers_are_persisted(client, pdf_factory):
    project_id = project(client)
    topic_id = topic(client, project_id)
    content = pdf_factory(
        "Aufgabe 1\nDrehimpuls im ersten Abschnitt.",
        "Aufgabe 2a\nDrehimpuls im zweiten Abschnitt.",
    )
    document = upload(client, project_id, content)
    analyze(client, project_id, document["version_id"])
    prefix = f"{BASE}/{project_id}/document-versions/{document['version_id']}"
    segments = successful(client.get(f"{prefix}/segments"))
    pages = [page.extract_text() for page in PdfReader(BytesIO(content)).pages]
    assert {segment["page_number"] for segment in segments} == {1, 2}
    for segment in segments:
        source = pages[segment["page_number"] - 1]
        assert source[segment["start_offset"] : segment["end_offset"]] == segment["text"]
    exercises = successful(client.get(f"{prefix}/exercises"))
    assert {exercise["label"] for exercise in exercises} == {"1", "2a"}
    proposals = links(client, project_id)
    assert len(proposals) == 2
    assert {proposal["exercise_id"] for proposal in proposals} == {
        exercise["id"] for exercise in exercises
    }
    assert all(proposal["topic_id"] == topic_id for proposal in proposals)
    assert all(proposal["relation_type"] == "APPLIES" for proposal in proposals)
    detail = successful(client.get(f"{BASE}/{project_id}/links/{proposals[0]['id']}"))
    assert detail["evidence"]
    assert detail["evidence"][0]["quote"] == "Drehimpuls"
    downloaded = client.get(f"{prefix}/file")
    assert downloaded.content == content
    assert downloaded.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    ("source_type", "text", "expected"),
    [
        ("lecture_notes", "Drehimpuls wird hier behandelt.", "EXPLAINS"),
        ("past_exam", "Aufgabe 3\nDrehimpuls wird hier behandelt.", "EXAMINES"),
    ],
)
def test_relationship_types_follow_document_function(
    client, pdf_factory, source_type, text, expected
):
    project_id = project(client)
    topic(client, project_id)
    document = upload(client, project_id, pdf_factory(text), source_type)
    analyze(client, project_id, document["version_id"])
    assert {item["relation_type"] for item in links(client, project_id)} == {expected}


def test_repeated_upload_and_analysis_do_not_duplicate(client, pdf_factory):
    project_id = project(client)
    topic(client, project_id)
    content = pdf_factory("Aufgabe 1\nDrehimpuls.")
    first = upload(client, project_id, content)
    second = upload(client, project_id, content)
    assert (first["document_id"], first["version_id"]) == (
        second["document_id"],
        second["version_id"],
    )
    first_run = analyze(client, project_id, first["version_id"])
    second_run = analyze(client, project_id, first["version_id"])
    assert first_run["run_id"] == second_run["run_id"]
    assert second_run["reused"] is True
    assert len(links(client, project_id)) == 1


@pytest.mark.parametrize("decision", ["accept", "reject"])
def test_review_decisions_survive_new_analysis_version(client, application, pdf_factory, decision):
    project_id = project(client)
    topic(client, project_id)
    document = upload(client, project_id, pdf_factory("Aufgabe 1\nDrehimpuls."))
    first_run = analyze(client, project_id, document["version_id"])
    original = links(client, project_id)[0]
    checked = successful(review(client, project_id, original, decision))
    application.state.pipeline = AnalysisPipeline(analyzer=NewVersionAnalyzer())
    next_run = analyze(client, project_id, document["version_id"])
    assert next_run["run_id"] != first_run["run_id"]
    result = links(client, project_id)
    assert len(result) == 1
    assert result[0]["id"] == original["id"]
    assert result[0]["review_status"] == {"accept": "accepted", "reject": "rejected"}[decision]
    assert result[0]["revision"] == checked["revision"]
    detail = successful(client.get(f"{BASE}/{project_id}/links/{original['id']}"))
    assert detail["review_decisions"][-1]["decision"] == decision


def test_manual_correction_is_retained_on_reanalysis(client, application, pdf_factory):
    project_id = project(client)
    topic(client, project_id, "Incorrect assignment", ["Drehimpuls"])
    document = upload(client, project_id, pdf_factory("Aufgabe 1\nDrehimpuls."))
    analyze(client, project_id, document["version_id"])
    original = links(client, project_id)[0]
    replacement_topic = topic(client, project_id, "Drehimpuls")
    correction = successful(
        client.post(
            f"{BASE}/{project_id}/links/{original['id']}/correction",
            json={
                "topic_id": replacement_topic,
                "expected_revision": original["revision"],
                "reason": "Corrected the catalogue assignment after original inspection.",
            },
        )
    )
    assert correction["original"]["review_status"] == "rejected"
    replacement = correction["replacement"]
    assert replacement["review_status"] == "proposed"
    successful(review(client, project_id, replacement, "accept"))
    application.state.pipeline = AnalysisPipeline(analyzer=NewVersionAnalyzer())
    analyze(client, project_id, document["version_id"])
    result = {item["id"]: item for item in links(client, project_id)}
    assert result[original["id"]]["review_status"] == "rejected"
    assert result[replacement["id"]]["review_status"] == "accepted"
    assert result[replacement["id"]]["topic_id"] == replacement_topic
    assert len(result) == 2


def test_stale_review_revision_conflicts(client, pdf_factory):
    project_id = project(client)
    topic(client, project_id)
    document = upload(client, project_id, pdf_factory("Aufgabe 1\nDrehimpuls."))
    analyze(client, project_id, document["version_id"])
    proposal = links(client, project_id)[0]
    successful(review(client, project_id, proposal, "accept"))
    assert review(client, project_id, proposal, "reject").status_code == 409


def test_accept_requires_explicit_inspection_of_evidence(client, pdf_factory):
    project_id = project(client)
    topic(client, project_id)
    document = upload(client, project_id, pdf_factory("Aufgabe 1\nDrehimpuls."))
    analyze(client, project_id, document["version_id"])
    proposal = links(client, project_id)[0]
    assert review(client, project_id, proposal, "accept", evidence_checked=False).status_code == 422
    assert links(client, project_id)[0]["review_status"] == "proposed"


class MissingEvidenceAnalyzer:
    version = "missing-evidence-test-v1"

    def analyze(self, segments, exercises, topics, source_type):
        return AnalysisSuggestions(
            links=(
                LinkDraft(
                    "exercise",
                    exercises[0].key,
                    topics[0].id,
                    "APPLIES",
                    "A deliberate negative fixture without an original excerpt.",
                    confidence_kind="none",
                ),
            )
        )


def test_missing_evidence_cannot_be_accepted(client, application, pdf_factory):
    application.state.pipeline = AnalysisPipeline(analyzer=MissingEvidenceAnalyzer())
    project_id = project(client)
    topic(client, project_id)
    document = upload(client, project_id, pdf_factory("Aufgabe 1\nDrehimpuls."))
    analyze(client, project_id, document["version_id"])
    proposal = links(client, project_id)[0]
    assert "missing_evidence" in proposal["issues"]
    assert review(client, project_id, proposal, "accept").status_code == 422


def test_new_analysis_repairs_missing_evidence_without_replacing_proposal(
    client, application, pdf_factory
):
    application.state.pipeline = AnalysisPipeline(analyzer=MissingEvidenceAnalyzer())
    project_id = project(client)
    topic(client, project_id)
    document = upload(client, project_id, pdf_factory("Aufgabe 1\nDrehimpuls."))
    first_run = analyze(client, project_id, document["version_id"])
    original = links(client, project_id)[0]
    assert original["evidence"] == []
    application.state.pipeline = AnalysisPipeline(analyzer=NewVersionAnalyzer())
    repaired_run = analyze(client, project_id, document["version_id"])
    repaired = links(client, project_id)
    assert len(repaired) == 1
    repaired = repaired[0]
    assert repaired["id"] == original["id"]
    assert repaired["revision"] == original["revision"] + 1
    assert repaired["review_status"] == "proposed"
    assert repaired_run["run_id"] != first_run["run_id"]
    assert repaired["evidence"]
    assert all(item["analysis_run_id"] == repaired_run["run_id"] for item in repaired["evidence"])
    accepted = successful(review(client, project_id, repaired, "accept"))
    assert accepted["review_status"] == "accepted"


def test_changed_exercise_membership_does_not_inherit_a_manual_decision(
    client, application, pdf_factory
):
    class OriginalExtraction:
        version = "continuation-incomplete-fixture-v1"

        def extract(self, pdf_bytes):
            return (
                ExtractedPage(1, "Aufgabe 1\nDrehimpuls im ersten Teil."),
                ExtractedPage(2, "Drehimpuls im zweiten", issues=("truncated_text",)),
            )

    class RevisedExtraction:
        version = "continuation-complete-fixture-v2"

        def extract(self, pdf_bytes):
            return (
                ExtractedPage(1, "Aufgabe 1\nDrehimpuls im ersten Teil."),
                ExtractedPage(2, "Drehimpuls im zweiten Teil."),
            )

    project_id = project(client)
    topic(client, project_id)
    content = pdf_factory("Aufgabe 1\nDrehimpuls im ersten Teil.", "Drehimpuls im zweiten Teil.")
    document = upload(client, project_id, content)
    application.state.pipeline = AnalysisPipeline(extractor=OriginalExtraction())
    analyze(client, project_id, document["version_id"])
    original = links(client, project_id)[0]
    successful(review(client, project_id, original, "accept"))
    exercises_url = f"{BASE}/{project_id}/document-versions/{document['version_id']}/exercises"
    memberships = {
        exercise["id"]: set(exercise["segment_ids"])
        for exercise in successful(client.get(exercises_url))
    }
    original_members = memberships[original["exercise_id"]]
    assert len(original_members) == 2
    application.state.pipeline = AnalysisPipeline(extractor=RevisedExtraction())
    analyze(client, project_id, document["version_id"])
    after = {proposal["id"]: proposal for proposal in links(client, project_id)}
    assert len(after) == 2
    assert after[original["id"]]["review_status"] == "accepted"
    new_proposal = next(item for key, item in after.items() if key != original["id"])
    assert new_proposal["exercise_id"] != original["exercise_id"]
    assert new_proposal["review_status"] == "proposed"
    after_memberships = {
        exercise["id"]: set(exercise["segment_ids"])
        for exercise in successful(client.get(exercises_url))
    }
    assert after_memberships[original["exercise_id"]] == original_members
    assert after_memberships[new_proposal["exercise_id"]] != original_members
    assert len(after_memberships[new_proposal["exercise_id"]] & original_members) == 1


def test_manual_source_evidence_repair_is_revisioned_and_preserves_reviewed_state(
    client, application, pdf_factory
):
    application.state.pipeline = AnalysisPipeline(analyzer=MissingEvidenceAnalyzer())
    project_id = project(client)
    topic(client, project_id)
    document = upload(client, project_id, pdf_factory("Aufgabe 1\nDrehimpuls."))
    analyze(client, project_id, document["version_id"])
    proposal = links(client, project_id)[0]
    segment = successful(
        client.get(f"{BASE}/{project_id}/document-versions/{document['version_id']}/segments")
    )[0]
    evidence_url = f"{BASE}/{project_id}/links/{proposal['id']}/evidence"
    body = {
        "expected_revision": proposal["revision"],
        "evidence": [
            {
                "segment_id": segment["id"],
                "start_offset": segment["start_offset"],
                "end_offset": segment["end_offset"],
                "quote": segment["text"],
            }
        ],
    }
    repaired = successful(client.post(evidence_url, json=body))
    assert repaired["id"] == proposal["id"]
    assert repaired["revision"] == proposal["revision"] + 1
    assert "missing_evidence" not in repaired["issues"]
    assert repaired["evidence"][0]["analysis_run_id"] is None
    assert repaired["evidence"][0]["created_by"] == "local-developer"
    assert client.post(evidence_url, json=body).status_code == 409
    accepted = successful(review(client, project_id, repaired, "accept"))
    body["expected_revision"] = accepted["revision"]
    assert client.post(evidence_url, json=body).status_code == 409
    after = successful(client.get(f"{BASE}/{project_id}/links/{proposal['id']}"))
    assert after["revision"] == accepted["revision"]
    assert after["review_status"] == "accepted"
    assert len(after["evidence"]) == 1


class DamagedMathExtractor:
    version = "damaged-math-fixture-v1"

    def extract(self, pdf_bytes):
        return (
            ExtractedPage(
                1,
                "Aufgabe 9\nDrehimpuls = \ufffd",
                issues=("unmapped_glyphs", "mathematical_layout_unverified"),
            ),
        )


def test_damaged_math_extraction_preserves_uncertainty(client, application, pdf_factory):
    application.state.pipeline = AnalysisPipeline(extractor=DamagedMathExtractor())
    project_id = project(client)
    topic(client, project_id)
    document = upload(client, project_id, pdf_factory("Aufgabe 9\nDrehimpuls = r x p"))
    result = analyze(client, project_id, document["version_id"])
    assert "unmapped_glyphs" in result["issues"]
    proposal = links(client, project_id)[0]
    assert "mathematical_layout_unverified" in proposal["issues"]
    assert review(client, project_id, proposal, "accept", evidence_checked=False).status_code == 422
    detail = successful(client.get(f"{BASE}/{project_id}/links/{proposal['id']}"))
    assert all(item["evidence_status"] == "uncertain" for item in detail["evidence"])


def test_scan_without_text_does_not_invent_exercises_or_evidence(client, pdf_factory):
    project_id = project(client)
    topic(client, project_id)
    document = upload(client, project_id, pdf_factory(""))
    result = analyze(client, project_id, document["version_id"])
    assert "no_text_layer" in result["issues"]
    assert links(client, project_id) == []
    prefix = f"{BASE}/{project_id}/document-versions/{document['version_id']}"
    assert successful(client.get(f"{prefix}/exercises")) == []


def test_foreign_project_is_hidden_and_cannot_be_linked(client, application, pdf_factory):
    project_id = project(client)
    topic(client, project_id)
    other_project = project(client, "Other project")
    other_topic = topic(client, other_project)
    document = upload(client, project_id, pdf_factory("Aufgabe 1\nDrehimpuls."))
    analyze(client, project_id, document["version_id"])
    proposal = links(client, project_id)[0]
    response = client.post(
        f"{BASE}/{project_id}/links/{proposal['id']}/correction",
        json={
            "topic_id": other_topic,
            "expected_revision": proposal["revision"],
            "reason": "An invalid cross-project assignment.",
        },
    )
    assert response.status_code in {404, 422}
    application.dependency_overrides[get_actor] = lambda: "another-user"
    assert client.get(f"{BASE}/{project_id}/links").status_code == 404
    prefix = f"{BASE}/{project_id}/document-versions/{document['version_id']}"
    assert client.get(f"{prefix}/file").status_code == 404


def test_database_rejects_cross_project_edge(client, db_session, pdf_factory):
    project_id = project(client)
    topic(client, project_id)
    other_project = project(client, "Other project")
    other_topic = topic(client, other_project)
    document = upload(client, project_id, pdf_factory("Drehimpuls."), "lecture_notes")
    analyze(client, project_id, document["version_id"])
    segment = successful(
        client.get(f"{BASE}/{project_id}/document-versions/{document['version_id']}/segments")
    )[0]
    db_session.add(
        SourceLink(
            project_id=UUID(project_id),
            segment_id=UUID(segment["id"]),
            topic_id=UUID(other_topic),
            relation_type="EXPLAINS",
            identity_key="f" * 64,
            reason="Cross-project negative fixture.",
            basis="manual",
            score=None,
            confidence_kind="none",
        )
    )
    with pytest.raises(IntegrityError) as failure:
        db_session.flush()
    assert failure.value.orig.diag.constraint_name
    db_session.rollback()


def test_database_never_treats_similarity_as_prerequisite(client, db_session):
    project_id = project(client)
    first = topic(client, project_id, "Vektoren")
    second = topic(client, project_id, "Drehimpuls")
    db_session.add(
        TopicRelation(
            project_id=UUID(project_id),
            source_topic_id=UUID(first),
            target_topic_id=UUID(second),
            relation_type="IS_PREREQUISITE_OF",
            identity_key="e" * 64,
            reason="Semantic similarity alone is intentionally insufficient.",
            basis="semantic_similarity",
            score=0.8,
            confidence_kind="heuristic_uncalibrated",
        )
    )
    with pytest.raises(IntegrityError) as failure:
        db_session.flush()
    assert failure.value.orig.diag.constraint_name == "ck_topic_relations_prerequisite_basis"
    db_session.rollback()


def test_manual_topic_relation_requires_real_evidence(client):
    project_id = project(client)
    first = topic(client, project_id, "Vektoren")
    second = topic(client, project_id, "Drehimpuls")
    relation = successful(
        client.post(
            f"{BASE}/{project_id}/topic-relations",
            json={
                "source_topic_id": first,
                "target_topic_id": second,
                "relation_type": "IS_PREREQUISITE_OF",
                "reason": "Manual proposal, still missing a checkable excerpt.",
                "evidence": [],
            },
        )
    )
    assert relation["review_status"] == "proposed"
    assert review(client, project_id, relation, "accept", kind="topic-relations").status_code == 422


def test_manual_prerequisite_and_correction_retain_original_evidence(client, pdf_factory):
    project_id = project(client)
    first = topic(client, project_id, "Concept A")
    second = topic(client, project_id, "Concept B")
    content = pdf_factory("Synthetic fixture: Concept A is prerequisite of Concept B.")
    document = upload(client, project_id, content, "lecture_notes")
    analyze(client, project_id, document["version_id"])
    segment = successful(
        client.get(f"{BASE}/{project_id}/document-versions/{document['version_id']}/segments")
    )[0]
    relation = successful(
        client.post(
            f"{BASE}/{project_id}/topic-relations",
            json={
                "source_topic_id": first,
                "target_topic_id": second,
                "relation_type": "IS_PREREQUISITE_OF",
                "reason": "The synthetic source explicitly states the prerequisite.",
                "evidence": [
                    {
                        "segment_id": segment["id"],
                        "start_offset": segment["start_offset"],
                        "end_offset": segment["end_offset"],
                        "quote": segment["text"],
                    }
                ],
            },
        )
    )
    checked = successful(review(client, project_id, relation, "accept", kind="topic-relations"))
    assert checked["review_status"] == "accepted"
    assert checked["evidence"][0]["evidence_status"] == "manually_checked"
    correction = successful(
        client.post(
            f"{BASE}/{project_id}/topic-relations/{relation['id']}/correction",
            json={
                "relation_type": "RELATED_TO",
                "expected_revision": checked["revision"],
                "reason": "Synthetic reviewer chooses the weaker relation instead.",
            },
        )
    )
    assert correction["original"]["review_status"] == "rejected"
    assert correction["replacement"]["review_status"] == "proposed"
    assert correction["replacement"]["basis"] == "manual"
    assert correction["replacement"]["corrected_from_id"] == relation["id"]
    assert correction["replacement"]["evidence"][0]["quote"] == segment["text"]


def test_existing_manual_relation_can_be_repaired_with_evidence(client, pdf_factory):
    project_id = project(client)
    first = topic(client, project_id, "Concept A")
    second = topic(client, project_id, "Concept B")
    request = {
        "source_topic_id": first,
        "target_topic_id": second,
        "relation_type": "IS_PREREQUISITE_OF",
        "reason": "Synthetic source explicitly connects the two concepts.",
        "evidence": [],
    }
    original = successful(client.post(f"{BASE}/{project_id}/topic-relations", json=request))
    document = upload(
        client,
        project_id,
        pdf_factory("Synthetic fixture: Concept A is prerequisite of Concept B."),
        "lecture_notes",
    )
    analyze(client, project_id, document["version_id"])
    segment = successful(
        client.get(f"{BASE}/{project_id}/document-versions/{document['version_id']}/segments")
    )[0]
    request["expected_revision"] = original["revision"]
    request["evidence"] = [
        {
            "segment_id": segment["id"],
            "start_offset": segment["start_offset"],
            "end_offset": segment["end_offset"],
            "quote": segment["text"],
        }
    ]
    repaired = successful(client.post(f"{BASE}/{project_id}/topic-relations", json=request))
    assert repaired["id"] == original["id"]
    assert repaired["revision"] == original["revision"] + 1
    assert repaired["review_status"] == "proposed"
    assert repaired["evidence"][0]["quote"] == segment["text"]
    accepted = successful(review(client, project_id, repaired, "accept", kind="topic-relations"))
    assert accepted["review_status"] == "accepted"


def test_fabricated_manual_evidence_is_rejected(client, pdf_factory):
    project_id = project(client)
    first = topic(client, project_id, "Concept A")
    second = topic(client, project_id, "Concept B")
    document = upload(client, project_id, pdf_factory("Known original content."), "lecture_notes")
    analyze(client, project_id, document["version_id"])
    segment = successful(
        client.get(f"{BASE}/{project_id}/document-versions/{document['version_id']}/segments")
    )[0]
    response = client.post(
        f"{BASE}/{project_id}/topic-relations",
        json={
            "source_topic_id": first,
            "target_topic_id": second,
            "relation_type": "RELATED_TO",
            "reason": "Deliberate negative quote fixture.",
            "evidence": [
                {
                    "segment_id": segment["id"],
                    "start_offset": segment["start_offset"],
                    "end_offset": segment["start_offset"] + len("Invented"),
                    "quote": "Invented",
                }
            ],
        },
    )
    assert response.status_code == 422
    assert successful(client.get(f"{BASE}/{project_id}/topic-relations")) == []


def test_invalid_pdf_is_rejected_without_source_records(client):
    project_id = project(client)
    response = client.post(
        f"{BASE}/{project_id}/documents",
        data={"title": "Invalid PDF", "source_type": "exercise_sheet"},
        files={"file": ("invalid.pdf", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 422
