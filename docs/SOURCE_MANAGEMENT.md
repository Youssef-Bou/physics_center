# Hybride wissenschaftliche Quellenverwaltung

Status: verbindlicher Featureentwurf, noch keine implementierte Funktion.
Ergänzt [Architektur](../ARCHITECTURE.md), [Datenmodell](DATA_MODEL.md) und
[Roadmap](ROADMAP.md). Konkrete Prüffälle stehen im
[Testvertrag](SOURCE_MANAGEMENT_TESTS.md).

## Ziel und gemeinsame Verantwortung

Visuelle Auswahl und natürliche Sprache steuern dieselbe serverseitige
Quellenmenge. Das gemeinsame Modul `sources` verwaltet Katalog, Versionen,
Auswahlregeln, Suche und Belegprüfung für Study und Research. Das Study-Modul
ergänzt Modul-/Themenzuordnungen; der KI-Tutor konsumiert die freigegebenen
Ergebnisse. Ein KI-Modell entscheidet weder über Zugriffsrechte noch über die
Erweiterung der Quellenmenge. Es gibt dafür keinen eigenen Microservice.

Wissenschaftliche Funktion ist über stabile Quellentypen erfasst: Skript,
Lehrbuch, Übungsblatt, Musterlösung, Altklausur, Publikation und weitere Typen.
Frei benannte Kategorien sowie manuelle Quellengruppen ergänzen diese Ordnung.
Ein Dokument gehört genau einem Projekt und in Study einem oder mehreren Modulen;
während der Erfassung darf eine Modulzuordnung noch fehlen. Research benötigt
keine Studienmodule. Quellen werden nicht projektübergreifend implizit freigegeben.

Metadaten umfassen Titel, geordnete Beteiligte mit Rolle (Autor, Professor/Dozent,
Herausgeber), Semester, Dokumentjahr, Publikationsjahr, Blattnummer, Themen und
Quellentyp. Eine Aufgabennummer bezeichnet eine konkrete Fundstelle, nicht
zwangsläufig ein ganzes Blatt. DOI und spätere BibTeX-Daten sind unabhängig von
Dateiformat und Modulstruktur; Details stehen im Datenmodell.

## Visuelle Steuerung

Eine Quellenansicht zeigt Typen/Kategorien, Gruppen und Einzeldokumente mit
Metadatenfilter, Versionsstand und Aktivierungszustand. Checkboxen erlauben die
Auswahl eines Dokuments oder aller aktuell passenden Dokumente einer Gruppe.
Gruppen zeigen „alle“, „teilweise“ oder „keine“ aus der tatsächlichen Menge an.
Überlappende Gruppen erzeugen keine doppelten Quellen: Gruppenaktionen fügen
konkrete Versions-IDs hinzu oder entfernen sie. „Kategorie deaktivieren“ entfernt
alle dazu aktuell aufgelösten Versionen, auch wenn sie außerdem einer anderen
Gruppe angehören. Es gibt keine widersprüchlichen versteckten Gruppenregeln.

Die aktive Auswahl gilt pro Unterhaltung. Neue Unterhaltungen beginnen ohne
aktive Quellen; ein übernommenes Preset benötigt eine sichtbare Auswahlaktion.
Eine bewusst betätigte Aktivierungscheckbox gilt selbst als sichtbare Bestätigung
der ausgewiesenen Quellen. Ein zusätzliches Dialogfenster ist dafür nicht nötig.
Bei Gruppen werden Umfang und Versionsstände vor Anwendung angezeigt und gebunden;
die serverseitig angewendete Menge darf keine unsichtbaren Neuzugänge enthalten.

