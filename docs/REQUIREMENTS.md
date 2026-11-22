# Anforderungen, Annahmen und Risiken

Implementierungsstand: Der lokale Themen-/Aufgaben-Prototyp ist inzwischen
vorhanden, siehe [KNOWLEDGE_LINKING](KNOWLEDGE_LINKING.md). Die ursprüngliche
Phaseneinteilung unten bleibt Zielrahmen; der explizite Analyseauftrag hat einen
begrenzten Backend-Schnitt vorgezogen, ohne den gesamten Study Workspace umzusetzen.

## Abgrenzung

Jetzt entstehen Architektur und Arbeitsgrundlage. Die erste Implementierungsphase
organisiert ein privates Study-Projekt mit Physikmodulen, Themen, Quellen und
manuell erfassten präzisen Fundstellen. Das ist die Grundlage für spätere
quellenbasierte Lernfunktionen. Research bleibt eine Erweiterungsrichtung.

Erforderlich sind strukturierte Beziehungen, nachvollziehbare Dokumentversionen,
prüfbare Projektgrenzen, verständliche Fehler und ein lokal reproduzierbarer Ablauf.
Nicht Teil der ersten Phase: Chat, automatische Extraktion, OCR, Lernplanung,
Klausurbewertung, Vektorsuche, kollaboratives Bearbeiten, LaTeX-Kompilierung und
Ausführung von Nutzer-Code.

## Verbindliches Feature: hybride Quellenverwaltung

Die [Featurespezifikation](SOURCE_MANAGEMENT.md) erweitert das Zielbild, ohne die
Implementierung aller Ausbaustufen in Phase 1 vorzuziehen. Metadaten und manuelle
Belege gehören zu Phase 1; Auswahlkern zu 2a, hybride Suche zu 2b, natürliche
Sprache und Antwortintegration zu Phase 3. Das Feature ist erst mit allen Teilen
vollständig. Die folgenden Anforderungen sind keine optionalen Ideen:

| Anforderung | Entwurfsentscheidung und Nachweis |
| --- | --- |
| Projekt-/Modulzuordnung und wissenschaftliche Funktion | Document/ModuleDocument und SourceType einschließlich Musterlösung; Research ohne Modulzwang. |
| Titel, Autor/Professor, Semester, Jahr, Aufgabe, Themen, Typ | Rollenbasierte Beteiligte, getrennte Jahresfelder, DocumentTopic und Aufgabenlabel am Locator. |
| Einzelquellen, Gruppen, Kategorien aktivieren/deaktivieren | SourceGroup und versionierte Conversation-Auswahl; Gruppen werden in konkrete Versionen aufgelöst. |
| Natürlichsprachliche Quellenanweisungen | Resolver mit strukturierten Operationen, Klärung bei Mehrdeutigkeit und serverseitiger Prüfung. |
| Einschränken frei, Erweitern nur sichtbar bestätigt | Getrennte Zielmenge und Delta; Turn-/Revisionsbindung, Ablehnung ohne automatische Ersatzantwort. |
| Herkunft jeder Antwort unterscheiden | Aussageblöcke source_supported, derivation und model_knowledge; Quellenmodus ohne ergänzendes Wissen möglich. |
| Nur tatsächlich geprüfte Fundstellen | Originalhash, PDF-Seite, geprüfter Text-/Formelbereich und separate inhaltliche Stützungsprüfung. |
| Unzureichende Quellen transparent machen | Lückenhinweis ohne erfundene Belege oder automatische Freigabe weiterer Dokumente. |
| Volltext und semantische Suche | PostgreSQL-Volltext plus pgvector; Scopefilter vor Kandidatenabruf und Ranking beider Pfade. |
| Mathematische PDFs und LaTeX | Versionierte Extraktion, Formelerhalt, sichtbare OCR-Grenzen und sichere Darstellung. |
| Publikationen, DOI und BibTeX erweiterbar | Gemeinsamer Quellenkern, normalisierte DOI und später versionierter bibliografischer Import. |
| Automatisierte Auswahl-/Konflikt-/Belegtests | Geplanter [Testvertrag](SOURCE_MANAGEMENT_TESTS.md) mit deterministischen Positiv- und Negativfällen. |

