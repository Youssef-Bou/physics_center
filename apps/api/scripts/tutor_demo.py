"""End-to-end local MOCK demonstration, not an evaluation of physics answers."""

import argparse

import httpx
from retrieval_demo import synthetic_pdf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=60) as client:

        def checked(response):
            response.raise_for_status()
            return response.json()

        project = checked(client.post("/api/v1/projects", json={"title": "Synthetic tutor demo"}))
        base = "/api/v1/projects/" + project["id"]
        checked(client.post(base + "/topics", json={"name": "Drehimpuls", "aliases": []}))
        original = synthetic_pdf(
            "Drehimpuls is only a named synthetic fixture, not a scientific explanation."
        )
        upload = checked(
            client.post(
                base + "/documents",
                data={"title": "Demo Skript", "source_type": "lecture_notes"},
                files={"file": ("synthetic.pdf", original, "application/pdf")},
            )
        )
        checked(client.post(base + "/document-versions/" + upload["version_id"] + "/analyses"))
        scope = checked(
            client.post(base + "/retrieval/scopes", json={"name": "Explicit tutor demo sources"})
        )
        scope = checked(
            client.put(
                base + "/retrieval/scopes/" + scope["id"] + "/sources",
                json={
                    "expected_revision": scope["revision"],
                    "document_version_ids": [upload["version_id"]],
                    "confirmed": True,
                },
            )
        )
        for mode in ("SOURCE_MODE", "DEEP_PHYSICS_MODE", "EXAM_MODE", "SOCRATIC_MODE"):
            request = {
                "question": "Erklaere den benannten Begriff Drehimpuls im synthetischen Test.",
                "retrieval_query": "Drehimpuls",
                "scope_id": scope["id"],
                "scope_revision": scope["revision"],
                "mode": mode,
            }
            if mode == "DEEP_PHYSICS_MODE":
                request["math_checks"] = [
                    {
                        "id": "d1",
                        "operation": "differentiate",
                        "expression": "x**2",
                        "variables": ["x"],
                        "expected": "2*x",
                    }
                ]
            answer = checked(client.post(base + "/tutor/answers", json=request))
            assert answer["status"] == "completed" and answer["is_mock"] is True
            assert answer["citations"] and all(
                item["document_version_id"] == upload["version_id"] for item in answer["citations"]
            )
            assert answer["quality"]["scientific_correctness_verified"] is False
            if mode == "DEEP_PHYSICS_MODE":
                assert answer["math_checks"][0]["status"] == "verified"
                assert answer["math_checks"][0]["physics_proof"] is False
            history = checked(
                client.get(base + "/tutor/conversations/" + answer["conversation_id"])
            )
            assert history["turns"][0]["status"] == "completed"
            print(mode + ": completed; real locator preserved; MOCK output; conversation stored.")
        print(
            "Synthetic tutor demo passed. No real LLM or scientific-answer quality was evaluated."
        )


if __name__ == "__main__":
    main()