Eine Gruppen-/Typ-/Kategorieauswahl wird **zum Aktionszeitpunkt** auf konkrete,
berechtigte `ready`-Dokumentversionen aufgelöst. Spätere Uploads, Gruppenzugänge
oder Metadatenänderungen aktivieren nichts automatisch. Neue Versionen erscheinen
als verfügbar, ersetzen aber niemals stillschweigend eine freigegebene Version.
Voreinstellung ist die zum Auswahlzeitpunkt neueste `ready`-Version pro Dokument;
ältere oder mehrere Versionen lassen sich ausdrücklich wählen.

Der Chat zeigt dauerhaft die aktive Menge und für jede Antwort die tatsächlich
verwendbare Menge dieses Turns. Nicht indizierte oder fehlerhaft extrahierte
Versionen werden als nicht durchsuchbar angezeigt, ohne ihre Auswahl zu erweitern.
Bedienung, Teilzustände und Bestätigungen müssen auch per Tastatur zugänglich sein.

## Deterministischer Auswahlvertrag

Für einen Turn bezeichnet:

- `S` die gespeicherte aktive Versionsmenge mit Auswahlrevision;
- `U` alle für den Benutzer in diesem Projekt aktuell berechtigten `ready`-Versionen;
- `A = S ∩ U` den zulässigen Ausgangsstand;
- `T` die aus einer eindeutigen Anweisung aufgelöste Zielmenge;
- `Δ = T \ A` die angefragte Erweiterung.

Ohne Quellenanweisung gilt `E = A` als effektive Turnmenge. Eine Einschränkung
berechnet `E = A ∩ T`. Entfernen bildet `T = A \ R`, Hinzufügen `T = A ∪ R`,
wobei `R` die aufgelöste Referenzmenge ist. „Nur …“ und „Vergleiche …“ beschränken
auf die genannten Quellen; „Berücksichtige …“ (mit oder ohne „auch“) ergänzt
die bestehende Menge.
Andere Formulierungen müssen eindeutig einem Modus zugeordnet oder geklärt werden.

Ist `Δ` nicht leer, wechselt der Turn vor jedem Inhaltsabruf in
`awaiting_confirmation`. Die Oberfläche zeigt Zielmenge, hinzukommende Dokumente
mit Version, wegfallende Quellen und Gültigkeit („nur diese Antwort“ oder
„ab jetzt“). Erst eine explizite Bestätigungsaktion erlaubt die Erweiterung.
Der Chattext selbst ist keine Bestätigung, auch nicht „aktiviere alles“.
Ablehnen oder Abbrechen startet keine Teilantwort und ändert keine Auswahl;
eine Antwort nur aus der verbleibenden Teilmenge braucht eine bewusste neue Aktion.

Standardmäßig gilt eine Chat-Einschränkung oder bestätigte Erweiterung nur für
diesen Turn. „Ab jetzt“ bzw. „für diese Unterhaltung“ erzeugt eine dauerhafte
Auswahländerung; auch dabei benötigen neue Quellen Bestätigung. Die Oberfläche
zeigt diese Reichweite vor Anwendung an. Ohne Erweiterung darf eine eindeutige
dauerhafte Einschränkung direkt als neue Auswahlrevision gespeichert werden.

Nach Bestätigung gilt für einen einmaligen Turn
`E = (A ∪ bestätigtes Δ) ∩ T`; dauerhaft wird `S = T` als neue Revision gespeichert.
In beiden Fällen werden Berechtigung, Status und Ausgangsrevision erneut geprüft.
Ist die Auswahl oder eine beteiligte Quelle inzwischen geändert, wird der Vorschlag
ungültig und aus dem aktuellen Stand neu angezeigt. Die konkrete freizugebende
Menge bleibt eingefroren; ein erneuter Selektor darf sie nicht heimlich vergrößern.

Der Server speichert den Turn mit seinen exakten Versions-IDs und der zugehörigen
Auswahlrevision. Jeder Suchaufruf braucht diesen Scope; ohne gültigen Scope wird
abgebrochen. Eine leere Menge bedeutet keine Quellen, niemals „alle Quellen“.

### Beispiele

