# Entwicklungsumgebung

## Implementierter Umfang

Das Backend in `apps/api` bietet einen lokalen, getesteten Analyse-/Reviewablauf.
Es benötigt Python 3.12, uv (hier 0.13.6), Docker Compose und PostgreSQL 17.
Die Paketversionen stehen vollständig in `apps/api/uv.lock`, das PostgreSQL-Image
ist in `compose.yaml` per Digest fixiert. Keine externen KI-Konten nötig.
Next.js, OCR, eine Chat-Weboberfläche, große Vektorindizes und produktive Anmeldung sind noch nicht
implementiert. Lokale Volltextsuche und ein optionaler lokaler Embedding-Port sind
vorhanden. Details: [KNOWLEDGE_LINKING](KNOWLEDGE_LINKING.md), [RETRIEVAL](RETRIEVAL.md).
Die dialogorientierte Tutor-API mit vier Modi, Promptversion `physics-tutor-v1`,
Conversation-Persistenz und optionalem SymPy ist implementiert; siehe
[PHYSICS_TUTOR](PHYSICS_TUTOR.md). Standardmäßig ist nur `MockProvider` / `mock-v1`
aktiv. Kein reales Sprachmodell wurde ausgeführt oder fachlich evaluiert.

Im vorhandenen Checkout arbeiten; Cloud-Aufgaben sind bereits isoliert.
Keinen zusätzlichen Worktree ohne ausdrücklichen Auftrag anlegen.

## Installation und Datenbank

Im Repository `/workspace/physics_center` (in anderen Checkouts den Pfad anpassen):

```sh
cd /workspace/physics_center
# Nur falls noch keine eigene .env existiert:
cp -n .env.example .env
# POSTGRES_PASSWORD in .env durch eigenes lokales Passwort ersetzen.
# Für die folgenden URL-Beispiele URL-sichere Zeichen verwenden.
set -a
. ./.env
set +a
docker compose up -d --wait db
cd apps/api
uv sync --frozen --extra math
export DATABASE_URL="postgresql+psycopg://physics:${POSTGRES_PASSWORD}@127.0.0.1:55432/physics_center"
uv run --frozen alembic upgrade head
```

`.env` und `.local/` sind ignoriert. Niemals reale Zugangsdaten in Git speichern.
PostgreSQL ist ausschließlich an Loopback gebunden; Port 55432 muss frei sein.
Die Datenbank überlebt Containerneustarts im benannten Compose-Volume.
Keine automatische Schemaerstellung beim API-Start: Migrationen sind explizit.

## Start und interne Readiness

Im selben Terminal unter `apps/api`, mit gesetztem `DATABASE_URL`:

```sh
export PHYSICS_LOCAL_MODE=1
export PHYSICS_STORAGE_ROOT="$PWD/.local/documents"
uv run --frozen uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

`PHYSICS_LOCAL_MODE=1` ist Pflicht. Die feste Entwickleridentität ist keine
produktive Anmeldung; den Server nicht öffentlich binden. Für Authentifizierungs-
und Berechtigungstests lässt sich ausschließlich die serverseitige Dependency
ersetzen; ein HTTP-Header bestimmt nicht den Eigentümer.

Eine interne Anfrage `curl --fail http://127.0.0.1:8000/health/ready` prüft den
Datenbankzugriff. Die FastAPI-Schemadokumentation unter `/docs` ist die minimale
Backend-Testoberfläche, keine eigene Review-Webanwendung. Ein echter Upload-,
Analyse- und Reviewablauf ist in [KNOWLEDGE_LINKING](KNOWLEDGE_LINKING.md) beschrieben.
In der API zeigt `GET .../links/{id}` die Belege und Historie;
`GET .../document-versions/{id}/file` liefert das Original als Download.

Originaldateien und DB müssen gemeinsam aufbewahrt werden. Prozesse überleben
keinen Snapshot/Neustart; API erneut mit obigem Befehl starten. Stoppen mit Ctrl-C,
Datenbank bei Bedarf aus dem Repository mit `docker compose stop db` anhalten.
Das Dokumentieren dieser Befehle veröffentlicht keine Cloud-Umgebung.

