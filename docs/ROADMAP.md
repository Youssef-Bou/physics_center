# Entwicklungs-Roadmap

Die Reihenfolge ist abhängigkeitsbasiert; Zeitangaben wären ohne Team- und
Umfangsschätzung nicht belastbar. Jede Phase benötigt einen eigenen überprüfbaren
Abschluss. Phase 0 ist dieser Dokumentationsauftrag.

## Aktueller Implementierungsstand

Der explizite Auftrag zur Themen-/Aufgabenverknüpfung hat einen begrenzten
Backend-Schnitt aus Phase 1 und der dokumentbezogenen Analyse vorgezogen:
FastAPI, PostgreSQL-Migrationen, Originalversionen, Segmente/Aufgaben, katalogbasierte
Themenzuordnung und manuelle Prüfung/Korrektur sind vorhanden. Die Tests verwenden
kontrollierte PDFs und deterministische Adapter. Details: [KNOWLEDGE_LINKING](KNOWLEDGE_LINKING.md).

Die [Retrieval-Engine](RETRIEVAL.md) ergänzt inzwischen Modulzuordnungen, explizite
Versions-/Analyseauswahl, Volltextsuche und filtergebundene Citation-Prüfung mit
einem optionalen lokalen Embedding-Port. Damit ist keine der folgenden Gesamtphasen
pauschal abgeschlossen: vollständige Metadatenverwaltung, Next.js, visuelle
Quellenauswahl, OCR und große Vektorsuche fehlen weiterhin.
Ein erster [Tutor-Backendablauf](PHYSICS_TUTOR.md) mit Mock/konfigurierbarem Provider,
vier Modi, Citation-Prüfung, Unterhaltungen und optionaler Symbolik ist implementiert.
Die fachliche Abnahme eines realen Modells ist ausdrücklich noch offen; die getrennte
[Evaluationsrubrik](TUTOR_EVALUATION.md) definiert dafür die nächsten Schritte.
Als Nächstes sind das reale Physikkorpus zu annotieren,
Extraktionsqualität zu evaluieren und die vorhandene Prüfstrecke in den Study-Kern
einzubinden. Produktive Anmeldung und Betrieb bleiben separate Voraussetzungen.

## Phase 0 – Projektgrundlage

Ergebnis: Anforderungen, Architektur, Datenmodell, Erweiterungsgrenzen und
Arbeitsregeln. Akzeptanz: lokale Dokumentlinks sind gültig; Entscheidungen und
Annahmen erkennbar; Phase 1 ist ohne vorgezogene KI-Implementierung ausführbar.

## Phase 1 – Durchgängiger Study-Kern

1. Next.js-/FastAPI-Grundgerüst, kompatible gepinnte Runtimes, Lockfiles,
   PostgreSQL-Entwicklungsdienst, Konfigurationsvorlage ohne Secrets und CI anlegen.
2. Migrationen für Eigentümer, Projekte, Module, Themen und Quellenmodell erstellen.
   Wissenschaftliche Typen einschließlich Musterlösungen, Metadatenrollen,
   Dokument-/Publikationsjahr, Blattnummer, Themen, Kategorien und Gruppen erfassen.
3. Anwendungsfälle und API für Anlegen, Lesen und Metadatenänderungen implementieren;
   Löschumfang auf unreferenzierte Einzelobjekte begrenzen.
4. PDF-Upload, private Speicherung, Versionsstatus und manuelle Fundstellen umsetzen.
   PDF-Seitenzahl mit gewarteter Bibliothek ermitteln; keine Textextraktion/OCR.
5. Minimale UI für genau diesen Ablauf, nachvollziehbare Fehler und Integrationstests.

### Verbindliche Akzeptanzkriterien

- Ein neuer Checkout startet nach dokumentierter Installation mit eingefrorenen
  Abhängigkeiten, PostgreSQL-Migration und klaren Startbefehlen. Readiness prüft
  Datenbankzugriff; ein API-Healthcheck und ein echter Schreib-/Leseablauf funktionieren.
- Migrationen laufen auf leerer PostgreSQL-Datenbank durch. Ein erneuter Upgrade-Lauf
  ist wirkungslos; Daten und Dateien überstehen einen Neustart der Dienste.
- Ein Browser-End-to-End-Test legt Projekt „Physikstudium“, Modul „Mechanik“ und
  Thema „Drehimpuls“ an, lädt ein bekanntes mehrseitiges Test-PDF hoch und ordnet
  Quelle und Thema zu. Ein manueller Beleg auf eine bekannte Seite wird gespeichert
  und nach Neuladen mit Version und korrektem Seitenbereich angezeigt.
- Ein zweiter Upload mit geänderten Bytes erzeugt eine neue Version. Der alte
  Beleg löst weiterhin die erste Version und deren Hash auf. Ein identischer Upload
  erzeugt keine doppelte Version desselben Dokuments.
- Seiten 0, umgekehrte Bereiche und Seiten oberhalb der tatsächlichen Seitenzahl
  werden abgewiesen. Pending/failed-Versionen sind nicht zitierbar.
- Rollen, Semester, Jahresfelder und Blattnummer bleiben nach Speicherung erhalten;
  Aufgabenlabels gehören zur Fundstelle. Manuell geprüft bedeutet Kontrolle der
  konkreten Text-/Formelstelle am Original, nicht bloß einen gültigen Seitenbereich.