## Arbeitsannahmen

- Zunächst eine Person pro privater Installation; das Schema kennt dennoch einen
  Eigentümer. Teamrollen und projektübergreifende Freigaben werden nicht vorgebaut.
- Ein Projekt ist ein abgegrenzter Arbeitskontext. Ein Studienprojekt kann mehrere
  Module enthalten; Dokumente können mehreren Modulen desselben Projekts dienen.
- PDF ist das erste Dateiformat. Bibliografische Quellen können auch ohne Datei
  erfasst werden; präzise PDF-Fundstellen benötigen eine gespeicherte Version.
- Deutsch ist zunächst die Dokumentationssprache; Titel und Inhalte dürfen andere
  Sprachen enthalten. Zeitpunkte werden in UTC gespeichert.
- Kein KI-Anbieter, Hostinganbieter oder Authentifizierungsanbieter ist ausgewählt.
  Bezahlte Konten und Geheimnisse sind für die erste lokale Phase nicht nötig.

Diese Annahmen sind Entscheidungen für den ersten Schnitt, keine bestätigten
Nutzerpräferenzen. Vor Mehrbenutzerbetrieb, externen KI-Aufrufen oder Research
müssen Datenschutz, Betriebsmodell und neue Anforderungen erneut geprüft werden.

## Risiken und Gegenmaßnahmen

| Risiko | Umgang und Entscheidungspunkt |
| --- | --- |
| PDF-Seite und gedruckte Seitenzahl unterscheiden sich | Physische Seite getrennt vom Seitenlabel speichern; gegen gespeicherte Version validieren. |
| Extraktion verliert Formeln und Lesereihenfolge | Original bleibt maßgeblich; später OCR/Parser mit Version, Qualitätshinweis und manueller Kontrolle. |
| KI erzeugt plausible falsche Herleitungen | Belege, explizite Annahmen, Unsicherheiten und später kuratierte Evaluation; keine automatische wissenschaftliche Freigabe. |
| Dokumente enthalten personenbezogene oder urheberrechtlich geschützte Inhalte | Privat speichern, kein externer Versand ohne explizite Freigabe, Lösch- und Lizenzkonzept vor Produktbetrieb. |
| Dateien und DB laufen auseinander | Statusmodell, idempotente Wiederholung, Bereinigung und Restore-Test. |
| Zu früher Research-Ausbau verlangsamt Study | Gemeinsamer Projekt-/Quellenkern; neue Research-Tabellen erst bei konkretem Anwendungsfall. |
| Speicher- und Rechenlast unbekannt | Konfigurierbare Limits; später repräsentative PDF- und OCR-Benchmarks vor Worker-/Vektorauswahl. |
| Rechenprüfung wird mit Beweis verwechselt | Definitionsbereiche, Einheiten und Näherungen dokumentieren; menschliche Prüfung bleibt sichtbar. |
| Chat/Cache führt deaktivierte Quellen wieder ein | Scopegebundene Caches und provenienzbasierte Kontextbereinigung; Race-/Folgeturntests. |
| Mehrdeutige Chat-Anweisung erweitert die Auswahl | Keine automatische Auflösung; sichtbare Auswahl und revisionsgebundene Bestätigung. |
| Gültige Quellenadresse wird als inhaltlicher Beleg ausgegeben | Fundstellen- und Stützungsprüfung trennen; unklare Aussagen zurückhalten oder offen als unbelegt kennzeichnen. |
| Manuelle Prüfungen begrenzen Tutor-Geschwindigkeit | Geprüftes Korpus zuerst; Automatisierung erst nach fachlicher Evaluation, keine stillschweigende Senkung des Prüfstandards. |

Offen für Phase 1: unterstützte PDF-Grenzen und Metadateneditor-Details werden
beim vertikalen Prototyp festgelegt. Vor öffentlichem Betrieb sind Authentifizierung,
Hostingregion, Sicherung und Aufbewahrung verpflichtende Entscheidungen.