## Automatisierte Prüfungen

Mit laufender lokaler Datenbank im Verzeichnis `apps/api`:

```sh
export TEST_DATABASE_URL="$DATABASE_URL"
uv run --frozen --extra math pytest
uv run --frozen --extra math ruff check app tests migrations scripts
uv run --frozen --extra math ruff format --check app tests migrations scripts
```

Die Integrationstests erzeugen zufällig benannte, isolierte PostgreSQL-Schemas,
spielen alle Alembic-Migrationen ein und entfernen ausschließlich ihr eigenes
Schema. Der Testnutzer braucht dafür CREATE-SCHEMA-Rechte. Keine produktive
Datenbank als Testziel verwenden. Ohne `TEST_DATABASE_URL` werden diese Tests
explizit übersprungen; ein solcher Lauf ist keine vollständige Validierung.
Nur die reinen Pipeline-Tests laufen ohne Datenbank:

```sh
uv run --frozen pytest tests/test_pipeline.py
```

Das `math`-Extra ist für den Dienst optional, für die vollständige symbolische
Testabnahme jedoch nötig. Ohne SymPy meldet das Werkzeug `unavailable`, statt eine
Berechnung vorzutäuschen. Die volle CI installiert das Extra; die beiden neuen
Abhängigkeiten SymPy und mpmath sind im Lockfile fixiert.

Mit laufendem Server im expliziten Mock-Modus lässt sich zusätzlich prüfen:

```sh
uv run --frozen --extra math python scripts/tutor_demo.py
```

Dieser echte HTTP-Ablauf importiert ein synthetisches PDF, aktiviert dessen Version,
ruft alle vier Modi auf, prüft Fundstellen und Unterhaltungsspeicherung sowie eine
bekannte symbolische Ableitung. Er bewertet ausdrücklich keine echte LLM-Antwort.
Einen echten Provider nur mit eigener Modellkonfiguration und sicher gebundener
`PHYSICS_LLM_API_KEY` aktivieren; niemals Schlüssel in Chat oder Git übertragen.
Zusätzlich ist pro externem Turn `allow_external_processing=true` nötig.

Die kleinen Test-PDFs entstehen deterministisch im Test, einschließlich bekannter
Seiten, Aufgabenüberschriften und Formelwarnungen. Test-Doubles ersetzen externe
Analyzer. Tests gegen diese Fixtures belegen keine allgemeine OCR-/KI-Qualität.
Die [Backend-CI](../.github/workflows/backend.yml) führt dieselben Prüfungen mit
PostgreSQL sowie die Offline-Green-Referenzchecks aus. Der erste Remote-Lauf des
Commits 082596b scheiterte an einer isolierten SymPy-Rechnung. Die bisherige
Deadline zählte Kaltstart und Rechnung gemeinsam. Start und Berechnung haben jetzt
getrennte, weiterhin begrenzte Deadlines; siehe [PHYSICS_TUTOR](PHYSICS_TUTOR.md).

Außerdem nach Änderungen `git diff --check` ausführen und Dokumentlinks prüfen.
Die vollständige Study-UI, produktives Hosting und ein realer wissenschaftlicher
Evaluationsdatensatz sind keine bereits bestandenen Prüfziele dieses Prototyps.

## Nachgewiesener lokaler Prüfstand

Am 22. November 2026 bestanden nach der begrenzten Startup-/Compute-Trennung
**435 Tests** gegen PostgreSQL, ohne Fehler oder Skips, in 65 Sekunden.
Ruff und Formatprüfung bestanden; die bekannte Starlette/httpx-Warnung bleibt.
Zusätzlich bestanden 20 Offline-Green-Referenzchecks sowie beide Mock-Promptpaare
(isoliert und End-to-end) für den präzisierten Datensatz 1.1.1 mit gleichen
Kontext-Hashes innerhalb jedes Paars. Die ursprünglichen 24 Fälle und ihre
Quellenseiten bleiben per Regressionstest erhalten. Ablauf und Grenzen:
[GREEN_PILOT](GREEN_PILOT.md). Reale Modellaufrufe: 0; sicherer API-Schlüssel und
unabhängige menschliche Fachabnahme stehen aus. Diese lokale Abnahme ersetzt
keine gemessene fachliche Modellqualität; den Remote-Stand zeigen die PR-Checks.

