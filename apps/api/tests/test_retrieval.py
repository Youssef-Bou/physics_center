"""Source-controlled PostgreSQL retrieval and exact citation recovery.

All PDFs and relevance judgments are explicitly synthetic. The evaluation measures
location recovery for this tiny corpus, not scientific correctness or real-world
retrieval quality.
"""

import json
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
from pypdf import PdfReader

from app.api.dependencies import get_actor
from app.infrastructure.models import DocumentSegment
from app.modules.sources.analysis import CatalogueAnalyzer
from app.modules.sources.contracts import ExtractedPage
from app.modules.sources.extraction import PdfExtractor
from app.modules.sources.pipeline import AnalysisPipeline

BASE = "/api/v1/projects"


def ok(response):
    assert response.status_code in {200, 201}, response.text
    return response.json()


def project(client, title="Retrieval fixture"):
    return ok(client.post(BASE, json={"title": title}))["id"]


def topic(client, project_id, name="Drehimpuls", aliases=None):
    return ok(
        client.post(f"{BASE}/{project_id}/topics", json={"name": name, "aliases": aliases or []})
    )["id"]


def document(
    client, pdf_factory, project_id, title, text, source_type="lecture_notes", analyze=True
):
    pages = text if isinstance(text, tuple) else (text,)
    content = pdf_factory(*pages)
    result = ok(
        client.post(
            f"{BASE}/{project_id}/documents",
            data={"title": title, "source_type": source_type},
            files={"file": ("synthetic.pdf", content, "application/pdf")},
        )
    )
    if analyze:
        result["run"] = ok(
            client.post(f"{BASE}/{project_id}/document-versions/{result['version_id']}/analyses")
        )
    result["bytes"] = content
    return result


def scope(client, project_id, versions=()):
    value = ok(
        client.post(
            f"{BASE}/{project_id}/retrieval/scopes", json={"name": "Explicit synthetic selection"}
        )
    )
    if versions:
        value = activate(client, project_id, value, versions)
    return value


def activate(client, project_id, selection, versions):
    return ok(
        client.put(
            f"{BASE}/{project_id}/retrieval/scopes/{selection['id']}/sources",
            json={
                "expected_revision": selection["revision"],
                "document_version_ids": list(versions),
                "confirmed": True,
            },
        )
    )


def request_search(
    client,
    project_id,
    selection,
    query="Drehimpuls",
    filters=None,
    mode="lexical",
    context=False,
    k=10,
):
    return client.post(
        f"{BASE}/{project_id}/retrieval/{'context' if context else 'search'}",
        json={
            "scope_id": selection["id"],
            "scope_revision": selection["revision"],
            "query": query,
            "filters": filters or {},
            "mode": mode,
            "k": k,
        },
    )


def search(*args, **kwargs):
    return ok(request_search(*args, **kwargs))


def citation(client, project_id, selection, citation_id):
    return client.get(
        f"{BASE}/{project_id}/retrieval/scopes/{selection['id']}/citations/{citation_id}",
        params={"scope_revision": selection["revision"]},
    )


def accept(client, project_id, value, kind="links"):
    return ok(
        client.post(
            f"{BASE}/{project_id}/{kind}/{value['id']}/review",
            json={
                "expected_revision": value["revision"],
                "decision": "accept",
                "evidence_checked": True,
                "reason": "Manually checked synthetic original and relationship.",
            },
        )
    )


@pytest.fixture
def corpus(client, pdf_factory):
    pid = project(client)
    a = document(
        client,
        pdf_factory,
        pid,
        "Skript A",
        ("Drehimpuls in the first synthetic page.", "Energie in the second synthetic page."),
    )
    b = document(
        client, pdf_factory, pid, "Skript B", "Drehimpuls SECRET_INACTIVE_SOURCE", "textbook"
    )
    exercise = document(
        client,
        pdf_factory,
        pid,
        "Blatt 7",
        "Aufgabe 7b\nDrehimpuls in a synthetic exercise.",
        "exercise_sheet",
    )
    selected = scope(client, pid, (a["version_id"], exercise["version_id"]))
    return pid, a, b, exercise, selected


