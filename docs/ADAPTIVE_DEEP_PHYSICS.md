# Adaptive Erklärungen im Deep-Physics-Modus

Die optionale Erweiterung verändert die **Darstellung** einer Physikerklärung,
nicht Quellenrechte, verfügbare Werkzeuge oder den Reasoning-Aufwand des Modells.
Sie ist ausschließlich für `DEEP_PHYSICS_MODE` vorgesehen. Die bestehenden Modi,
das alte `depth`-Feld und `physics-tutor-v1` bleiben nutzbar. Eine neue
Erklärungstiefe belegt keine verbesserte fachliche Qualität eines realen Modells.

Grundlage: [Physiktutor](PHYSICS_TUTOR.md),
[reale Modelle und Evaluation](REAL_MODEL_EVALUATION.md) sowie
[Bewertungsraster](TUTOR_EVALUATION.md).

## API und Priorität

`POST /api/v1/projects/{project_id}/tutor/answers` unterstützt zusätzlich:

| Feld | Bedeutung |
| --- | --- |
| `explanation_depth` | Optional `STANDARD`, `DETAILED`, `RIGOROUS` oder `AUTO`; nur im Deep-Physics-Modus. |
| `prompt_version` | Optional `physics-tutor-v1` oder `physics-tutor-v2`; v2 gilt nur für Deep Physics. |
| `depth` | Bisheriges `concise`, `standard` oder `deep`, weiterhin akzeptiert. |

Ohne neue Angabe bleibt v1 Standard. Eine neue `explanation_depth` wählt v2,
sofern nicht ausdrücklich eine Promptversion angegeben wurde. Eine explizite
Version geht vor; `explanation_depth` zusammen mit v1 ändert nicht heimlich den
alten Prompt. Für den Vergleich kann deshalb dieselbe Anfrage ausdrücklich
unterschiedliche Promptversionen wählen. Der ursprüngliche v1-Systemprompt bleibt
bei gleichen alten Parametern bytegleich.

Die effektive Tiefe wird deterministisch aufgelöst:

1. Eine explizite neue Tiefe außer `AUTO` gewinnt, auch gegenüber altem `depth`.
2. `AUTO` überschreibt kein ausdrücklich übermitteltes altes `depth`.
3. Ohne ausdrückliche neue Tiefe bleibt die alte Zuordnung erhalten:
   `concise`/`standard` entsprechen im Plan `STANDARD`, `deep` entspricht `DETAILED`.
4. Nur ein tatsächlich freigegebenes `AUTO` verwendet die unten beschriebenen Regeln.

Die API erkennt ausdrücklich übermittelte alte Felder, auch wenn ihr Wert dem
bisherigen Default entspricht. Ein Client, der `AUTO` nutzen möchte, sollte deshalb
kein altes `depth` automatisch mitsenden. In anderen Modi erzeugt die neue
Erklärungstiefe bzw. v2 einen validierbaren Fehler, keine still ignorierte Einstellung.

Die Antwort führt `prompt_version`, `explanation_depth` und `explanation_plan` mit
`requested`, `effective`, `selection_source`, `reasons`, ausgewählten `aspects`
und `heuristic_calibrated=false`. Der Plan liegt mit dem ursprünglichen Kontext
im gespeicherten Tutor-Turn; die vorhandene Datenbankstruktur genügt dafür.

## Was die drei Tiefen bedeuten

| Effektive Tiefe | Erwartete Darstellung |
| --- | --- |
| `STANDARD` | Kernaussage, nötige Begriffe und Voraussetzungen, angemessene Gleichungen und Schritte; keine künstlich lange Nebenrechnung. |
| `DETAILED` | Nachvollziehbarer Ansatz und kritische Zwischenschritte, Größen, Einheiten, relevante Näherungen und Kontrollen. |
| `RIGOROUS` | Relevante Definitionsbereiche, Regularität, Randbedingungen und Konventionen; kritische Übergänge, notwendige/hinreichende Bedingungen und geeignete Gegen- oder Grenzfälle. |