Am 19. November 2026 bestanden nach den Responses-, Evaluations- und Adaptive-
Erweiterungen **409 Tests**, ohne Fehler oder Skips. Ruff, Formatprüfung,
Dokumentlinks und die Prüfung des vorgemerkten Git-Diffs bestanden ebenfalls.
Die PostgreSQL-Tests liefen in isolierten Schemas eines separaten lokalen
Testdienstes; das bestehende Anwendungsvolume blieb unverändert. Reale Modell-
Aufrufe waren deaktiviert. Die bekannte Starlette/httpx-Abkündigungswarnung bleibt.
Dies belegt die lokale Funktions- und Vertragsprüfung, keine gemessene fachliche
Qualitätssteigerung eines realen Modells.

Nach Tutor-Phase 1 bestanden am 16. November 2026 **216 Tests**, ohne Fehler oder
Skips: alle bisherigen 79, 46 Tutor-/PostgreSQL-Integrationstests, 45 Provider-/Prompt-
Vertragstests und 46 Mathematiktests. Die symbolischen Tests verwendeten tatsächlich
SymPy 1.14.0 in separaten Prozessen. Der HTTPS-Modelladapter wurde über deterministische
HTTP-Testtransporte geprüft, nicht mit einem realen Modellkonto.

Ruff, Formatprüfung, eingefrorene Installation mit `math`-Extra, Migration 0004 und
Schemaabgleich bestanden. Der echte lokale HTTP-Durchlauf `scripts/tutor_demo.py`
prüfte alle vier Modi mit Mock/mock-v1, Quellenpositionen, Unterhaltungen und eine
bekannte Ableitung. Eine Starlette-Abkündigungswarnung zum funktionierenden httpx-
Testclient bleibt. Remote-CI und Cloud-Veröffentlichung wurden nicht ausgeführt.
Die folgenden älteren Abschnitte halten die Prüfstände der vorherigen Schritte fest.

Nach Ergänzung der Retrieval-Engine bestanden am 16. November 2026 **79 Tests**,
darunter alle bisherigen 45 und 34 neue Retrieval-/API-/Evaluationsfälle, ohne Fehler
oder Skips. Ruff und Formatprüfung bestanden. Der ausführbare Ablauf
`uv run --frozen python scripts/retrieval_demo.py` wurde gegen den tatsächlich
gestarteten Server geprüft: Import, Aktivierung, Suche, exakte Quellenwiedergewinnung
und Konflikt für eine nicht aktivierte Quelle. Migration 0003 wurde additiv angewendet;
Schemaabgleich und Upgrade/Downgrade in isolierten Schemas erhalten Bestandsdaten.
Die untenstehende ältere Prüfung dokumentiert den ursprünglichen Analyse-Schnitt.

Am 16. November 2026 bestanden 45 Tests: 22 Pipeline-Tests und 23 API-/PostgreSQL-
Integrationstests, ohne Fehler oder Skips. Ruff-Prüfung und Formatprüfung bestanden.
Eine Starlette-Abkündigungswarnung betrifft den weiterhin funktionierenden
httpx-Testclient; sie ist kein fehlgeschlagener Test.

Zusätzlich geprüft: eingefrorene Installation, Compose-Start mit Readiness,
beide Migrationen und wiederholtes Upgrade, Schemaabgleich ohne neue Operationen
sowie ein echter HTTP-Ablauf mit Skript, Übungsblatt und Altklausur zu demselben
Thema. Drei geprüfte Beziehungen und ihre Originalbelege blieben nach einem
API-Neustart erhalten. Diese lokale Prüfung ist kein Nachweis einer Cloud-
Veröffentlichung oder eines ausgeführten GitHub-CI-Laufs.