def test_empty_scope_never_means_search_all_documents(client, pdf_factory):
    pid = project(client)
    document(client, pdf_factory, pid, "Not active", "Drehimpuls")
    selected = scope(client, pid)
    value = search(client, pid, selected)
    assert value["hits"] == []
    assert value["effective_sources"] == []
    assert value["warnings"]


def test_expanding_scope_requires_explicit_confirmation(client, pdf_factory):
    pid = project(client)
    doc = document(client, pdf_factory, pid, "Skript A", "Drehimpuls")
    selected = scope(client, pid)
    response = client.put(
        f"{BASE}/{pid}/retrieval/scopes/{selected['id']}/sources",
        json={
            "expected_revision": selected["revision"],
            "document_version_ids": [doc["version_id"]],
            "confirmed": False,
        },
    )
    assert response.status_code == 409
    assert search(client, pid, selected)["hits"] == []


def test_only_selected_versions_are_searched(corpus, client):
    pid, a, b, exercise, selected = corpus
    result = search(client, pid, selected)
    assert result["schema_version"] == "retrieval.v1"
    assert {hit["document_id"] for hit in result["hits"]} == {
        a["document_id"],
        exercise["document_id"],
    }
    assert b["document_id"] not in {hit["document_id"] for hit in result["hits"]}
    assert "SECRET_INACTIVE_SOURCE" not in json.dumps(result)


@pytest.mark.parametrize(
    "filter_name", ["document_ids", "document_version_ids", "source_instruction"]
)
def test_explicit_inactive_source_is_a_conflict(corpus, client, filter_name):
    pid, _, inactive, _, selected = corpus
    filters = {
        "document_ids": [inactive["document_id"]],
        "document_version_ids": [inactive["version_id"]],
        "source_instruction": "Verwende nur Skript B",
    }
    response = request_search(client, pid, selected, filters={filter_name: filters[filter_name]})
    assert response.status_code == 409
    assert "hits" not in response.json()


@pytest.mark.parametrize(
    "filter_name", ["document_ids", "document_version_ids", "source_types", "source_instruction"]
)
def test_document_type_and_title_filters_narrow_active_sources(corpus, client, filter_name):
    pid, a, _, _, selected = corpus
    filters = {
        "document_ids": [a["document_id"]],
        "document_version_ids": [a["version_id"]],
        "source_types": ["lecture_notes"],
        "source_instruction": "Verwende nur Skript A",
    }
    result = search(client, pid, selected, filters={filter_name: filters[filter_name]})
    assert {hit["document_id"] for hit in result["hits"]} == {a["document_id"]}


def test_module_filter_is_applied_within_active_sources(corpus, client):
    pid, a, b, _, selected = corpus
    module = ok(client.post(f"{BASE}/{pid}/modules", json={"title": "Mechanik"}))
    for doc in (a, b):
        ok(client.put(f"{BASE}/{pid}/modules/{module['id']}/documents/{doc['document_id']}"))
    hits = search(client, pid, selected, filters={"module_id": module["id"]})["hits"]
    assert {hit["document_id"] for hit in hits} == {a["document_id"]}


def test_page_and_exercise_filters_use_stored_positions(corpus, client):
    pid, a, _, exercise, selected = corpus
    energy = search(client, pid, selected, "Energie", {"page_start": 2, "page_end": 2})
    assert [(hit["document_id"], hit["page_number"]) for hit in energy["hits"]] == [
        (a["document_id"], 2)
    ]
    tasks = search(client, pid, selected, filters={"exercise_label": "7b"})
    assert {hit["document_id"] for hit in tasks["hits"]} == {exercise["document_id"]}
    assert {task["label"] for hit in tasks["hits"] for task in hit["exercises"]} == {"7b"}


def test_chapter_filter_uses_actual_metadata(client, pdf_factory):
    pid = project(client)
    doc = document(
        client,
        pdf_factory,
        pid,
        "Chapter fixture",
        ("2.1 Drehimpuls\nDrehimpuls first chapter.", "2.2 Energie\nDrehimpuls second chapter."),
    )
    selected = scope(client, pid, [doc["version_id"]])
    hits = search(client, pid, selected, filters={"chapter": "2.1"})["hits"]
    assert hits and all(hit["page_number"] == 1 and hit["chapter"] == "2.1" for hit in hits)