Keine Stufe erzwingt eine Wortzahl oder eine starre Überschriftenfolge. Eine kurze
Begriffsfrage braucht auch bei hoher Tiefe keine irrelevante Abhandlung; eine
schwierige Herleitung darf bei knapper Darstellung keine notwendigen Voraussetzungen
verschweigen. Gefordert werden prüfbare Argumente und Rechenschritte, keine internen
Gedankenketten eines Sprachmodells.

## AUTO als transparente Heuristik

Die Regeln in [adaptive.py](../apps/api/app/modules/tutor/adaptive.py) erkennen
beispielsweise Beweis-/Gegenbeispielanfragen, Herleitungen und Rechnungen sowie
anspruchsvollere Randbedingungen, Distributionen oder Definitionsbereiche.
Beweis-/Gegenbeispielanfragen und bestimmte Kombinationen formaler Anforderungen
wählen `RIGOROUS`; Rechnungen/Herleitungen typischerweise `DETAILED`, einfache oder
unspezifische Begriffsfragen `STANDARD`.

Das ist keine empirisch kalibrierte Schwierigkeitsschätzung. Sprache, Fachwortwahl
und Formulierungen können die Auswahl fehlleiten. Die Antwort zeigt deshalb
Regelgründe, und der Nutzer kann eine Tiefe ausdrücklich festlegen. AUTO ändert
weder `reasoning_effort` noch `max_output_tokens`, Temperatur, Kontextbudget,
Quellenfilter, Zugriff oder Mathematikoperationen. Größere Tiefe ist keine Zusage
höherer Richtigkeit und keine automatische Erlaubnis höherer Modellkosten.

## Neun situative Aspekte

Der Plan wählt relevante Aspekte aus dieser festen, nachvollziehbaren Liste:

- Problem und gesuchte Größen.
- Definitionen und verwendete Begriffe.
- Mathematische Voraussetzungen und Definitionsbereiche.
- Gleichungen und Konventionen.
- Prüffähige Herleitungsschritte.
- Physikalische Interpretation.
- Gültigkeit, Näherungen und Grenzen.
- Einheiten-, Rand- oder Grenzfallkonsistenz.
- Begründete fachliche Verbindungen.

Dies sind keine neun Pflichtabschnitte jeder Antwort. Die Auswahl enthält nur
vertrauenswürdige Anwendungslabels; Nutzereingaben und Quelltexte werden nicht in
den Systemprompt eingesetzt. Die eigentliche Frage bleibt im Benutzerdatenblock.
Fachliche Voraussetzungen dürfen weiterhin nicht aus bloßer Begriffsähnlichkeit
oder einem hohen Suchrang abgeleitet werden.

## Herkunft und Validierung

v2 beschreibt vier Herkunftskategorien für Antwortblöcke:

| Kategorie | Aussage |
| --- | --- |
| `source_content` | Aussage mit einer bereitgestellten, auflösbaren Citation; die tatsächliche inhaltliche Stützung ist zusätzlich zu prüfen. |
| `derivation` | Eigene nachvollziehbare Ableitung aus ausdrücklich genannten Voraussetzungen. |
| `model_knowledge` | Ergänzendes Modellwissen, sichtbar getrennt vom Quelleninhalt. |
| `unverified_assumption` | Unbelegte oder noch ungeprüfte Voraussetzung; keine stillschweigende Aufwertung zu gesichertem Quellenwissen. |

Der gemeinsame Antwortvertrag kann diese Kategorien transportieren. Der
`SOURCE_MODE` bleibt eigenständig und erlaubt weiterhin kein ergänzendes
Modellwissen. Strukturvalidierung prüft Typen, Citation-IDs, Scope, Filter,
Locatorpositionen und vorhandene Werkzeugreferenzen. Sie prüft keine allgemeine
Wahrheit einer Aussage und beweist nicht, dass eine auflösbare Citation die
Behauptung inhaltlich stützt.

