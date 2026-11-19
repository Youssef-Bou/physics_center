# Evaluationsfälle: unvalidierte Physik-Kandidaten

Zwei maschinenlesbare Versionen verwenden die Kennung `physics-tutor-candidates`:

| Datei | Version | Umfang |
| --- | --- | --- |
| [physics_v1.json](../apps/api/app/modules/evaluation/data/physics_v1.json) | `1.0.0` | Unveränderte Baseline mit 24 Fällen, genau vier je Kategorie. |
| [physics_adaptive_v1.json](../apps/api/app/modules/evaluation/data/physics_adaptive_v1.json) | `1.1.0` | Dieselben 24 Fälle plus fünf anspruchsvolle Fälle für adaptive Erklärungstiefe, insgesamt 29. |

Die Baseline enthält **24 selbst formulierte Fälle**, jeweils vier in den sechs
Kategorien Herleitung, Konzeptverständnis, Klausuraufgabe, Gültigkeitsgrenzen,
Quellenarbeit und sokratische Erstinteraktion. Die Erweiterung fügt drei
Herleitungsfälle, einen Konzeptfall und einen Grenzfall hinzu; sie ist deshalb
nicht mehr gleichmäßig auf die Kategorien verteilt. Die ursprüngliche Datei und
ihre 24 Fälle bleiben unverändert.

Beide Versionen sind Kandidatenbestände für kontrollierte Tests, **keine fachlich
validierten Goldstandards**. Es wurden damit noch keine Qualitätswerte eines realen
Modells gemessen. Die Erweiterung erzeugt allein durch anspruchsvollere Aufgaben
auch keinen Nachweis erfolgreicher adaptiver Tutorleistung.

Alle `validation`- und Quellen-`physical_review`-Datensätze tragen
`status=unvalidated`, ohne erfundene Prüfernamen oder Prüfzeitpunkte. Die Lösungen
sind ausdrücklich Referenzkandidaten. Vor einer Fachabnahme brauchen sie unabhängige
Prüfung und gegebenenfalls Korrektur; Plausibilität oder ein erfolgreicher
Schemacheck ersetzen diese Prüfung nicht.

## Bestand

| Fall-ID | Kategorie | Fachlicher Schwerpunkt | Schwierigkeit / Modus |
| --- | --- | --- | --- |
| `DER_OSCILLATOR` | derivation | Oszillator mit zwei Anfangswerten, Energie und Einheiten | intermediate / DEEP_PHYSICS_MODE |
| `DER_CENTRAL_FORCE` | derivation | Drehimpuls bei zeitabhängiger Zentralkraft | intermediate / DEEP_PHYSICS_MODE |
| `DER_VACUUM_WAVE` | derivation | Maxwell, Transversalität, Dispersion, Poyntingvektor | advanced / DEEP_PHYSICS_MODE |
| `GREEN_DIRICHLET` | derivation | Konstruktion und Eindeutigkeit eines Dirichlet-Greenkerns | advanced / DEEP_PHYSICS_MODE |
| `CON_GAUSS_FLUX` | concept | Nullfluss bedeutet kein punktweises Nullfeld | foundational / DEEP_PHYSICS_MODE |
| `CON_QM_COHERENCE` | concept | Kohärente Überlagerung versus statistische Mischung | intermediate / DEEP_PHYSICS_MODE |
| `CON_ENTROPY_ISOLATED` | concept | Gesamtentropie und Entropie eines Teilsystems | intermediate / DEEP_PHYSICS_MODE |
| `CON_FOURIER_L2` | concept | Orthogonalität und Konvergenzsinn der Sinusreihe | intermediate / DEEP_PHYSICS_MODE |
| `EXAM_OSCILLATOR` | exam | Synthetische Zahlenaufgabe zu Frequenz und Energie | foundational / EXAM_MODE |
| `EXAM_CAPACITOR` | exam | Isolierter Kondensator mit fester Ladung | intermediate / EXAM_MODE |
| `EXAM_BOX_PHOTON` | exam | Kastenenergien, Photonfrequenz und Winkelfrequenz | intermediate / EXAM_MODE |
| `EXAM_ISOTHERMAL` | exam | Reversible isotherme Expansion und Vorzeichen | intermediate / EXAM_MODE |
| `LIMIT_OSCILLATOR_FREE` | limits | Fester-Zeit-Grenzwert zur freien Bewegung | intermediate / DEEP_PHYSICS_MODE |
| `LIMIT_GAUSSIAN_SPREAD` | limits | Dispersion, Unschärfeprodukt und Korrelation | advanced / DEEP_PHYSICS_MODE |
| `LIMIT_GAUSS_ASYMMETRY` | limits | Grenzen einer symmetriebasierten Feldberechnung | intermediate / DEEP_PHYSICS_MODE |
| `LIMIT_CLASSICAL_GAS` | limits | Nichtentartung und unzulässige Tieftemperaturextrapolation | advanced / DEEP_PHYSICS_MODE |
| `SOURCE_DREHIMPULS` | source | Definition aus einer konkret gebundenen Quelle | foundational / SOURCE_MODE |
| `SOURCE_GAUSS_CLOSED` | source | Geschlossene orientierte Oberfläche im Originaltext | foundational / SOURCE_MODE |
| `SOURCE_GAUSSIAN_CONVENTIONS` | source | Vergleich zweier Breitenkonventionen mit zwei Belegen | intermediate / SOURCE_MODE |
| `SOURCE_GREEN_MISSING_BC` | source | Gezielte Evidenzlücke: Randbedingungen fehlen | advanced / SOURCE_MODE |
| `SOC_OSCILLATOR_SIGN` | socratic | Eine Frage zum falschen Rückstellvorzeichen | foundational / SOCRATIC_MODE |
| `SOC_CAPACITOR_CONSTRAINT` | socratic | Ladung oder Spannung als Nebenbedingung klären | intermediate / SOCRATIC_MODE |
| `SOC_QM_DENSITY` | socratic | Amplitude und Dichte über einen Hinweis trennen | intermediate / SOCRATIC_MODE |
| `SOC_GREEN_RIGHT_BOUNDARY` | socratic | Rechte Randbedingung eines Kernansatzes prüfen | advanced / SOCRATIC_MODE |

