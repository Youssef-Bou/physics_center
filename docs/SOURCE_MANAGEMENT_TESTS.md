# Testvertrag für die hybride Quellenverwaltung

Status: geplante automatisierte Tests und Abnahmekriterien, noch nicht implementiert
oder ausgeführt. Fachliche Regeln stehen in [SOURCE_MANAGEMENT](SOURCE_MANAGEMENT.md),
Persistenzregeln in [DATA_MODEL](DATA_MODEL.md). Die Fälle werden mit den zugehörigen
Roadmap-Phasen eingeführt, nicht durch einen Null-Test-Lauf als erledigt markiert.

## Deterministische Testbasis

Ein lokales, frei nutzbares Testkorpus enthält synthetische PDFs mit festgelegten
Bytes, Hashes, Seitenzahlen und bekannten Text-/Formelstellen. Keine privaten Dokumente
oder kostenpflichtigen Provider sind Voraussetzung dieser Tests.

| Kürzel | Testdaten und Zustand |
| --- | --- |
| P / M | Projekt P mit Modul Mechanik M, Eigentümer U; zweites Projekt Q und Nutzer V. |
| A1 | Skript A, Version 1, ready, 20 physische Seiten; in der Unterhaltung aktiv. |
| A2 | Neu hochgeladene Version von Skript A mit anderen Bytes; noch nicht aktiviert. |
| B1 | Skript B, ready; nicht aktiv. Ein zweites gleichnamiges Skript erzeugt Mehrdeutigkeit. |
| U7 | Übungsblatt 7, ready, mit Aufgaben 1 und 2; aktiv. Musterlösung L7 ist separat und inaktiv. |
| K22 / K23 / K24 | Altklausuren mit Dokumentjahren 2022, 2023, 2024; nur K22 aktiv. |
| X | Quelle aus Q bzw. von V; unabhängig von Texttreffern für P unzulässig. |
| F / W | Fehlgeschlagene bzw. noch verarbeitete Version; nicht abrufbar oder zitierbar. |
| E1 / E2 | Verifizierte Fundstelle auf A1, Seite 5, Gleichung (2.3), sowie unbestätigte OCR-Stelle. |

Vor jedem Fall wird derselbe Ausgangsstand hergestellt: aktive Versionsmenge
`S = {A1, U7, K22}`, unveränderte Berechtigungen und festes Selektionsrevisionstoken.
`A` ist der zum Turnbeginn daraus zulässige ready-Stand. Gruppen und Kategorien
werden bei jeder bewussten Auswahl in konkrete Versions-IDs aufgelöst.
Ein Fake-Provider zeichnet auf, welcher Kontext ihn erreicht; ein Retrieval-Spy
zeichnet Filter, Kandidaten und Ergebnisse getrennt auf.

## Quellenauswahl und Bestätigung

| ID / Ebene | Aktion | Erwartung |
| --- | --- | --- |
| S01 / Unit | „nur Skript A“ | Turn nutzt ausschließlich A1; S bleibt für den nächsten Turn unverändert. |
| S02 / Unit | „berücksichtige Übungsblatt 7“ | Bereits aktives U7 wird verwendet; keine neue Version oder Musterlösung wird mitaktiviert. |
| S03 / API + UI | „vergleiche die Altklausuren 2022 bis 2024“ | Sichtbarer Vorschlag für K23 und K24; vor Bestätigung weder Retrieval noch Providerkontext dieser Quellen. |
| S04 / API + UI | Vorschlag bestätigen | Exakt angezeigte Versions-IDs werden im angegebenen Umfang freigegeben; die Revision und der endgültige Turn-Snapshot sind nachvollziehbar. |
| S05 / API | Vorschlag ablehnen oder auslaufen lassen | Keine Erweiterung; die ursprüngliche Vergleichsfrage wird nicht stillschweigend als vollständig beantwortet. |
| S06 / API | Nur „ja“ ohne eindeutig gebundenen Vorschlag, Replay oder fremder Nutzer | Keine Erweiterung; keine wiederholte oder fremde Bestätigung wird akzeptiert. |
| S07 / Unit + UI | Mehrdeutiger Titel, widersprüchliche Anweisung oder unbekannte Jahreszahl | Klärung statt geratenem Dokument; bis dahin keine Erweiterung und keine fremden Metadaten im Vorschlag. |
| S08 / UI | B1 explizit einschalten, danach ausschalten | Bewusste sichtbare Auswahl aktiviert B1 für die angegebene Unterhaltung; Ausschalten entfernt es wieder. |
| S09 / Unit + UI | Kategorie/Gruppe einschalten, überlappende Gruppe auswählen, Einzelquelle ausschalten | Einmalige Mengenauflösung ohne Duplikate; Einzeldeaktivierung gilt trotz Gruppenmitgliedschaft, UI zeigt Teilauswahl. |
| S10 / API | Nach Gruppenauswahl neue Datei, Gruppenmitgliedschaft oder A2 hinzufügen | Keine automatische Aktivierung; A1 bleibt die ausgewählte Version. Erneute bewusste Auswahl zeigt die Änderung. |
| S11 / Unit + UI | „ab jetzt nur Skript A“ | Explizite dauerhafte Einschränkung setzt S auf A1; spätere Turns verwenden diese Revision. |
| S12 / Unit | Leere Auswahl oder auf keine vorhandene Quelle auflösbarer Selektor | Keine globale Ersatzsuche; klarer Hinweis auf fehlende Quellen bzw. Klärungsbedarf. Sind passende Quellen vorhanden, aber inaktiv, folgt ein Bestätigungsvorschlag statt Abruf. |
| S13 / Unit + UI | Kategorie deaktivieren, deren Quelle auch in einer ausgewählten Gruppe liegt | Quelle wird unabhängig vom anderen Gruppenbezug entfernt; Gruppenstatus wird als teilweise/keine angezeigt. |
| S14 / Unit + UI | A2 ist verfügbar: erst „nur Skript A“, dann „neueste Version von Skript A“ | Der erste Turn behält A1; der Versionswechsel auf A2 wartet auf sichtbare Bestätigung. |