| Anweisung | Verhalten |
| --- | --- |
| „Nur Skript A“; A aktiv | Für diesen Turn ausschließlich A; andere aktive Quellen bleiben für spätere Turns aktiv. |
| „Nur Skript A“; A inaktiv | Vorschlag zum einmaligen Wechsel auf A; ohne sichtbare Bestätigung kein Abruf aus A. |
| „Berücksichtige auch Übungsblatt 7“ | Eindeutiges Blatt im Projekt/Modul suchen; aktiv: aktuelle Menge beibehalten, inaktiv: Erweiterung vorschlagen. |
| „Vergleiche die Altklausuren 2022 bis 2024“ | Nach Typ und Dokumentjahr inklusiv auflösen, auf diese Menge einschränken; inaktive Treffer zusammen zur Bestätigung anzeigen. Fehlende Jahre offenlegen. |
| „Ab jetzt ohne Musterlösungen“ | Typ `worked_solution` aus der dauerhaften Menge entfernen; künftige Turns verwenden die neue Revision. |
| „Nur Skript A, aber auch ausschließlich Lehrbuch B“ | Widersprüchlicher Zielscope: klären; nicht stillschweigend eine Regel bevorzugen. |

Mehrere Treffer „Blatt 7“ in verschiedenen Modulen/Semestern werden als Auswahl
angeboten. Es wird nicht nach Ähnlichkeit ein beliebiges Dokument gewählt. Unbekannte
oder unberechtigte Referenzen führen zu einem neutralen Hinweis ohne Offenlegung
fremder Metadaten. Datumsbereiche nutzen strukturierte Jahresfelder; „2022–2024“
wird nicht aus Uploadzeitpunkten oder Dateinamen geraten.

Nennt eine Chat-Anweisung ein Dokument ohne Versionsangabe, bleiben dessen bereits
ausgewählte Versionen maßgeblich: „nur Skript A“ wählt A1, auch wenn inzwischen A2
hochgeladen wurde. Eine inzwischen unbrauchbare ausgewählte Version wird nicht
automatisch ersetzt. Bei bisher nicht ausgewählten Dokumenten wird die neueste
`ready`-Version als konkrete Erweiterung vorgeschlagen. Eine ausdrücklich angefragte
neuere Version erfordert dieselbe sichtbare Bestätigung wie jede andere Hinzunahme.

## Natürlichsprachliche Auflösung und API-Grenzen

Ein Resolver erzeugt einen validierbaren Entwurf aus Operation, Selektoren,
Gültigkeitsdauer und gegebenenfalls Klärungsbedarf. Er kann zunächst explizite Muster
verwenden und später einen austauschbaren Sprachmodelladapter nutzen. Dokumenttitel,
Gruppen oder Typen werden gegen den berechtigten Projektkatalog aufgelöst. Diese
Metadatensuche darf inaktive Dokumente zur Auswahl anzeigen, aber keine Textstellen
aus ihnen abrufen oder an einen Antwortanbieter senden. Katalogzugriff ist keine
Freigabe zur Inhaltsverarbeitung.

Der Resolver liefert Vorschläge, keine SQL-Ausdrücke und keine direkt ausführbaren
Suchfilter. Servervalidierung prüft erlaubte Operationen, IDs, Projekt, Revision,
Mehrdeutigkeiten und Mengen. Quellenanweisungen werden nur aus authentifizierten
Nutzereingaben und UI-Aktionen übernommen, nie aus PDF-Text oder Modellantworten.
Externe KI-Verarbeitung benötigt unabhängig davon eine eigene Versandfreigabe;
eine Quellenaktivierung erteilt diese nicht automatisch. Dies gilt auch für externe
Resolver, Embeddingdienste und Reranker; ohne Freigabe werden keine Dokumentdaten
an diese Dienste gesendet.

Geplante projektgebundene Verträge unter `/api/v1/projects/{project_id}`:

| Anwendungsfall | Vertrag |
| --- | --- |
| Katalog filtern | Dokumente mit Typ, Modul, Themen, Jahr, Semester, Kategorien und Gruppen paginiert lesen. |
| Visuelle Auswahl ändern | Conversation-Scope mit `expected_revision`, exakten Versions-IDs und sichtbarer Aktionsbestätigung aktualisieren. |
| Quellenanweisung auflösen | Turn + Nachricht gegen aktuelle Auswahl auflösen; `resolved`, `needs_clarification` oder `awaiting_confirmation` zurückgeben. |
| Erweiterung bestätigen | Benutzer-/Conversation-/Turn-gebundene Proposal-ID, Revision und Zustimmung/Abbruch atomar verarbeiten. |
| Antwort erzeugen | Nur mit freigegebenem Turn-Snapshot; Scope ist serverseitige Voraussetzung, kein frei formulierbarer Providerparameter. |

Bestätigungsvorschläge binden exakte Versions-IDs, Zielmodus, Auswahlrevision und
relevanten Katalogstand. Sie sind zeitlich begrenzt, einmalig nutzbar und mit
Idempotenzschlüssel gegen doppelte Anwendung geschützt. Abgelaufene, abgelehnte
oder überholte Vorschläge dürfen keine neue Auswahl erzeugen. Konflikte liefern 409
und eine aktuelle Ansicht statt stiller Zusammenführung.

Deaktivierung während laufender Generierung entwertet den offenen Turn: neue
Such-/Toolaufrufe werden blockiert, eine veraltete Antwort nicht als aktuell
ausgegeben. Bereits an einen Anbieter gesendete Daten lassen sich nicht zurückrufen;
die Oberfläche macht den Abbruch sichtbar. Jede erneute Ausführung prüft den Scope.
Historische Antworten behalten ihren ursprünglichen Scope als Herkunftsinformation.

## Suche: Filter vor Abruf und Ranking

Beide Suchwege erhalten ausschließlich den effektiven Turn-Scope:

1. Berechtigung, Projekt, aktive Versions-IDs, Verarbeitungsstatus und optionale
   Metadaten-/Locatorfilter bilden die zulässige Passage-Relation.
2. PostgreSQL-Volltextsuche (`tsvector`/GIN) und semantische Suche (pgvector) suchen
   und ranken innerhalb dieser Relation. Zum Start nutzt die Vektorsuche exakte
   Ähnlichkeitsberechnung über die vorgefilterte Menge. ANN kommt erst nach Messung
   und nur mit nachgewiesener Scope-Garantie hinzu.
3. Die Trefferlisten werden z. B. per Reciprocal Rank Fusion zusammengeführt,
   dedupliziert und begrenzt. Ein Reranker erhält nur diese bereits erlaubten Treffer.
4. Vor Kontextbau werden IDs, Scope und unveränderliche Versions-/Extraktionsstände
   erneut validiert. Der Anbieter erhält keine anderen Dokumentinhalte.

Globales Top-k mit anschließendem Quellenfilter ist unzulässig: Es verletzt die
vorgegebene Abrufgrenze und kann relevante erlaubte Stellen verdrängen. Volltext und
Vektorpfad müssen auch unabhängig funktionieren und dieselben Filter befolgen.
Ein temporärer Ausfall des Vektorpfads wird als eingeschränkte Suche gemeldet;
er gilt nicht als vollständig bestandene Abnahme der hybriden Suche.

Sprachabhängige Volltextkonfiguration, exakte Fachbegriffe, Gleichungs-/Aufgabenlabels
und normalisierte LaTeX-Suchformen ergänzen Embeddings. Formelzeichen werden nicht
einfach durch Stopwort-/Stemmingregeln entfernt. Semantische Ähnlichkeit ist weder
ein Nachweis gleicher Formeln noch ein wissenschaftlicher Beleg.