Ein austauschbarer `SemanticEvidenceChecker`-Port trennt eine spätere fachliche
Stützungsprüfung von diesen Strukturregeln. Der aktuelle
`NotCheckedEvidenceChecker` liefert ausdrücklich `not_checked`; er ruft kein Modell
auf und erfindet kein positives Urteil. Auch ein späterer Modellgutachter wäre als
`model_judgment` zu kennzeichnen und kein unabhängiger wissenschaftlicher Beweis.

Die bestehende Quellen- und Historienkontrolle bleibt erhalten: konkrete
Dokument-/Analysestände, Einschränkung statt stiller Erweiterung, erneute Prüfung
nach Werkzeuglatenz und vor/nach Modellaufruf sowie keine ungeprüfte Übernahme
fremder Assistant-Historie. Antworten aus anderen Promptversionen werden nicht
unbemerkt als passend formatierter Dialogkontext weiterverwendet.

## Begrenzte symbolische Grenzwertprüfung

Die optionale Mathematikschnittstelle unterstützt jetzt auch `operation=limit`.
Ein Beispiel für einen ausdrücklich angeforderten Werkzeugcheck, kein bereits
behauptetes Prüfergebnis:

```json
{
  "id": "limit_sinc",
  "operation": "limit",
  "expression": "sin(x)/x",
  "variables": ["x"],
  "variable": "x",
  "point": "0",
  "direction": "both",
  "expected": "1"
}
```

Endliche Annäherungspunkte müssen sichere geschlossene Ausdrücke sein; außerdem
sind `oo` und `-oo` zulässig. `direction` ist `+` (von rechts), `-` (von links)
oder `both`; bei Unendlich bestimmt das Vorzeichen des Ziels die reale Annäherung.
Zweiseitige
Grenzwerte vergleichen die zulässigen einseitigen Annäherungen. Unterschiedliche,
oszillierende oder nicht ausreichend geklärte reale Grenzwerte ergeben
`inconclusive`, statt eine Gleichheit vorzutäuschen. Punkt, Richtung und
Definitionsbedingungen werden im Ergebnis genannt.

Die bisherige AST-Whitelist und das isolierte Zwei-Sekunden-Rechenbudget gelten
weiter. Der Prozessstart einschließlich SymPy-Import ist separat auf fünf Sekunden
begrenzt; ein Ready-Handshake trennt beide Phasen. Es gibt keine freie
Python-Auswertung, keine allgemeine Beweisautomatik und
keine vollständige Prüfung von Quantenmechanik, Distributionen oder
Funktionalanalysis. Ohne installiertes `math`-Extra kann das Werkzeug `unavailable`
melden. Jedes Ergebnis behält `physics_proof=false`; ein symbolisch geprüfter
Grenzwert bestätigt nicht das physikalische Modell einer gesamten Antwort.

## Kontrollierter Vergleich und nächste Abnahme

Der separate Datensatz
[physics_adaptive_v1.json](../apps/api/app/modules/evaluation/data/physics_adaptive_v1.json)
hat die Kennung `physics-tutor-candidates`, Version `1.1.1`, und 29 Fälle.
Die ursprünglichen 24 Fälle bleiben in `physics_v1.json` Version `1.0.0`
unverändert verfügbar. Hinzu kommen fünf anspruchsvolle Deep-Physics-Kandidaten:

| Case-ID | Fachlicher Prüfgegenstand |
| --- | --- |
| `VARIATIONAL_EULER_LAGRANGE` | Variationsprinzip, zulässige Variationen und Euler-Lagrange-Gleichung. |
| `ELECTROSTATIC_GREEN_DIRICHLET` | Poissonproblem und inhomogene Dirichlet-Randwerte. |
| `QM_COMMUTATOR_DOMAIN` | Kanonischer Kommutator und gemeinsame Operatordomänen. |
| `FOURIER_HEAT_EQUATION` | Fourierlösung der Wärmegleichung und Gültigkeitsbedingungen. |
| `MECHANICS_PENDULUM_LIMIT` | Pendel, Variationsgleichung und Kleinwinkelgrenze. |