def test_citation_recovers_exact_original_page_span(corpus, client):
    pid, a, _, _, selected = corpus
    hit = search(client, pid, selected, filters={"document_ids": [a["document_id"]]})["hits"][0]
    original = PdfReader(BytesIO(a["bytes"])).pages[hit["page_number"] - 1].extract_text()
    assert original[hit["start_offset"] : hit["end_offset"]] == hit["original_text"]
    resolved = ok(citation(client, pid, selected, hit["citation_id"]))
    for key in (
        "original_text",
        "page_number",
        "start_offset",
        "end_offset",
        "sha256",
        "document_version_id",
    ):
        assert resolved[key] == hit[key]
    assert resolved["locator_verified"] is True


def test_changed_segment_text_cannot_be_presented_as_verified(corpus, client, db_session):
    pid, a, _, _, selected = corpus
    hit = search(client, pid, selected, filters={"document_ids": [a["document_id"]]})["hits"][0]
    segment = db_session.get(DocumentSegment, UUID(hit["segment_id"]))
    segment.text = segment.text.replace("Drehimpuls", "Xrehimpuls")
    db_session.commit()
    assert citation(client, pid, selected, hit["citation_id"]).status_code == 409
    result = search(client, pid, selected, "synthetic", {"document_ids": [a["document_id"]]})
    assert hit["segment_id"] not in {value["segment_id"] for value in result["hits"]}
    assert "invalid_citations_excluded" in result["warnings"]


def test_repeated_terms_do_not_duplicate_a_segment(client, pdf_factory):
    pid = project(client)
    doc = document(
        client,
        pdf_factory,
        pid,
        "Repeated term",
        "Drehimpuls Drehimpuls Drehimpuls in one segment.",
    )
    selected = scope(client, pid, [doc["version_id"]])
    first = search(client, pid, selected)
    second = search(client, pid, selected)
    assert len(first["hits"]) == 1
    assert [hit["citation_id"] for hit in first["hits"]] == [
        hit["citation_id"] for hit in second["hits"]
    ]


def test_no_results_does_not_expand_sources(corpus, client):
    pid, _, _, _, selected = corpus
    result = search(client, pid, selected, "TotallyAbsentTerm")
    assert result["hits"] == []
    assert result["warnings"]


def test_unanalyzed_version_cannot_be_activated(client, pdf_factory):
    pid = project(client)
    doc = document(client, pdf_factory, pid, "Waiting analysis", "Drehimpuls", analyze=False)
    selected = scope(client, pid)
    response = client.put(
        f"{BASE}/{pid}/retrieval/scopes/{selected['id']}/sources",
        json={
            "expected_revision": selected["revision"],
            "document_version_ids": [doc["version_id"]],
            "confirmed": True,
        },
    )
    assert response.status_code == 409


def test_new_version_and_analysis_do_not_change_pinned_scope(
    corpus, client, application, pdf_factory
):
    pid, a, _, _, selected = corpus

    class UpdatedAnalyzer(CatalogueAnalyzer):
        version = "retrieval-test-new-analysis"

    application.state.pipeline = AnalysisPipeline(analyzer=UpdatedAnalyzer())
    rerun = ok(client.post(f"{BASE}/{pid}/document-versions/{a['version_id']}/analyses"))
    assert rerun["run_id"] != a["run"]["run_id"]
    newer = document(client, pdf_factory, pid, "Skript A", "Drehimpuls NEW_VERSION_ONLY")
    hits = search(client, pid, selected, filters={"document_ids": [a["document_id"]]})["hits"]
    assert hits and {hit["analysis_run_id"] for hit in hits} == {a["run"]["run_id"]}
    assert {hit["document_version_id"] for hit in hits} == {a["version_id"]}
    assert (
        request_search(
            client, pid, selected, filters={"document_version_ids": [newer["version_id"]]}
        ).status_code
        == 409
    )