Property-basierte Mengenprüfungen ergänzen Beispiele: ohne bestätigte Erweiterung
gilt für beliebige Anfragen stets `effective_sources ⊆ A`; Duplikate ändern die Menge
nicht; jede Quelle gehört zum Projekt und zu einer konkret gespeicherten Version.
Die konkreten Request- und Bestätigungsformate werden gegen denselben Vertrag geprüft.

## Revisionen, Berechtigungen und Kontextgrenzen

| ID / Ebene | Konflikt | Erwartung |
| --- | --- | --- |
| C01 / PostgreSQL + API | Zwei Tabs schreiben dieselbe Auswahlrevision | Ein Update gewinnt; das andere erhält einen Konflikt und muss den aktuellen Stand anzeigen. |
| C02 / API | Auswahl ändert sich bei offenem Erweiterungsvorschlag | Alter Vorschlag ist nicht anwendbar; aktualisierter Vorschlag erfordert neue Bestätigung. |
| C03 / Integration | Quelle wird während Retrieval/Generierung deaktiviert oder Zugriff entzogen | Lauf wird vor weiterer Verwendung gestoppt/neu geplant; keine neue Antwort wird aus dem veralteten Kontext freigegeben. |
| C04 / PostgreSQL + API | X per erratener UUID an Auswahl, Gruppe, Version oder Referenz hängen | Datenbank-/Servicegrenzen verhindern Zugriff und Zuordnung; kein fremder Titel wird offengelegt. |
| C05 / Integration | Antwortcache, frühere Chatantwort oder Zusammenfassung enthält inzwischen deaktiviertes B1 | Inhalt gelangt nicht über den Folgekontext zurück zum Provider; Cache ist an Auswahl-/Versionsstand gebunden. |
| C06 / Provider-Vertrag | PDF-Text fordert Aktivierung fremder Quellen oder Ignorieren der Auswahl | Keine Zustandsänderung, Bestätigung oder Berechtigung aus Dokumenttext. |
| C07 / Provider-Vertrag | A1 ist aktiv, aber externe Versandfreigabe fehlt | Kein externer Resolver-, Embedding-, Reranker- oder Antwortaufruf erhält Dokumentdaten; Quellenaktivierung ersetzt keine Versandfreigabe. |
| C08 / Integration + UI | Provider streamt vor abgeschlossener Prüfung oder während Scopeänderung | Inhalt bleibt bis zur Scope-/Beleg-/Stützungsprüfung gepuffert; veraltete oder ungeprüfte Aussagen gelangen nicht in die sichtbare Antwort. |

Race-Tests verwenden kontrollierte Barrieren zwischen Auswahlprüfung, Retrieval,
Provideraufruf und Antwortfreigabe. Sie dürfen nicht von zufälligen Wartezeiten abhängen.
Bereits an einen Provider gesendeter Kontext kann nicht zurückgerufen werden;
Deaktivierung verhindert weitere Nutzung und Veröffentlichung des laufenden Ergebnisses.

## Retrieval, Belege und mathematische Inhalte

