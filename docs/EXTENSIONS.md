# Erweiterungspfade

Dieses Dokument beschreibt weiterführende Integrationspunkte. Ein begrenzter
PDF-/Analyse-/Review-Kern ist in [KNOWLEDGE_LINKING](KNOWLEDGE_LINKING.md) bereits
implementiert; die hier beschriebenen OCR-, Retrieval-, Tutor- und Research-Ausbaustufen
sind weiterhin geplant.
Ein erster [Tutor-Backend-Schnitt](PHYSICS_TUTOR.md) ist inzwischen vorhanden;
die nachstehenden Tutor-Punkte betreffen darüber hinausgehende Fachabnahme,
semantische Belegprüfung und produktiven Betrieb. Der Standardprovider ist ein Mock.
Jede Erweiterung benötigt eigene Migrationen, Qualitätskriterien und Datenschutzprüfung.
Für Quellensteuerung, Abrufgrenzen und Antwortbelege gilt die
[hybride Quellenverwaltung](SOURCE_MANAGEMENT.md); das gemeinsame Modul wird von
Study und Research verwendet.

## Dokumentverarbeitung und Retrieval

Die weiterführende Extraktionspipeline soll ausschließlich freigegebene `ready`-Versionen
aus dem Dateispeicher. ExtractionRun erfasst Originalhash, Parser-/OCR-Version,
Parameter, Zeitpunkt, Status und Fehler. Abgeleitete Segmente behalten Seiten- und
gegebenenfalls Bereichskoordinaten; Ergebnisse ersetzen nie das Original.
Wiederholung mit gleichem Input und derselben Konfiguration ist idempotent.

Lange OCR-Aufgaben rechtfertigen einen separaten Workerprozess aus derselben
Codebasis. Eine persistente Jobtabelle ermöglicht Wiederholung und Fehlerdiagnose;
ein eigener Broker erst bei nachgewiesenem Bedarf. Keine langlaufende OCR im
HTTP-Request oder nur im flüchtigen FastAPI-Hintergrundtask.

Phase 2b implementiert klassische Volltextsuche und semantische Suche mit pgvector
als verbindliche Bestandteile des Features. Ein kuratiertes Physik-Testset prüft
beide Pfade und deren Fusion. Embeddings tragen Modell, Dimension, Segment- und
Extraktionsversion; Modellwechsel erzeugen einen neuen Index. Projekt-, Versions-
und Turnfilter gelten vor dem Abruf und Ranking beider Suchpfade. Eine globale
Suche mit nachträglichem Aussortieren ist unzulässig. Vektorähnlichkeit allein
begründet keine fachliche Aussage. ANN-Optimierung bleibt bedarfsabhängig.

## KI-Tutor

Ein Tutor-Anwendungsfall orchestriert Kontextauswahl, Provideraufruf und validierte
Antwort. Ein kleiner fachlicher Port nimmt Nachrichten, Quellenkontext, gewünschtes
Ausgabeformat sowie Zeit-/Tokenbudget entgegen. Adapter übersetzen für konkrete
Anbieter. Modellname, Fähigkeiten (z. B. strukturierte Ausgabe), Kostenlimits,
Timeout und Retrystrategie sind serverseitige Konfiguration. Ein anderer Anbieter
muss denselben Vertragstest bestehen; Funktionsgleichheit wird nicht unterstellt.

Eine Antwort enthält Aussage/Herleitung, Annahmen, verwendete Quellenreferenzen und
explizite Unsicherheit; Aussageblöcke unterscheiden Quellenbeleg, Eigenableitung
und ergänzendes Modellwissen. Beleg-IDs müssen zu mitgesendetem Kontext, Turn und
Projekt gehören und auf geprüfte Originalstellen zurückgehen. Die inhaltliche
Stützung wird separat geprüft. Ungültige oder unzureichende Belege verhindern die
Freigabe als quellenbelegte Aussage; im strikten Quellenmodus erscheint stattdessen
ein Lückenhinweis. Dokumenttext ist untrusted input, keine Systemanweisung.
Toolaufrufe sind erlaubnisbeschränkt; keine freie Shell oder Codeausführung.

Natürliche Quellenanweisungen liefern lediglich Auswahlvorschläge. Einschränkungen
verwenden den gemeinsamen Auswahlkern, Erweiterungen brauchen die sichtbare
Bestätigung einer konkreten Versionsmenge. Der Provider kann keine Quelle aktivieren.

Für Nachvollziehbarkeit werden Provider-/Modellkennung, Promptvorlagenversion,
Parameter, freigegebene Kontextversionen und Ergebnis gespeichert. Keine internen
Gedankenketten verlangen oder speichern; prüfbare Rechenschritte und Belege genügen.
Providerkennungen garantieren keine bitgenaue Reproduzierbarkeit. Nutzer müssen
externen Dokumentversand freigeben können; standardmäßig bleibt dieser deaktiviert.

Mathematische Prüfungen mit SymPy/NumPy sind getrennte Werkzeuge mit expliziten
Variablen, Einheiten, Definitionsbereichen und Toleranzen. Keine Auswertung beliebiger
Python-Eingaben. Evaluation umfasst bekannte Aufgaben, falsche Belege, fehlenden
Kontext, Grenzfälle und Prompt-Injection; Faktenfehler und Belegabdeckung werden
getrennt gemessen. KI-Ausgaben bleiben als solche erkennbar.

## Klausuranalyse und Lernplaner

Klausuranalyse baut auf versionierter Extraktion auf. Ein AnalysisRun liefert
Aufgabenvorschläge, Teilaufgaben, Themenzuordnungen, Punktzahlen und Belege. Zuerst
prüft und korrigiert der Nutzer; erst bestätigte Daten fließen in die Lernplanung.
Unsicherheit bei Formeln, Seiten oder Aufgabenstruktur bleibt sichtbar.

Der Lernplaner verwendet Aufgaben, beobachteten Fortschritt, Themenvoraussetzungen,
Prüfungstermin und verfügbare Zeit. Zunächst genügt ein deterministischer,
erklärbarer Algorithmus mit editierbaren Ergebnissen. Planversionen speichern
Eingabestand und Regelversion; KI darf Vorschläge erläutern, entscheidet aber nicht
unbemerkt über Lerndefizite. Kein aus bloßer Chataktivität erfundener Kompetenzwert.

## Research Workspace

Neue Module ergänzen Literaturimport (z. B. DOI/BibTeX), Notizrevisionen,
Herleitungen, LaTeX-Quellen und Analyseartefakte am bestehenden Projekt-/Quellenkern.
ResearchNote und Derivation können dieselben versionierten Fundstellen verwenden.
Eine Umwandlung bestehender Study-Projekte wird nicht automatisch vorausgesetzt.

Reproduzierbare Analysen benötigen Eingabehashes, Code-/Commitstand,
Abhängigkeitslock, Parameter, Zufallsseeds und gespeicherte Ergebnisartefakte.
LaTeX-Kompilierung und Notebook-/Codeausführung laufen später in isolierten,
ressourcenbegrenzten Prozessen ohne impliziten Netzwerk- oder Secretzugriff.
Ein vollständiges Forschungs-Ausführungssystem entsteht erst mit diesem Bedarf.