def test_stale_selection_and_foreign_project_are_rejected(corpus, client, application):
    pid, a, _, _, selected = corpus
    old = dict(selected)
    activate(client, pid, selected, [a["version_id"]])
    assert request_search(client, pid, old).status_code == 409
    application.dependency_overrides[get_actor] = lambda: "foreign-reader"
    try:
        assert request_search(client, pid, old).status_code == 404
    finally:
        application.dependency_overrides.clear()


def test_blank_scan_returns_no_fabricated_content(client, pdf_factory):
    pid = project(client)
    doc = document(client, pdf_factory, pid, "Synthetic scan or blank", "")
    selected = scope(client, pid, [doc["version_id"]])
    result = search(client, pid, selected)
    assert result["hits"] == []
    assert any(
        "no_text_layer" in warning or "ocr_required" in warning for warning in result["warnings"]
    )


def test_math_quality_flags_are_retained(client, pdf_factory):
    pid = project(client)
    doc = document(
        client,
        pdf_factory,
        pid,
        "Unverified formula fixture",
        "Drehimpuls = ambiguous mathematical layout",
    )
    selected = scope(client, pid, [doc["version_id"]])
    result = search(client, pid, selected)
    assert result["hits"]
    assert "mathematical_layout_unverified" in result["hits"][0]["issues"]
    assert result["hits"][0]["locator_verified"] is True


def test_failed_text_extraction_is_reported(client, application, pdf_factory):
    class FailedPageExtractor(PdfExtractor):
        version = "retrieval-test-failed-page"

        def extract(self, data):
            return (ExtractedPage(1, "", "unreadable", ("extraction_failed",)),)

    pid = project(client)
    application.state.pipeline = AnalysisPipeline(extractor=FailedPageExtractor())
    doc = document(
        client, pdf_factory, pid, "Failed extraction", "Drehimpuls is present in the original"
    )
    selected = scope(client, pid, [doc["version_id"]])
    result = search(client, pid, selected)
    assert result["hits"] == []
    assert any("extraction_failed" in warning for warning in result["warnings"])


def test_manual_correction_remains_authoritative_for_tutor_context(client, pdf_factory):
    pid = project(client)
    wrong = topic(client, pid, "Wrong topic", ["Drehimpuls"])
    correct = topic(client, pid, "Correct topic")
    doc = document(
        client, pdf_factory, pid, "Correction fixture", "Drehimpuls synthetic occurrence"
    )
    links = ok(client.get(f"{BASE}/{pid}/links"))
    assert len(links) == 1
    old = links[0]
    result = ok(
        client.post(
            f"{BASE}/{pid}/links/{old['id']}/correction",
            json={
                "expected_revision": old["revision"],
                "topic_id": correct,
                "reason": "Correct the deliberately wrong synthetic alias assignment.",
            },
        )
    )
    accept(client, pid, result["replacement"])
    selected = scope(client, pid, [doc["version_id"]])
    context = search(client, pid, selected, context=True)["tutor_context"]
    assert {value["id"] for value in context["topics"]} == {correct}
    assert wrong not in {value["id"] for value in context["topics"]}
    history = ok(client.get(f"{BASE}/{pid}/links/{old['id']}"))
    assert history["review_status"] == "rejected"
    assert history["review_decisions"][-1]["decision"] == "correct"