| ID / Ebene | Prüfgegenstand | Erwartung |
| --- | --- | --- |
| R01 / PostgreSQL + Retrieval | B1 und X haben bessere Text-/Vektortreffer als A1 | Volltext- und semantische Kandidatenabfragen sind vor Ranking auf erlaubte Versions-IDs gefiltert; kein globales top-k mit anschließendem Aussortieren. |
| R02 / Retrieval | Enge Auswahl mit wenigen Treffern | Beide Suchpfade beachten dieselbe Menge; niedrige Trefferzahl lockert keinen Filter und verschweigt keine Quellenlücke. |
| R03 / Retrieval | Exaktes Aufgabenlabel, Formelzeichen oder Synonym suchen | Klassischer Suchpfad findet bekannte Labels, semantischer Pfad bekannte Paraphrasen; Fusion erzeugt keine fremden Versionen. |
| R04 / Integration | Extraktion/Embedding fehlt oder hat falsche Version/Dimension | Betroffener Suchpfad meldet Einschränkung; keine alten Segmente einer anderen Dokumentversion. |
| B01 / API + Provider-Vertrag | Erfundene Referenz-ID, falscher Hash, Seite 0 oder >20, fremde Version | Beleg wird abgewiesen; Aussage wird nicht als quellenbelegt veröffentlicht. |
| B02 / API + fachliche Fixture | Echte Seite enthält eine andere Aussage als behauptet | Gültiger Seitenbereich genügt nicht als inhaltlicher Nachweis; keine Freigabe als quellenbelegte Aussage. |
| B03 / Integration + UI | E1 stützt die Behauptung; PDF-Seite 5 trägt gedrucktes Label 3 | Anzeige nennt A1, physische Seite und getrenntes Label sowie verifiziertes Kapitel/Gleichung/Aufgabe, soweit vorhanden. |
| B04 / Integration | E2 aus fehlerhafter OCR, falsche Aufgabe oder nicht geprüfter Formelanker | Als unbestätigt gekennzeichnet; keine automatische Aufwertung durch bloße Modellbehauptung. |
| B05 / Provider-Vertrag + UI | Antwort mischt Zitat, mathematische Ableitung und ergänzendes Wissen | Aussageblöcke sind source_supported, derivation oder model_knowledge zugeordnet; Ableitungen nennen Voraussetzungen und Modellwissen bekommt keinen erfundenen Beleg. |
| B06 / Provider-Vertrag + UI | Keine stützende Fundstelle oder Quellen widersprechen sich | Lücke bzw. Widerspruch mit betroffenen Belegen sichtbar; keine scheinbare Einigkeit oder erfundene Literaturangabe. |
| B07 / Provider-Vertrag + UI | „Ausschließlich aus den Quellen“, aber Provider liefert Modellwissen oder unbelegte Aussage | Kein Umdeklarieren zur erlaubten Ergänzung; sichtbarer Lückenhinweis und keine Veröffentlichung der unbelegten Aussage. |
| B08 / API + PostgreSQL | Prüfstatus setzen, aber nur gültige Seite ohne Ausschnitt oder präzise Region gespeichert | Keine positive Verifikation; der konkrete Prüfgegenstand ist Pflicht, nicht nur ein unbegründeter Hash. |
| M01 / Extraktion | Mehrspaltiger Text, Brüche, Indizes, Integrale, Matrizen, griechische Zeichen | Reihenfolge und Formelinhalt stimmen mit geprüfter Fixture überein oder sind ausdrücklich als unsicher markiert. |
| M02 / Extraktion + UI | Fehlerhafter Scan und LaTeX mit nicht unterstützten Makros | Kein Verlust wird als sichere Extraktion ausgegeben; Original bleibt zugänglich, Formeln werden ohne Codeausführung sicher dargestellt. |

Belegtests trennen technische Auflösbarkeit, tatsächlich geprüfte Fundstelle und
inhaltliche Stützung. Fachlich bekannte positive und negative Fixtures sind nötig;
die Selbstbewertung eines Sprachmodells ist kein Bestehenskriterium.

## Abnahme und Nachweis

- Auswahlregeln laufen als Unit-/Property-Tests ohne KI-Anbieter. Persistenz- und
  Berechtigungsfälle laufen gegen PostgreSQL; SQLite ersetzt diese Fälle nicht.
- Retrievaltests verwenden PostgreSQL-Volltext und den realen semantischen Suchadapter
  mit festgelegten Testvektoren; Kandidatenfilter werden zusätzlich per Spy geprüft.
- Derselbe Provider-Vertrag wird mit mindestens zwei Fake-Adaptern geprüft. Ein realer
  Anbieter braucht eine getrennte fachliche Evaluation, nicht zwingend Zugang in CI.
- Ein UI-End-to-End-Test umfasst Kategorieauswahl, Einzelausschluss, Chat-Einschränkung,
  sichtbare Erweiterungsbestätigung und das Öffnen einer verifizierten Fundstelle.
- Jede implementierte Phase weist Testanzahl, ausgeführte Zielversion und Fehler/Skips
  getrennt aus. Alle zugeordneten deterministischen Fälle müssen bestehen; offene
  Qualitätsprobleme mit Mathematik oder Extraktion bleiben als Einschränkung sichtbar.