Caches sind an Benutzer/Projekt, Hash der effektiven Versionsmenge, Filter,
Extraktions-/Indexstand, Anfrage und Embeddingmodell gebunden; Berechtigung wird
bei Wiederverwendung erneut geprüft. Frühere Chatnachrichten, Zitate, Ergebnisse,
Zusammenfassungen und Toolkontexte aus inzwischen ausgeschlossenen Quellen dürfen
nicht als versteckter Retrievalkontext weitergegeben werden. Die Kontextaufbereitung
filtert sie anhand ihrer Provenienz; bei gemischter oder unklarer Herkunft entfällt
der ganze betroffene Kontext. Historische Anzeige bleibt davon getrennt.

## Mathematische PDFs und LaTeX

Versionierte Extraktion erhält Seitenlayout, Lesereihenfolge, Abschnitts-,
Gleichungs- und Aufgabenlabels sowie Abbildungsverweise. Textbasierte PDFs werden
zuerst direkt verarbeitet; OCR ist ein expliziter Fallback für Scans mit sichtbarer
Qualitätskennzeichnung. Rohtext, normalisierter Suchtext und LaTeX-Repräsentation
bleiben getrennt und auf das Original abbildbar. Zeilenumbrüche, Ligaturen,
Mehrspaltigkeit und über Seiten fortgesetzte Herleitungen sind eigene Testfälle.

Formeln bleiben als zusammenhängende Einheiten mit umgebenden Voraussetzungen
erhalten; schwierige Stellen werden zur Prüfung markiert. Parser-/OCR-Version,
Inputhash und Parameter werden gespeichert. Kein Parser garantiert allgemeine
Formelerkennung; Qualitätsgrenzen werden mit Physikfixtures vor Freigabe gemessen.
Unlesbare Formeln liefern keine scheinbar geprüften Belege.

LaTeX wird als begrenzter Inhalt dargestellt, nicht als ausführbares Programm.
Der Renderer beschränkt Makros, HTML und externe Ressourcen. Der Entwurf fordert
keine LaTeX-Kompilierung und keine freie Formel-/Codeausführung im Quellenmodul.

## Belegprüfung und Antwortvertrag

Eine gültige Seitenzahl allein ist keine verifizierte Fundstelle. Ein Quellenbeleg
benötigt eine tatsächlich im Original geprüfte Text-/Formelstelle, unveränderliche
Version mit Hash, Locator und dokumentierte Prüfung. `manually_checked` bedeutet
Prüfung am Original, nicht bloß Speichern eines Labels. Extrahierte Passagen sind
ohne solche Prüfung nur Kandidaten. Automatisierte Prüfverfahren dürfen später
nur mit dokumentierter Methode und separat abgenommenen Qualitätsgrenzen den
Prüfstatus setzen; eine Modellbehauptung reicht nicht.

Der Prüfgegenstand wird gespeichert: wörtlicher Text-/Formelausschnitt oder eine
präzise Region der Originalseite, jeweils mit Originalhash und Fingerprint. Nur
Seitenzahl und Kapitel ohne identifizierbare konkrete Stelle reichen nicht aus.
Eine Korrektur der Fundstelle erzeugt einen neuen Verweis und braucht neue Prüfung.

Kapitel, Gleichung und Aufgabennummer werden nur ausgegeben, wenn sie an der Stelle
festgestellt wurden. Die PDF-Seitenzahl wird stets angegeben, optionale gedruckte
Seitenlabels getrennt. Eine strukturierte Citation wird serverseitig aus gespeicherten
Daten aufgebaut; der Anbieter erzeugt höchstens eine zulässige Beleg-ID.

Jede inhaltliche Antwort gliedert ihre Aussagen bzw. Abschnitte in:

| Kennzeichnung | Erforderlicher Inhalt |
| --- | --- |
| `source_supported` – quellenbelegt | Aussage mit mindestens einer im Turn zugelassenen, verifizierten Fundstelle; die Stelle muss die konkrete Aussage stützen. |
| `derivation` – eigene mathematische Ableitung | Prüffähige Rechenschritte, Prämissen, Definitionsbereiche, Einheiten und Näherungen; Quellen für übernommene Prämissen separat angeben. Keine Behauptung, die Ableitung stehe so in einer Quelle. |
| `model_knowledge` – ergänzendes Modellwissen | Sichtbar ergänzendes Wissen ohne Quellenbeleg aus der aktiven Menge; keine erfundene Citation. |

Gemischte Abschnitte werden aufgeteilt. Eine Ableitung darf auf vorangegangene
Prämissen verweisen; das macht sie nicht zur zitierten Herleitung. Der Nutzer
kann „ausschließlich aus den Quellen“ verlangen; dann entfällt ergänzendes
Modellwissen. Die Auswahlanweisung „nur Skript A“ grenzt zunächst die Dokumentmenge
ein; die Herkunftskategorien bleiben sichtbar.

Widersprechen sich freigegebene Quellen, werden die verschiedenen Aussagen mit
ihren jeweiligen verifizierten Fundstellen gegenübergestellt. Unterschiedliche
Voraussetzungen, Konventionen oder Versionsstände werden benannt, soweit sie
belegt sind. Das System erzeugt keine scheinbare Einigkeit und wählt nicht allein
nach Suchrang oder Mehrheitszahl eine vermeintlich richtige Quelle aus. Nicht
auflösbare fachliche Konflikte bleiben ausdrücklich offen.

Vor Ausgabe prüft der Server Beleg-ID, Version, Scope, Locator, Prüfstatus und
Übereinstimmung mit der bereitgestellten Passage. Zusätzlich braucht jede
Quellenbehauptung einen Stützungsbefund (`supported`, `unsupported`, `uncertain`)
mit Methode. Anfänglich ist dies eine manuelle Prüfung; eine spätere automatisierte
Stützungsprüfung benötigt eigene fachliche Evaluation. Weder ein ID-Abgleich noch
die Selbsteinschätzung des erzeugenden Modells prüft inhaltliche Richtigkeit.
Ungeprüfte/unsichere Aussagen werden nicht als quellenbelegt veröffentlicht;
sie werden zurückgehalten oder ausdrücklich als unbelegte Ergänzung angezeigt,
sofern der Nutzer diesen Antwortmodus erlaubt. Im strikten Quellenmodus bleibt
stattdessen ein sichtbarer Lückenhinweis.

Inhaltliche Ausgaben werden bis zum Abschluss der Scope-, Beleg- und
Stützungsprüfung gepuffert. Ein Tokenstream darf diese Freigabe nicht umgehen;
währenddessen sind nur Statusmeldungen sichtbar. Ein späteres Streamingverfahren
muss jede veröffentlichte Einheit vorab prüfen und bei Scopeänderung abbrechen.

Fehlt ausreichende Evidenz, nennt die Antwort konkret, was in der freigegebenen
Menge nicht belegt werden konnte. „Keine Treffer“ beweist nicht, dass das Dokument
die Aussage nicht enthält. Keine automatische Erweiterung, kein stiller Zugriff
auf deaktivierte Quellen und kein Auffüllen von Belegfeldern durch Modellwissen.

## Umsetzung und Abnahme

Phase 1 legt strukturierte Metadaten und manuelle geprüfte Fundstellen an.
Phase 2a implementiert visuelle Auswahl und den deterministischen Auswahlkern mit
Testresolver ohne KI. Phase 2b ergänzt PDF-/Formelverarbeitung, Volltext und
semantische Suche innerhalb des Scopes. Phase 3 integriert natürlichsprachliche
Auflösung, Bestätigungsoberfläche und den klassifizierten Antwortvertrag.
Die Roadmap und der Testvertrag definieren die jeweilige Abnahme. Bis alle diese
Teile bestanden sind, gilt die hybride Quellenverwaltung nicht als implementiert.