## Fünf zusätzliche anspruchsvolle Fälle in Version 1.1.0

Alle folgenden Fälle sind `advanced`, verwenden `DEEP_PHYSICS_MODE` und bleiben
`unvalidated`:

| Fall-ID | Kategorie | Fachliche Pflichtpunkte |
| --- | --- | --- |
| `VARIATIONAL_EULER_LAGRANGE` | derivation | Reguläre Variation, feste Endzeiten/-werte, expliziter Randterm, partielle Integration, Fundamentallemma, Stationarität versus Minimum. |
| `ELECTROSTATIC_GREEN_DIRICHLET` | derivation | Poissonproblem mit zwei vorgegebenen Potentialwerten, Delta-Sprung, homogene Randwertergänzung, Eindeutigkeit, konstante Ladung und Einheiten. |
| `QM_COMMUTATOR_DOMAIN` | concept | Kanonischer Kommutator auf Schwartzfunktionen, unbeschränkte Produktdomänen, periodisches Intervall als Randbedingungskontrolle, keine pauschale Unschärfebehauptung. |
| `FOURIER_HEAT_EQUATION` | derivation | Explizite Fourierkonvention, modale Diffusion, normierter Gaußkern, Anfangswertgrenze, räumliche Integralserhaltung, Lösungsklasse und Rückwärtsinstabilität. |
| `MECHANICS_PENDULUM_LIMIT` | limits | Nichtlineare Euler-Lagrange-Gleichung, zwei Anfangswerte, echte Kleinamplitudenbedingung, endliche Amplitude und Separatrix. |

Die erweiterten Quellen bleiben acht synthetische Dokumente. Fünf zusätzliche
ASCII-Seiten wurden in der **neuen Datasetversion** an passende Quellen angehängt;
die ursprünglichen Seiten und deren Zitatpositionen bleiben erhalten. Quellen-IDs
allein dürfen nicht als versionsübergreifend identischer Inhalt behandelt werden:
Datensatzversion und die tatsächlich erzeugten Dokumenthashes gehören zur Bindung.
Die Erweiterung enthält keine vorgeblich empirisch geprüften Formeln und keine
neuen komplexen Rechenaufträge an den begrenzten Mathematikadapter.

Jeder Fall enthält Frage, Voraussetzungen, Referenzkandidat, Kriterien,
Pflichtschritte, typische Fehler, erlaubte Quellenbindungen, erwartete Originalstellen,
Retrievalanfrage und gegebenenfalls begrenzte mathematische Teilprüfungen.
`mandatory_steps` sind fachliche Prüfanforderungen; das bloße Vorkommen ihrer Wörter
in einer Modellantwort beweist weder Richtigkeit noch Vollständigkeit.

## Kontrollierte Quellen statt scheinbarer Originaldokumente

Acht selbst verfasste Quellenfixtures decken Mechanik, Elektrodynamik,
Quantenmechanik, Thermodynamik und mathematische Methoden ab. Dazu kommen ein
synthetisches Klausurblatt, ein Hinweisblatt und ausdrücklich begrenzte oder
abweichend parametrisierte Quellenangaben. Keine Universität, Professur oder
veröffentlichte Prüfung wird damit nachgebildet oder als Urheber genannt.

