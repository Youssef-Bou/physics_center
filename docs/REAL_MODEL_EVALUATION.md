# Reales Modell und nachvollziehbare Physik-Evaluation

Implementiert sind ein Responses-API-Adapter, ein begrenzter Evaluationsrunner und
versionierte synthetische Kandidaten. Ein realer, kostenpflichtiger Modellaufruf
oder eine unabhängige fachliche Abnahme wurde in diesem Entwicklungsschritt nicht
durchgeführt. Mock- und HTTP-Testtransport-Ergebnisse belegen die Integration,
nicht die Fähigkeit eines Modells zu anspruchsvoller Physik.

Grundlagen: [Physiktutor](PHYSICS_TUTOR.md), [Bewertungsraster](TUTOR_EVALUATION.md),
[Kandidatenbestand](EVALUATION_CASES.md) und [adaptive Erklärung](ADAPTIVE_DEEP_PHYSICS.md).

## Modell- und API-Entscheidung

Der neue Standard für ausdrücklich aktivierte reale Aufrufe ist `gpt-6.1-sol`
über `OpenAIResponsesProvider` / `openai_responses` und `POST /responses`.
Die offiziellen Dokumentationsseiten wurden am **16. November 2026** als erreichbar
geprüft; diese Dokumentationsprüfung ist kein Modellaufruf und kein Zugangsnachweis:

- [Modell und öffentliche Preise](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
- [Reasoning-Leitfaden](https://developers.openai.com/api/docs/guides/reasoning)
- [Responses-Erstellung](https://developers.openai.com/api/docs/reference/resources/responses/methods/create)

Der Adapter verwendet strukturierte JSON-Ausgabe, `store=false` und ein explizites
`max_output_tokens`. Für dieses Modell gelten `low`, `medium`, `high`, `xhigh` und
`max`; ohne ausdrückliche Vorgabe wird `medium` verwendet. `none` und `minimal`
gehören zwar zum allgemeinen Schnittstellenvertrag, sind für dieses Modell nicht
freigegeben. Andere Modelle benötigen separat geprüfte Fähigkeiten und Preise.

`temperature` wird beim Responses-Adapter **nicht gesendet**. Die gemeinsame
Schnittstelle enthält den angefragten Wert weiterhin; Berichte unterscheiden ihn
von den tatsächlich übertragenen Parametern. `max_output_tokens` umfasst auch
Reasoning-Tokens und ist keine garantierte Länge der sichtbaren Antwort.
Erklärungstiefe und Reasoning-Aufwand sind unabhängige Einstellungen.

Der Adapter aktiviert keine Tools, keine Pro-Variante und keine automatische
Fortsetzung. Er verwirft unvollständige, verweigerte, zu große oder schematisch
ungültige Antworten. Reasoning-Ausgabeelemente werden nicht als Antworttext oder
Gedankenkette gespeichert. `store=false` bedeutet keine Zusage vollständiger
Daten-Nichtaufbewahrung; vor dem Versand gelten weiterhin die tatsächlich
vereinbarten Datenschutz- und Aufbewahrungsbedingungen des Anbieters.

HTTP 429 liefert einen sicheren Rate-Limit-Fehler, gegebenenfalls mit begrenzter
`Retry-After`-Angabe. Es gibt keinen automatischen Retry. Timeouts, Fehler und
ungültige Antworten dürfen weder API-Schlüssel noch ungefilterte HTTP-Bodies in
Bericht oder Unterhaltung schreiben.

## Bewusste Aktivierung

Standard bleibt `MockProvider` mit `mock-v1`. Für einen echten Dienst sind
unabhängige Schritte erforderlich:

1. `PHYSICS_LLM_API_KEY` sicher über die Laufzeit-/Umgebungseinstellungen binden;
   Schlüssel niemals in Chat, Git, Befehlsargumenten oder Berichten ablegen.
2. Für den Tutor `PHYSICS_LLM_PROVIDER=openai_responses` und
   `PHYSICS_LLM_ENABLE_REAL=1` setzen. Die CLI wählt denselben Adapter ausdrücklich
   mit `--provider openai_responses`. Optional `PHYSICS_LLM_MODEL=gpt-6.1-sol` und
   `PHYSICS_LLM_REASONING_EFFORT=medium` ausdrücklich setzen.
3. Bei Tutor-Anfragen zusätzlich `allow_external_processing=true` im jeweiligen
   Turn übermitteln. Quellenaktivierung allein erteilt keine externe Versandfreigabe.
4. Bei Evaluation zusätzlich `--allow-paid`, ein Budget `--max-calls` von **1 bis 10**
   und eine passende Fallauswahl mit `--limit`/`--case-id` setzen.

Echte Aufrufe sind in CI gesperrt. Nur ein deterministischer `httpx.MockTransport`
umgeht die Netzfreigabe für Adaptertests; ein beliebiger Netzwerktransport ist keine
Berechtigung. Der Evaluationsrunner zählt Versuche vor dem Versand, auch wenn sie
fehlschlagen. Ein Aufrufbudget begrenzt die Zahl der Requests, nicht verbindlich
Geldkosten; Parameter, tatsächliche Usage und Preismodell bleiben relevant.

Alle mitgelieferten Referenzen sind unvalidiert. Ein explorativer realer Versuch
benötigt daher ausdrücklich `--allow-unvalidated`. Dieses Flag macht aus dem
Material keinen Goldstandard. Quellen ohne Erlaubnis zum externen Versand dürfen
auch damit nicht übertragen werden.

## Zwei getrennte Versuchsbedingungen

| Verfahren | Verarbeitung | Aussagebereich |
| --- | --- | --- |
| `isolated` | Deterministisch erzeugte PDF-Fixtures; anhand erwarteter Quellen-ID, Seite und exaktem Zitat fest ausgewählte, technisch auflösbare Passagen. Kein Retrievalranking. | Modell-/Promptverhalten bei vorgegebener Oracle-Auswahl. Die physikalischen Referenzen bleiben ungeprüft. |
| `end_to_end` | Import, Analyse, Scope, Retrieval, Kontextbudget, Tutor und Citation-Prüfung über die bestehenden Backend-Services und PostgreSQL. | Verhalten des gesamten Ablaufs einschließlich fehlender oder verdrängter Fundstellen. Keine isolierte Aussage über das Modell allein. |

Technisch geprüfte Locatorpositionen und fachlich bestätigte Referenzlösungen sind
verschiedene Eigenschaften. Die synthetischen Positionen werden aus tatsächlichen
Fixture-Bytes und unveränderten Extraktionen bestimmt; ihre physikalischen Inhalte
werden dadurch nicht unabhängig bestätigt. End-to-end ersetzt den Modelladapter
nicht durch eine parallele Fachimplementierung.

End-to-end benötigt eine erreichbare, migrierte lokale **Evaluationsdatenbank**
und Dateispeicher. Es legt pro Lauf ein eigenes Projekt und Quellen an und löscht
keine bestehenden Nutzerdaten. Diese Artefakte bleiben nachvollziehbar erhalten.
Installation und Migration: [DEVELOPMENT](DEVELOPMENT.md). Eine erfolgreiche Prüfung
gegen einen separaten Testdienst, etwa auf Port 55435, ist keine Aussage über die
Wiederherstellung des regulären App-Dienstes auf Port 55432.

## Datensätze und Referenzstatus

Der Standarddatensatz
[physics_v1.json](../apps/api/app/modules/evaluation/data/physics_v1.json) enthält
24 Fälle, Version `1.0.0`, mit je vier Fällen zu Herleitungen, Konzepten,
Klausuraufgaben, Gültigkeitsgrenzen, Quellenarbeit und sokratischen Interaktionen.
Die separat auswählbare Erweiterung
[physics_adaptive_v1.json](../apps/api/app/modules/evaluation/data/physics_adaptive_v1.json)
enthält 29 Fälle, Version `1.1.1`, darunter fünf zusätzliche Deep-Physics-Fragen.
Sie wird in [ADAPTIVE_DEEP_PHYSICS](ADAPTIVE_DEEP_PHYSICS.md) beschrieben;
der bisherige Bestand bleibt erhalten. Die Datasetkennung lautet für beide
`physics-tutor-candidates`; Version und Hash unterscheiden die Stände.

Jeder Fall führt Frage, Voraussetzungen, Referenzkandidat, Pflichtschritte,
Fehlertypen, erlaubte Quellen und erwartete Stellen. Fälle und synthetische Quellen
tragen `unvalidated`, ohne erfundene Prüfer oder Prüfzeiten. Eine menschliche
Validierung braucht eine explizite Prüferkennung und einen Zeitstempel.

## Reproduzierbare CLI-Abläufe

Alle folgenden Befehle werden in `apps/api` nach der Installation mit Lockfile
und optionalem `math`-Extra ausgeführt. `physics-eval` ist der installierte
Konsoleneinstieg; `uv run --frozen --extra math` verwendet dieselbe Umgebung.

```sh
uv run --frozen --extra math physics-eval list
uv run --frozen --extra math physics-eval list --json
uv run --frozen --extra math physics-eval list \
  --dataset app/modules/evaluation/data/physics_adaptive_v1.json
uv run --frozen --extra math physics-eval run --provider mock --method isolated \
  --case-id CON_GAUSS_FLUX --limit 1 --output .local/evaluations/mock-concept.json
```

Mit gesetztem `DATABASE_URL` auf die dafür vorgesehene Entwicklungsdatenbank:

```sh
uv run --frozen --extra math physics-eval run --provider mock --method end_to_end \
  --case-id CON_GAUSS_FLUX --limit 1 \
  --storage-root .local/evaluation-originals --output .local/evaluations/mock-e2e.json
```

Ein **bewusst kostenpflichtiger** isolierter Einzelversuch nach sicherer
Schlüsselbindung und Aktivierung der oben beschriebenen Umgebungsvariablen:

```sh
uv run --frozen --extra math physics-eval run --provider openai_responses \
  --model gpt-6.1-sol --reasoning-effort medium --method isolated \
  --case-id CON_GAUSS_FLUX --limit 1 --allow-paid --max-calls 1 \
  --allow-unvalidated --output .local/evaluations/real-concept.json
```

Dieser Befehl ist eine Anleitung, kein hier bereits ausgeführter Modelllauf.
Vor jeder Wiederholung neue Reportpfade wählen; vorhandene Reports werden nicht
überschrieben. Vergleich und Export vorhandener, eigener Berichte:

```sh
uv run --frozen --extra math physics-eval compare \
  .local/evaluations/mock-concept.json .local/evaluations/mock-e2e.json \
  --output .local/evaluations/method-comparison.json
uv run --frozen --extra math physics-eval export .local/evaluations/mock-concept.json \
  --output .local/evaluations/mock-concept-copy.json
```

Ein Vergleich verschiedener Methoden ist ausdrücklich kein kontrollierter
Prompt-A/B-Nachweis. Der Report kennzeichnet fehlende Vergleichbarkeit; Änderungen
an einer Antwort begründen keine Verbesserung.

`run` unterstützt zusätzlich `--explanation-depth` und `--prompt-version` für
Deep-Physics-Fälle. Für einen kontrollierten Vergleich von v1 und v2 dient
`compare-prompts`; siehe [ADAPTIVE_DEEP_PHYSICS](ADAPTIVE_DEEP_PHYSICS.md).
Sein Aufrufbudget gilt gemeinsam für beide Arme, nicht jeweils erneut.

Die CLI unterscheidet Exitcode 0 (alle ausgewählten Ablaufstufen abgeschlossen),
1 (Report enthält fehlgeschlagene Fälle) und 2 (CLI-/Konfigurations-/Preflightfehler).
Ein fehlendes Fachurteil ist kein technischer Laufzeitfehler, aber ebenso wenig
eine bestandene wissenschaftliche Bewertung.

## Berichte, Kosten und Urteile

JSON-Berichte enthalten Datasetversion und -hash, Fragen, Quellen-/Originalhashes,
Extraktor- und Promptstand, Kontext-SHA, Modell und wirksame Parameter, Antwort-Hash,
Fehlerstufe, Zeit, vorhandene Token-Usage und einen getrennten Bewertungsbereich.

`source_versions` verfolgt alle für den Fall erlaubten Versionen; `source_context`
enthält nur die tatsächlich vorgelegten Passagen. `source_context_sha256` bindet
diesen konkreten Kontext. Die Adressabdeckung im Kontext
(`context_coverage_expected`) und die erwarteten Stellen, die die Antwort tatsächlich
zitiert (`answer_citation_coverage_expected`), bleiben getrennt. Keine dieser
Abdeckungen beweist inhaltliche Stützung oder physikalische Korrektheit.
Fehler in Setup, Retrieval, Kontext, Mathematik, Generierung und Citation-Vertrag
bleiben unterscheidbar. Eine nicht ausgeführte Generierung zählt nicht als gelöster Fall.

Kosten beruhen ausschließlich auf tatsächlichen Usage-Angaben und dem datierten
öffentlichen Preissnapshot für `gpt-6.1-sol` vom **16. November 2026**:

| Tokenart | USD je Million Tokens |
| --- | ---: |
| Nicht gecachter Input | 2,00 |
| Gecachter Input | 0,10 |
| Separat ausgewiesener Cache-Schreibanteil | 2,50 |
| Output einschließlich Reasoning | 10,00 |

Das ist eine Schätzung, keine Rechnung. Fehlende Usage, ein unbekanntes Modell oder
nicht unterstützte Aufschlüsselung ergeben `estimated_usd=null`; bei Mock wird
keine erfundene reale Usage oder Kostenbeobachtung erzeugt. Reasoning- und Cache-
Unterzähler werden nicht doppelt zu ihren Input-/Output-Oberzählern addiert.
Tools, spezielle Tarife, Steuern und spätere Preisänderungen sind nicht enthalten.

Das [fachliche Raster](TUTOR_EVALUATION.md) bewertet sechs Dimensionen separat
mit **0 bis 4** oder bleibt `not_reviewed`: mathematische Korrektheit,
Herleitungsvollständigkeit, physikalische Voraussetzungen, Interpretation,
Citationgenauigkeit und Unsicherheit. Rechenprüfungen, deterministische Verträge,
Modellurteile und menschliche Urteile werden mit ihrer jeweiligen Methode geführt.
Ein Modellurteil ist keine unabhängige fachliche Prüfung. Hohe Vollständigkeit
(3 oder 4) verlangt explizite Kontrolle **jedes** verpflichtenden Zwischenschritts;
eine richtige Endformel oder Antwortlänge genügt nicht.

Schwere Fehler wie Vorzeichenfehler, ungültige Randbedingungen, erfundene Citations
und unzulässige Verallgemeinerung werden zusätzlich einzeln erfasst und nicht
hinter Stil- oder Durchschnittswerten versteckt. Erklärungsökonomie ist eine
separate, begründete Inhaltsbewertung, kein automatischer Längenwert.

Manuelle oder ausdrücklich gekennzeichnete Modellbewertungen lassen sich als
Review-JSON importieren. `run_id`, `case_id` und `answer_sha256` müssen den exakt
bewerteten Bericht treffen; hohe Vollständigkeitswerte brauchen
`mandatory_steps_checked`. Prüfer, Methode und Begründung bleiben sichtbar:

```sh
uv run --frozen --extra math physics-eval apply-ratings \
  .local/evaluations/mock-concept.json .local/evaluations/reviews.json \
  --output .local/evaluations/mock-concept-reviewed.json
```

Die Datei `reviews.json` wird von den Bewertenden erstellt; der Befehl erzeugt keine
Fachurteile. Reale Qualitätsaussagen benötigen weiterhin unabhängige Fachprüfung,
einen getrennten Testsatz und dokumentierte Wiederholungen.

## Reale Quellen vorbereiten

`validate-import` prüft ein lokales Manifest mit `source_id`, Titel, PDF-Pfad,
SHA-256, `authorization` (`local_only` oder `external_allowed`) und `license_note`:

```sh
uv run --frozen --extra math physics-eval validate-import /pfad/zum/manifest.json
```

Die Prüfung bestätigt lesbare PDF-Bytes, passende Hashes und eine vorhandene
Rechtserklärung. Sie erteilt keine Rechte und bestätigt keine Physik. Der Manifestweg
ist eine vorbereitete Validierungsgrenze, noch kein in den Evaluationsrunner
integrierter Import eines realen Forschungs-/Lehrkorpus. Vor dem nächsten Schritt
werden rechtlich geklärte Quellen, überprüfte Fachlösungen und unabhängige
Annotationen der Quellenstützung benötigt.