- PostgreSQL- und API-Tests verhindern projektfremde Beziehungen, doppelte
  Zuordnungen und Löschen referenzierter Versionen. Veraltete Metadatenrevisionen
  erzeugen einen Konflikt statt stillen Überschreibens.
- Ein Zugriff mit einem zweiten Testbenutzer kann weder fremde Metadaten noch
  Dateibytes lesen oder ändern; auch erratene UUIDs und verschachtelte URLs helfen nicht.
- Uploadtests prüfen Größenlimit, unzulässige Datei, Pfadmanipulation, Fehler zwischen
  Dateiablage und DB-Schritt sowie sichere Wiederholung/Bereinigung. Grenzen werden
  dokumentiert; Logs enthalten keine Dateiinhalte oder Zugangsdaten.
- Backendtests, PostgreSQL-Integrationstests, Frontend-Typprüfung und Produktionsbuild
  sowie der beschriebene Browsertest laufen in CI. Ausgeführte Testzahlen sind sichtbar;
  ein Lauf ohne Tests zählt nicht als Erfolg.
- Der lokale Entwicklungsbenutzer funktioniert ausschließlich im expliziten lokalen
  Modus; unsichere Konfiguration für öffentliche Bereitstellung wird abgewiesen.

Öffentliche Bereitstellung ist kein automatischer Abschluss dieser Phase. Sie braucht
vorher OIDC-/Sessionintegration, Betriebs- und Sicherungskonzept samt Restore-Test.
KI, Vektoren, OCR, automatische Bewertung und Research sind keine Abnahmekriterien.

## Phase 2a – Visuelle Quellensteuerung

Unterhaltungsbezogene Auswahl, Gruppen-/Kategorieaktionen, feste Versionsmengen,
Turn-Snapshots und Bestätigungszustände implementieren. Ein deterministischer
Testresolver ermöglicht den Auswahlvertrag ohne KI-Integration. Abschluss:
Einzel-/Gruppenaktionen, Teilzustände, konkurrierende Änderungen und vorbereitete
Erweiterungsbestätigungen bestehen die Fälle S01–S14 und C01–C04 des
[Testvertrags](SOURCE_MANAGEMENT_TESTS.md) auf Auswahl-/API-Ebene. Neue Versionen
und Gruppenmitglieder aktivieren sich nicht selbst. Die endgültige Chat-UI folgt
in Phase 3; ihr End-to-End-Nachweis ist hier noch nicht erbracht.

## Phase 2b – Dokumente verstehen und hybrid durchsuchen

Versionierte Text-/Formelextraktion, sichtbare Qualität, zunächst manuelle Aufgaben
und Themenzuordnung; bei Bedarf persistente Jobs und OCR. Volltext und semantische
Suche samt Fusion sind verbindlich. Beide erhalten denselben Quellenfilter vor
Kandidatenabruf und Ranking. Abschluss: R01–R04, M01–M02 sowie Fundstellenprüfungen
aus B01–B04 bestehen auf Extraktions-/Retrievalebene mit repräsentativen PDFs.
Extraktionsfehler sind sichtbar, Quellenlücken lockern keine Filter und Wiederholung
erzeugt keine Duplikate. Provider-/Antwortprüfungen dieser Fälle folgen in Phase 3.

## Phase 3 – Quellenbasierter Tutor

Providerport, erster Adapter, natürlichsprachlicher Quellenresolver und die
Bestätigungsoberfläche integrieren. Antworten unterscheiden quellenbelegte Aussagen,
Eigenableitungen und Modellwissen. Nur verifizierte, die Aussage stützende Fundstellen
dürfen als Belege erscheinen. Abschluss: alle Fälle der Gruppen S, C, R, B und M des Testvertrags,
insbesondere History-/Cachegrenzen, Abbruch bei Deaktivierung und UI-End-to-End-Test,
laufen auf ihren vorgesehenen Ebenen. Anbieterwechsel mit Testadaptern und Umgang
mit fehlender Evidenz sind nachgewiesen. Kuratierte Physikaufgaben und Negativfälle
bestehen vorher festgelegte Qualitätsgrenzen; diese werden vor Implementierung
anhand des Testsets festgelegt, nicht nachträglich an Ergebnisse angepasst.

Erst dann ist das gesamte Feature „Hybride wissenschaftliche Quellenverwaltung“
abgenommen. Ein bestandener Dokumentationscheck oder eine Checkboxoberfläche allein
belegt weder Suchqualität noch korrekte Quellenantworten.

## Phase 4 – Klausuren und Lernplanung

Bestätigbare Klausuranalyse, Aufgabenversuche und evidenzbasierte Fortschrittsdaten,
danach erklärbare Planung. Abschluss: jede Zuordnung ist zur Originalaufgabe
zurückverfolgbar; Nutzerkorrekturen werden berücksichtigt und gleiche Eingaben
erzeugen bei gleicher Regelversion denselben Plan.

## Phase 5 – Research

Literaturimport, versionierte Notizen und Herleitungen; danach LaTeX und isolierte
Analysen. Abschluss: ein Forschungsartefakt kann aus dokumentierten Eingaben und
Umgebung reproduziert werden; Notizen und Herleitungen behalten ihre Belege.
Vor Beginn werden reale Bachelorarbeitsabläufe erhoben, statt sie jetzt zu erfinden.