Alle Referenzkandidaten und Quellen bleiben `unvalidated`; es sind keine
Prüfernamen oder Prüfzeitpunkte erfunden. Die Quellen sind acht ausdrücklich
synthetische ASCII-PDF-Fixtures, keine echten Vorlesungsskripte. Neue Seiten sind
angehängt; die bisherigen 24 Fälle und ihre erwarteten Stellen bleiben erhalten.
Für den erweiterten Bestand `--dataset` ausdrücklich setzen. Ein normaler Lauf
hat weiterhin `--limit 24` als Default; alle 29 Fälle erfordern `--limit 29`.

Ein Promptvergleich muss dieselben Fragen, Quellenpassagen und wirksamen
Modellparameter verwenden. Der tatsächliche gepackte Kontext wird gehasht;
unterschiedliche Kontext-SHA-Werte sind kein kontrollierter Promptvergleich.
Die Baseline bleibt v1, die neue Bedingung verwendet v2. Es gibt keine automatische
Promptoptimierung oder Anpassung an bereits betrachtete Testantworten.

Die CLI `compare-prompts` wählt ohne ausdrückliche Fallauswahl nur
`DEEP_PHYSICS_MODE`-Fälle. Die beiden Promptversionen sind fest v1 und v2; es gibt
keine separaten Links-/Rechts-Versionflags. `--explanation-depth AUTO` ist für
diesen Vergleich voreingestellt und lässt sich ausdrücklich ändern. Der Runner
teilt Fixture bzw. End-to-end-Projekt, Originalversionen und Quellenauswahl zwischen
beiden Armen; ein unterschiedlicher gepackter Kontext wird nicht als kontrollierter
Vergleich ausgewiesen.

Im Verzeichnis `apps/api`, ohne externen Modellaufruf:

```sh
uv run --frozen --extra math physics-eval compare-prompts --provider mock \
  --method isolated --case-id CON_GAUSS_FLUX --limit 1 \
  --explanation-depth AUTO --output .local/evaluations/prompts-mock.json
```

Mit bewusst aktivierter realer Verarbeitung und sicher gebundenem Schlüssel
gemäß [REAL_MODEL_EVALUATION](REAL_MODEL_EVALUATION.md) würde ein einzelner
Fragevergleich **zwei** Modellversuche benötigen:

```sh
uv run --frozen --extra math physics-eval compare-prompts \
  --provider openai_responses --model gpt-6.1-sol --reasoning-effort medium \
  --method isolated --case-id CON_GAUSS_FLUX --limit 1 \
  --explanation-depth AUTO --allow-paid --allow-unvalidated --max-calls 2 \
  --output .local/evaluations/prompts-real.json
```

Dies ist eine Anleitung, kein durchgeführter kostenpflichtiger Vergleich.
`--max-calls` zählt beide Arme gemeinsam einschließlich Fehlversuchen. Höchstens
zehn reale Aufrufe erlauben daher höchstens fünf vollständige Fragepaare; ein
unzureichendes Budget wird vor Versand abgewiesen. Auch End-to-end-Vergleiche
verwenden dieselbe laufbezogene Datenbank-/Dateibasis für beide Arme.

Die zusätzliche Bewertung **Erklärungsökonomie** fragt, ob alle nötigen Schritte
zweckmäßig und ohne unnötige Wiederholung erklärt sind. Sie ersetzt weder
mathematische Korrektheit noch Vollständigkeit und darf nicht aus Antwortlänge
berechnet werden. Ein Mock-A/B-Lauf prüft nur die Vergleichsmechanik; er misst
weder fachliche Verbesserung noch bessere Erklärungsökonomie eines realen Modells.

Unabhängig bewertete, fachlich annotierte Antworten und ein rechtlich verwendbares
Quellenkorpus bleiben erforderlich. Der neue Kandidatenbestand und die CLI-
Vergleichsschritte werden mit ihren tatsächlichen Versions-/Hashangaben geführt;
keine synthetische Referenz wird durch einen bestandenen Test zum Goldstandard.