def test_unselected_evidence_cannot_leak_as_confirmed_prerequisite(client, pdf_factory):
    pid = project(client)
    first = topic(client, pid, "Vektoren")
    second = topic(client, pid, "Drehimpuls")
    active = document(
        client, pdf_factory, pid, "Active script", "Drehimpuls active concept fixture."
    )
    outside = document(
        client,
        pdf_factory,
        pid,
        "Outside evidence",
        "Synthetic: Vektoren is a prerequisite of Drehimpuls.",
    )
    for link in ok(client.get(f"{BASE}/{pid}/links")):
        accept(client, pid, link)
    segment = ok(client.get(f"{BASE}/{pid}/document-versions/{outside['version_id']}/segments"))[0]
    relation = ok(
        client.post(
            f"{BASE}/{pid}/topic-relations",
            json={
                "source_topic_id": first,
                "target_topic_id": second,
                "relation_type": "IS_PREREQUISITE_OF",
                "reason": "Explicit statement in controlled synthetic evidence.",
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
    accept(client, pid, relation, "topic-relations")
    selected = scope(client, pid, [active["version_id"]])
    context = search(client, pid, selected, context=True)["tutor_context"]
    assert context["prerequisites"] == []
    assert "Outside evidence" not in json.dumps(context)
    selected = activate(client, pid, selected, [active["version_id"], outside["version_id"]])
    context = search(client, pid, selected, context=True)["tutor_context"]
    assert relation["id"] in {value["id"] for value in context["prerequisites"]}


class LocalEmbeddingDouble:
    model_id = "deterministic-test-v1"
    is_local = True

    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.append(texts)
        return tuple((1.0, 0.0) if "Drehimpuls" in text else (0.0, 1.0) for text in texts)


def test_optional_embedding_receives_only_prefiltered_sources(corpus, client, application):
    pid, a, _, _, selected = corpus
    provider = LocalEmbeddingDouble()
    application.state.embedding_provider = provider
    result = search(
        client, pid, selected, filters={"document_ids": [a["document_id"]]}, mode="semantic"
    )
    assert result["hits"]
    assert provider.calls
    sent = json.dumps(provider.calls)
    assert "SECRET_INACTIVE_SOURCE" not in sent
    assert "synthetic exercise" not in sent
    assert {hit["document_id"] for hit in result["hits"]} == {a["document_id"]}


def test_missing_or_external_semantic_provider_fails_explicitly(corpus, client, application):
    pid, _, _, _, selected = corpus
    assert request_search(client, pid, selected, mode="semantic").status_code == 501
    provider = LocalEmbeddingDouble()
    provider.is_local = False
    application.state.embedding_provider = provider
    assert request_search(client, pid, selected, mode="semantic").status_code == 409
    assert provider.calls == []


def test_synthetic_retrieval_evaluation_reports_recall_and_exact_citations(client, pdf_factory):
    dataset = json.loads(
        (Path(__file__).parent / "fixtures" / "retrieval_evaluation.json").read_text()
    )
    assert dataset["synthetic"] is True
    pid = project(client, dataset["dataset_id"])
    originals, versions = {}, []
    for entry in dataset["documents"]:
        uploaded = document(
            client, pdf_factory, pid, entry["title"], tuple(entry["pages"]), entry["source_type"]
        )
        originals[entry["title"]] = PdfReader(BytesIO(uploaded["bytes"]))
        versions.append(uploaded["version_id"])
    selected = scope(client, pid, versions)
    recalls, recovered, returned = [], 0, 0
    for case in dataset["questions"]:
        result = search(client, pid, selected, case["query"], case["filters"], k=3)
        expected = {(value["document_title"], value["page_number"]) for value in case["expected"]}
        found = {(hit["document_title"], hit["page_number"]) for hit in result["hits"]}
        recalls.append(len(expected & found) / len(expected))
        for hit in result["hits"]:
            original = originals[hit["document_title"]].pages[hit["page_number"] - 1].extract_text()
            recovered += original[hit["start_offset"] : hit["end_offset"]] == hit["original_text"]
            returned += 1
    metrics = {
        "dataset_id": dataset["dataset_id"],
        "queries": len(recalls),
        "k": 3,
        "macro_recall_at_3": sum(recalls) / len(recalls),
        "citation_exact_match": recovered / returned,
        "returned_citations": returned,
        "synthetic": True,
    }
    print("retrieval_evaluation=" + json.dumps(metrics, sort_keys=True))
    assert metrics["macro_recall_at_3"] == 1.0
    assert metrics["citation_exact_match"] == 1.0


def test_literal_mathematical_token_is_findable_without_an_embedding(client, pdf_factory):
    pid = project(client)
    expression = r"\frac{a}{b}"
    doc = document(
        client, pdf_factory, pid, "Literal LaTeX fixture", "Synthetic token: " + expression
    )
    selected = scope(client, pid, [doc["version_id"]])
    result = search(client, pid, selected, expression)
    assert len(result["hits"]) == 1
    assert expression in result["hits"][0]["original_text"]
    assert "mathematical_layout_unverified" in result["hits"][0]["issues"]


def test_deactivated_source_is_no_longer_citable(corpus, client):
    pid, a, _, exercise, selected = corpus
    old_hit = search(client, pid, selected, filters={"document_ids": [a["document_id"]]})["hits"][0]
    updated = ok(
        client.put(
            f"{BASE}/{pid}/retrieval/scopes/{selected['id']}/sources",
            json={
                "expected_revision": selected["revision"],
                "document_version_ids": [exercise["version_id"]],
                "confirmed": False,
            },
        )
    )
    assert citation(client, pid, updated, old_hit["citation_id"]).status_code == 409
    hits = search(client, pid, updated)["hits"]
    assert {hit["document_id"] for hit in hits} == {exercise["document_id"]}


def test_invalid_embedding_dimensions_fail_without_lexical_fallback(corpus, client, application):
    class InvalidEmbeddingDouble(LocalEmbeddingDouble):
        def embed(self, texts):
            return tuple((1.0, 0.0) if i == 0 else (1.0,) for i, _ in enumerate(texts))

    pid, _, _, _, selected = corpus
    application.state.embedding_provider = InvalidEmbeddingDouble()
    response = request_search(client, pid, selected, mode="hybrid")
    assert response.status_code == 422
    assert "hits" not in response.json()


def test_conflicting_title_instruction_and_version_filter_is_rejected(corpus, client):
    pid, a, b, _, selected = corpus
    selected = activate(client, pid, selected, [a["version_id"], b["version_id"]])
    response = request_search(
        client,
        pid,
        selected,
        filters={
            "source_instruction": "nur Skript A",
            "document_version_ids": [b["version_id"]],
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "source_conflict"


def test_filtered_citation_verification_keeps_the_original_search_constraints(corpus, client):
    pid, a, b, _, selected = corpus
    selected = activate(client, pid, selected, [a["version_id"], b["version_id"]])
    filters = {"document_ids": [a["document_id"]]}
    context = search(client, pid, selected, filters=filters, context=True)
    a_hit = context["hits"][0]
    b_hit = search(client, pid, selected, filters={"document_ids": [b["document_id"]]})["hits"][0]
    constraints = context["citation_constraints"]
    assert constraints["scope_id"] == selected["id"]
    assert constraints["scope_revision"] == selected["revision"]
    assert constraints["filters"]["document_ids"] == [a["document_id"]]

    def verify(hit, query_filters):
        return client.post(
            f"{BASE}/{pid}/retrieval/citations/verify",
            json={
                "scope_id": selected["id"],
                "scope_revision": selected["revision"],
                "segment_id": hit["segment_id"],
                "filters": query_filters,
            },
        )

    assert verify(b_hit, filters).status_code == 409
    assert verify(a_hit, {**filters, "page_start": 2, "page_end": 2}).status_code == 409
    assert ok(verify(a_hit, filters))["original_text"] == a_hit["original_text"]
    # Broad manual resolution remains possible for an otherwise active source;
    # this is distinct from permission to cite it in a narrowed answer.
    assert citation(client, pid, selected, b_hit["citation_id"]).status_code == 200


def test_invalid_source_locator_is_removed_before_embedding(
    corpus, client, application, db_session
):
    pid, a, _, _, selected = corpus
    original = search(client, pid, selected, filters={"document_ids": [a["document_id"]]})["hits"][
        0
    ]
    segment = db_session.get(DocumentSegment, UUID(original["segment_id"]))
    segment.text = segment.text.replace("Drehimpuls", "Xrehimpuls")
    db_session.commit()
    provider = LocalEmbeddingDouble()
    application.state.embedding_provider = provider
    result = search(
        client,
        pid,
        selected,
        filters={"document_ids": [a["document_id"]]},
        mode="semantic",
    )
    assert provider.calls
    assert "Xrehimpuls" not in json.dumps(provider.calls)
    assert original["segment_id"] not in {hit["segment_id"] for hit in result["hits"]}
    assert "invalid_citations_excluded" in result["warnings"]
