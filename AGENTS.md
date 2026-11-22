# Arbeitsregeln

## Auftrag und Orientierung

Lies README.md, ARCHITECTURE.md und die für den Auftrag relevanten Dokumente unter
docs/. Implementiert ist ein begrenzter lokaler Backend-Prototyp in apps/api für
Themen-/Aufgabenverknüpfung, siehe docs/KNOWLEDGE_LINKING.md. Der übrige Study Workspace,
Frontend und vollständige hybride Quellensteuerung sind weiterhin Entwürfe. Lokale
Volltextsuche, Scope-Steuerung und Citation-Prüfung sind inzwischen implementiert,
siehe docs/RETRIEVAL.md. Tutor-API, Providerport, Prompts und optionale sichere
Symbolik sind in docs/PHYSICS_TUTOR.md dokumentiert. Mock-Tests belegen keine
reale LLM-Fachqualität. Bezeichne geplante Funktionen niemals als bereits vorhanden.

Nutze den bestehenden Checkout. Cloud-Aufgaben sind bereits isoliert; erstelle
keinen zusätzlichen Git-Worktree ohne ausdrücklichen Nutzerauftrag.

## Umsetzung

- Implementiere kleine vertikale Schritte gemäß docs/ROADMAP.md. Keine vorgezogenen
  KI-, OCR-, Vektor-, Research- oder Microservice-Funktionen.
- Explizite neue Nutzeraufträge dürfen den Roadmap-Schnitt erweitern. Automatische
  Links bleiben Vorschläge; semantische Ähnlichkeit darf nie eine Voraussetzung
  begründen. Manuelle Entscheidungen und ihre Originalbelege bei Neuanalyse erhalten.
- Halte UI, Anwendungsfälle, Domänenregeln und Infrastruktur getrennt.
  Fachregeln gehören nicht in React-Komponenten, HTTP-Routen oder Provideradapter.
- PostgreSQL ist die maßgebliche Datenquelle. Schemaänderungen brauchen versionierte
  Migrationen; Tests für Constraints müssen gegen PostgreSQL laufen.
- Prüfe Projektzugehörigkeit und Berechtigung für jeden Zugriff, einschließlich
  verschachtelter Ressourcen, Dateiabruf und Hintergrundaufträge.
- Gib Quellenverweise auf unveränderliche Dokumentversionen zurück. Erfinde keine
  Seitenzahlen, Zitate, Modellantworten oder wissenschaftlichen Belege.
- Beachte docs/SOURCE_MANAGEMENT.md: Quellenfilter gelten vor jedem Retrievalpfad.
  Chat darf Quellen ohne sichtbare Bestätigung nur einschränken. Neue Versionen,
  Gruppenänderungen, Caches und alte Chatkontexte dürfen keine Freigabe umgehen.
  Trenne Quellenbelege, eigene Ableitungen und Modellwissen; ein gültiger Locator
  allein ist keine Prüfung der Fundstelle oder ihrer inhaltlichen Stützung.
- RetrievalScope pinnt Dokumentversion und Analyselauf. Suche/Embeddings erhalten
  nur vorgefilterte, erlaubte Inhalte. Tutor-Citation-Prüfungen müssen die ursprünglichen
  Filter aus citation_constraints mitführen; der breite manuelle GET ist kein Ersatz.
- Tutor-Verlauf nur unter passenden Quellen-, Modul- und Modusgrenzen wiederverwenden.
  Prüfe Quellen erneut nach Werkzeuglatenz und vor/nach einem Modellaufruf. Provider-
  Fehler niemals mit Zugangsdaten oder ungefilterten Bodies speichern. Mathematik
  nur über erlaubte AST-Operationen; keine eval-/Python-Ausführung aus Modelltext.
- Halte spätere Provider-SDKs innerhalb ihrer Infrastrukturadapter. Keine SDK-Typen
  in Domäne oder öffentlichen API-Verträgen.
- Verändere bestehende Nutzerarbeit nicht beiläufig. Speichere keine Geheimnisse,
  privaten Studiendokumente oder personenbezogenen Protokolle im Repository.

## Qualität und Übergabe

Neue Abhängigkeiten begründen, kompatible Versionen festlegen und Lockfiles nutzen.
Führe die zum Verhalten passenden Tests aus; melde übersprungene und fehlgeschlagene
Checks getrennt. In apps/api gelten uv.lock, Ruff (app/tests/migrations/scripts) und pytest. Vollständige Tests
benötigen das optionale math-Extra und TEST_DATABASE_URL auf PostgreSQL und führen Migrationen in isolierten
Testschemas aus; nur Unit-Tests ersetzen diese Prüfung nicht. Befehle: docs/DEVELOPMENT.md.
Prüfe bei Dokumentationsänderungen Links und git diff --check.

Dokumentiere geändertes Verhalten, relevante Entscheidungen und konkrete Grenzen.
Wissenschaftliche Beispiele müssen Annahmen, Einheiten, Definitionsbereiche und
gegebenenfalls Näherungen nennen. Symbolische oder numerische Plausibilität ist
kein allgemeiner mathematischer Beweis.