Die Quellseiten sind ASCII-Texte für eine reproduzierbare einfache PDF-Erzeugung.
Alle sind als `rights_status=synthetic` markiert; `external_use_allowed=true` gilt
für diese selbst erzeugten Fixtures, nicht pauschal für spätere Uploads. Ihre
physikalischen Inhalte sind trotz kontrollierter Schreibweise unvalidiert.
Die bekannte Quellenposition bedeutet nur, dass ein erwartetes Zitat tatsächlich
auf der angegebenen synthetischen Seite steht.

`expected_sources` bindet wörtliche Zitate und 1-basierte physische Fixture-Seiten.
Das Datenschema prüft diese Bindung gegen den tatsächlich gespeicherten Quelltext.
Es erzeugt keine beliebigen Seitenzahlen und bestätigt nicht automatisch, ob das
Zitat eine komplexe Modellbehauptung inhaltlich stützt. Vier Quellenfälle prüfen
insbesondere Quellenwiedergabe, Konventionsvergleich und das Offenlegen einer
absichtlich fehlenden Randbedingung.

## Besonderer Vollständigkeitsfall: `GREEN_DIRICHLET`

Der Fall fixiert den Operator `A=-d²/dx²` auf `(0,L)` mit `L>0`, homogenen
Dirichlet-Rändern und stetiger Quelle. Der Referenzkandidat
`G(x,xi)=x_<*(L-x_>)/L` ist nur ein Teil der erwarteten Bearbeitung.

Die Pflichtschritte verlangen zusätzlich:

- lineare homogene Zweige außerhalb der Quelle und beide Randbedingungen;
- Stetigkeit, den korrekten Sprung `G_x(xi+)-G_x(xi-)=-1` und die Vermeidung
  eines zusätzlichen Delta-Ableitungsterms;
- `-d_x²G=delta(x-xi)` im distributionellen Sinn und die Integraldarstellung für `u`;
- Existenz im angegebenen regulären Fall und Eindeutigkeit über die triviale
  homogene Dirichlet-Lösung bzw. ein passendes Energieargument;
- die homogene Mehrdeutigkeit ohne Randbedingungen und konsistente Dimensionen.

Wer nur den Kern hinschreibt, erfüllt diese Anforderungen nicht. Bei einer
Längenkoordinate hat `G` die Einheit einer Länge und die Delta-Distribution die
einer inversen Länge. Der beigefügte kurze symbolische Sprungcheck bestätigt
höchstens diese eine algebraische Identität, nicht die gesamte Greenkonstruktion.

## Begrenzte Mathematikprüfungen und sokratische Fälle

Fünf kleine `MathCheckRequest`-Einträge verwenden ausschließlich die vorhandene
begrenzte AST-Sprache. Sie prüfen etwa eine Oszillatorableitung, eine numerische
Energiesumme, einen Ableitungssprung und einzelne Ableitungen. Ein erfolgreicher
Toolstatus ist keine Prüfung der physikalischen Modellannahmen, des Quellbelegs
oder der vollständigen Herleitung. Fehlende bzw. unentschiedene Werkzeugresultate
bleiben als solche sichtbar.

Die vier sokratischen Fälle bewerten ausdrücklich nur eine erste gezielte
Interaktion auf einen falschen oder unvollständigen Ansatz. Sie erheben weder
langfristigen Lernerfolg noch personalisierten Kenntnisstand. Das ungefragte
Ausgeben der vollständigen Lösung ist hier eine Verfehlung des vereinbarten
Hinweisgrads, auch wenn die Lösung mathematisch korrekt sein sollte.

## Offene Fachprüfung und nächster Datensatz

Die Aufgaben sind bewusst klein und kontrolliert. Nicht ausreichend abgedeckt sind
reale mehrspaltige PDFs, fehlerhafte Formel-OCR, anspruchsvolle Randwertoperatoren,
allgemeine komplexe Quantenrechnung und stoffabhängige Grenzfälle. Referenzantworten
können weiterhin Fehler oder zu starke Vereinfachungen enthalten. Insbesondere
brauchen Operatordomänen und Unschärfeaussagen, Existenz-/Eindeutigkeitsklassen
von Randwert- und Wärmeproblemen sowie Langzeitfehler der Pendelnäherung eine
eigenständige mathematische Fachprüfung. Die gelisteten Pflichtschritte sind eine
Prüfvorlage und kein Ersatz für diese Prüfung.

Benötigt werden unabhängige fachliche Reviews mit dokumentierten Urteilen und
realen rechtlich verwendbaren Quellstellen, ein separater Testsplit und klar
festgelegte Fehlerkosten. Der Kandidatenbestand selbst darf nicht zugleich als
unabhängige Referenz seiner eigenen Erzeugung ausgegeben werden. Das allgemeine
Bewertungsverfahren und seine sechs getrennten Dimensionen stehen in
[TUTOR_EVALUATION](TUTOR_EVALUATION.md).
