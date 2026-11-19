# Physics Center

Modulare Plattform für das Physikstudium; perspektivisch auch für wissenschaftliche Arbeit.

Aktueller Stand: lokaler FastAPI-/PostgreSQL-Prototyp zur überprüfbaren Verknüpfung
von Themen, Aufgaben und PDF-Abschnitten. Enthalten sind versionierte Originale,
eine austauschbare Analysepipeline, Prüf-/Korrekturendpunkte, Migrationen und
automatisierte Tests. Eine Next.js-Oberfläche gibt es noch nicht.
Hinzu kommt eine quellenkontrollierte Retrieval-/Citation-Engine: lokale
PostgreSQL-Volltextsuche, explizite Versions-/Analyseauswahl, überprüfbare Fundstellen
und ein Tutor-Kontextvertrag ohne Antwortgenerierung.
Darauf baut jetzt ein PhysicsTutorService mit vier Modi, versionierten Prompts,
persistenten Unterhaltungen und optionalen symbolischen Prüfungen auf. Standardmäßig
läuft ein ausdrücklich gekennzeichneter Mock. Der echte Modelladapter ist austauschbar;
seine fachliche Qualität wurde noch nicht mit einem realen Modell evaluiert.

## Einstieg

- [Architektur und Entscheidungen](ARCHITECTURE.md)
- [Anforderungen, Annahmen und Risiken](docs/REQUIREMENTS.md)
- [Datenmodell und Quellenbelege](docs/DATA_MODEL.md)
- [Implementierte Themen- und Aufgabenverknüpfung](docs/KNOWLEDGE_LINKING.md)
- [Retrieval, Citation-Prüfung und reproduzierbares Beispiel](docs/RETRIEVAL.md)
- [Physics Tutor: Ablauf, Modi und Konfiguration](docs/PHYSICS_TUTOR.md)
- [Fachliche Tutor-Evaluation und Referenzaufgaben](docs/TUTOR_EVALUATION.md)
- [Sichere reale Modellanbindung und Evaluations-CLI](docs/REAL_MODEL_EVALUATION.md)
- [Adaptive Erklärungstiefe und kontrollierter Promptvergleich](docs/ADAPTIVE_DEEP_PHYSICS.md)
- [Versionierte Evaluationsfälle und Prüfstatus](docs/EVALUATION_CASES.md)
- [Hybride wissenschaftliche Quellenverwaltung](docs/SOURCE_MANAGEMENT.md)
- [Testvertrag für Quellensteuerung und Belege](docs/SOURCE_MANAGEMENT_TESTS.md)
- [Erweiterungen und wissenschaftliche Nachvollziehbarkeit](docs/EXTENSIONS.md)
- [Roadmap und Akzeptanzkriterien](docs/ROADMAP.md)
- [Entwicklungsumgebung und Prüfstatus](docs/DEVELOPMENT.md)
- [Arbeitsregeln für Entwicklungsagenten](AGENTS.md)

Installation, Migrationen, Start und Tests: [Entwicklungsanleitung](docs/DEVELOPMENT.md).
Der Prototyp ist nur für expliziten lokalen Entwicklungsbetrieb vorgesehen.
Er erkennt Themen anhand eines vorgegebenen Katalogs und einfache Aufgabenüberschriften;
automatische Ergebnisse bleiben Vorschläge. Scans und unsichere Mathematik werden
markiert, nicht durch erfundene Inhalte ergänzt. OCR, produktiver Tutor-Betrieb und
Research-Funktionen folgen später; der Tutor-Prototyp ist kein fachlich abgenommenes System.
Die vollständige hybride Quellenverwaltung ist weiterhin ein Entwurf. Die
Retrieval-API setzt bereits die Quellenbegrenzung und einfache Titelanweisungen um.
Ein optionaler lokaler Embedding-Port ist vorhanden; es ist kein reales Modell
installiert. Eine dialogorientierte Tutor-API ist vorhanden; visuelle Quellenauswahl,
allgemeine natürliche Quellensteuerung und große Vektorindizes fehlen weiterhin.
