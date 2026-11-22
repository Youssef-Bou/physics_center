# Fachliche Evaluation des Physiktutors

Status: reproduzierbarer **Evaluationsplan mit selbst formulierten Referenzaufgaben**,
kein bereits gemessenes Qualitätsresultat eines realen Modells. Der Standard-Mock
prüft Ablaufverträge und löst diese Aufgaben nicht. Erfolgreiche API-, Quellen- oder
SymPy-Tests dürfen nicht als fachliche Tutor-Evaluation ausgegeben werden.
Implementierungsgrenzen: [PHYSICS_TUTOR](PHYSICS_TUTOR.md).

## Versuchsaufbau und wissenschaftliche Verantwortung

Die Aufgaben unten sind ausdrücklich neu formulierte Testfälle und keine Auszüge
vermeintlich hochgeladener Lehrbücher oder Klausuren. Die angegebenen Standard-
Referenzrechnungen dienen zur unabhängigen Prüfung. Vor Freigabe eines Benchmarks
müssen Fachprüfer sie kontrollieren und mit einem versionierten, rechtlich verwendbaren
Quellenkorpus verbinden. Es werden hier keine Seitenzahlen oder Literaturbelege erfunden.

Für jeden Evaluationsfall festhalten:

- Aufgabe, Modus, Tiefe, Eingaben, Einheiten, erlaubte Modellannahmen und erwartete
  Teilresultate; gegebenenfalls gewünschter Hinweisgrad statt vollständiger Lösung.
- Tatsächliche Dokument-/Versionshashes und manuell geprüfte Fundstellen, Scope-ID,
  Revision, Filter und tatsächlich gepackten Quellenkontext. Fehlende Annotationen
  bleiben fehlend; kein automatisches Auffüllen von Quellenlabels.
- Promptversion, Provider-/Modellkennung, Generationseinstellungen, Werkzeugversionen,
  Laufzeit, verfügbare Usage-Angaben und Kontextbudgetwarnungen.
- Getrennte Bewertung der Retrieval-Abdeckung, der generierten Antwort und der
  Werkzeugresultate. Eine korrekte Rechnung mit einer unpassenden Quelle ist kein
  korrekter Quellenbeleg.
- Fachurteile mindestens zweier unabhängig bewertender Menschen und gegebenenfalls
  begründete gemeinsame Auflösung von Uneinigkeit. Ein Modell als zusätzlicher
  Gutachter wird als Modellurteil markiert und ersetzt die menschliche Referenz nicht.

Prompts werden anhand eines Entwicklungssatzes verbessert. Ein davon getrennter,
versionierter Testsatz mit weiteren Aufgaben und PDF-Layouts dient der Abnahme.
Die Grenze zwischen Entwicklung und Test darf nicht durch nachträgliches Auswählen
passender Antworten verwischt werden. Identische Modellparameter garantieren bei
externen Diensten keine identischen Antworten; Wiederholungen und Streuung dokumentieren.

## Bewertungsraster

Die ausführbare Evaluation verwendet separat **0 bis 4 Punkte** je Dimension
oder `nicht beurteilbar` mit Grund. Damit ersetzt diese Version das frühere
0-bis-3-Planungsraster. Die Werte sind ordinale Urteile, keine kalibrierten
Wahrscheinlichkeiten. Ergebnisse unterschiedlicher Skalen dürfen nicht unvermerkt
verglichen werden. Keine Gesamtsumme darf kritische Fehler verdecken.

| Dimension | 0 | 1 | 2 | 3 | 4 |
| --- | --- | --- | --- | --- | --- |
| Mathematische Korrektheit | Zentrales Ergebnis falsch oder undefiniert. | Wesentlicher Rechen-/Definitionsfehler. | Teilresultate korrekt, relevante Lücken. | Im Wesentlichen korrekt, kleinere Einschränkung. | Ergebnis und Operationen im angegebenen Bereich korrekt geprüft. |
| Vollständigkeit der Herleitung | Nur Behauptung oder Endformel. | Ansatz ohne wesentliche Begründung. | Mehrere nötige Schritte, aber entscheidende Lücke. | Fast alle erforderlichen Schritte begründet. | Alle verpflichtenden Zwischenschritte fachlich geprüft; keine internen Modellgedanken nötig. |
| Voraussetzungen und Gültigkeit | Entscheidende Voraussetzungen falsch. | Wichtige Grenze übersehen. | Hauptannahmen teilweise zutreffend. | Relevante Voraussetzungen weitgehend konsistent. | Annahmen, Definitionsbereiche, Randbedingungen, Einheiten und Näherungen explizit und konsistent. |
| Physikalische Interpretation | Falsche Größenbedeutung oder Widerspruch zur Physik. | Formeln ohne tragfähige Erklärung. | Plausible Teilinterpretation. | Stimmige Interpretation mit passender Kontrolle. | Physikalische Bedeutung, relevante Grenzfälle und Modellgrenzen sorgfältig erklärt. |
| Quellen und Citations | Erfundenes Zitat oder inaktive Quelle. | Adresse auflösbar, Aussage nicht gestützt. | Einige Aussagen tatsächlich belegt. | Quellenbezüge überwiegend passend. | Jede Quellenbehauptung tatsächlich gestützt; Ableitungen und Zusatzwissen klar getrennt. |
| Unsicherheit und Grenzen | Unbegründete Gewissheit oder erfundene Werkzeugprüfung. | Wesentliche Unsicherheit verschwiegen. | Grenzen nur pauschal erwähnt. | Wesentliche Lücken konkret benannt. | Evidenz-, Rechen- und Modellgrenzen genau benannt; passende Klärung statt Erfindung. |

Die zusätzliche adaptive Bewertung **Erklärungsökonomie** bleibt getrennt von den
sechs Kerndimensionen: 0 bedeutet eine unbrauchbare oder ablenkende Darstellung,
1 starke Redundanz bzw. unzureichende Orientierung, 2 mehrere vermeidbare Umwege,
3 überwiegend zweckmäßige Erklärung und 4 alle notwendigen Schritte ohne unnötige
Wiederholung. Weder Länge noch Quellenzahl bestimmen diesen Wert automatisch.

Für eine hohe Vollständigkeitswertung (3 oder 4) muss ein importierter Review jeden
verpflichtenden Schritt explizit geprüft haben. Eine richtige Endformel allein
reicht nicht. Ungeprüfte Referenzkandidaten bleiben vom Goldstandard ausgeschlossen;
Modellurteile werden separat als `model_judgment` geführt.

Kritische Fehler werden zusätzlich binär erfasst: erfundene Fundstelle, Verwendung
nicht freigegebener Quellen, falscher Verifikationsstatus, schwerer Definitions-
oder Einheitenfehler sowie unbegründete fachliche Voraussetzung. Ein solcher Fall
kann nicht durch gute Stilbewertungen bestanden werden. Nicht beurteilbare
Quellenstützung zählt nicht als bestandene Quellenbewertung.

## Referenzaufgabe 1: harmonischer Oszillator mit Anfangswerten

**Frage:** Eine Masse `m > 0` bewegt sich eindimensional unter `F = -k x`, mit
`k > 0`, `x(0) = x0` und `dx/dt(0) = v0`. Leite `x(t)` her und prüfe Anfangswerte,
Einheiten und Energieerhaltung. Welche Modellannahmen begrenzen das Ergebnis?

**Bereich und Annahmen:** Reelles `t`, konstantes `m` und `k`, Inertialsystem,
keine Reibung oder Anregung, lineares Hooke-Modell im tatsächlich zulässigen
Auslenkungsbereich. SI: `m` in kg, `k` in N/m, `x0` in m, `v0` in m/s.

**Referenzresultate:**

```text
m x'' + k x = 0
omega = sqrt(k/m)                         [omega] = 1/s
x(t) = x0 cos(omega t) + (v0/omega) sin(omega t)
E = (m/2) x'(t)^2 + (k/2) x(t)^2
  = (m/2) v0^2 + (k/2) x0^2               [E] = J
```

Zu prüfen: zwei unabhängige Integrationskonstanten, tatsächliches Einsetzen der
Anfangswerte und `dE/dt = x'(m x'' + kx) = 0`. Ein kurzer numerischer Kontrollfall:
`m=2 kg`, `k=8 N/m`, `x0=0,1 m`, `v0=0,2 m/s` ergibt `omega=2/s` und `E=0,08 J`.
Das ist ein Kontrollpunkt, kein Beweis für beliebige Parameter.

**Typische Negativfälle:** `omega=k/m` statt Quadratwurzel, fehlender Faktor
`1/omega` vor `v0`, unklare Anfangsphase oder Energieerhaltung trotz eingeführter
Reibung. Im Grenzfall `k→0+` bei festem endlichem `t` muss die Lösung gegen
`x0+v0 t` gehen; die Formel mit `v0/omega` darf nicht unkommentiert bei `omega=0`
eingesetzt werden.

**Modusvarianten:** `SOURCE_MODE` nur bei passenden Originalstellen; ansonsten
Lückenmeldung. `DEEP_PHYSICS_MODE` mit Herleitung und Kontrollen.
`SOCRATIC_MODE` soll zunächst nach Bewegungsgleichung oder Anfangswerten fragen,
sofern keine vollständige Lösung ausdrücklich verlangt ist.

## Referenzaufgabe 2: Drehimpuls bei einer Zentralkraft

**Frage:** Für ein Teilchen mit konstanter Masse sei
`F(r,t)=f(|r|,t) r/|r|` für `|r|>0`. Begründe die Drehimpulserhaltung. Folgt daraus
auch Energieerhaltung? Welche zusätzliche Annahme benötigt eine effektive radiale
Potentialbeschreibung?

**Bereich und Annahmen:** Klassische Mechanik in einem Inertialsystem, Ortsvektor
zum festen Kraftzentrum, `m>0`. Die Singularität `r=0` wird ausgeschlossen. Nicht
alle Zentralkräfte sind zeitunabhängig oder erlauben eine konservierte Energie.

**Referenzresultate:**

```text
L = r × (m r_dot)                         [L] = kg m^2/s
dL/dt = r_dot × (m r_dot) + r × F = 0
```

Bei `L != 0` liegt die Bahn in einer festen Ebene senkrecht zu `L`. Bei `L=0`
ist diese Normalenrichtung nicht definiert; eine radiale Bewegung widerspricht
der Erhaltung dennoch nicht. Konstantes `L` allein beweist keine Energieerhaltung.

Erst für ein zeitunabhängiges konservatives Potential `U(r)` mit
`F=-U'(r) r/|r|` gilt:

```text
E = (m/2) r_dot^2 + U_eff(r)
U_eff(r) = U(r) + L^2/(2 m r^2)
```

Hier ist `r=|r|` und `r_dot` die radiale Geschwindigkeit, nicht der Betrag der
vollen Geschwindigkeitskomponente. Optionaler Kontrollfall: Für
`U=-mu*m/r` mit `mu>0` in m³/s² und `L!=0` ist eine Kreisbahnstationarität bei
`r0=L²/(mu*m²)` möglich; dann gilt `E=-mu*m/(2*r0)`.

**Typische Negativfälle:** „Zentralkraft ⇒ Energieerhaltung“ trotz explizitem `t`,
Verwechslung von Drehimpuls und Drehmoment, Ableitung einer Voraussetzung allein
wegen ähnlicher Begriffe sowie eine angebliche eindeutige Bahnebene bei `L=0`.
Eine Quellenpassage über einen zeitunabhängigen Spezialfall darf nicht als Beleg
für die allgemeinere zeitabhängige Behauptung verwendet werden.

## Referenzaufgabe 3: freies gaußförmiges Wellenpaket

**Frage:** Ein eindimensionales freies Teilchen mit `m>0` habe auf der ganzen
reellen Achse den normierten Anfangszustand

```text
psi(x,0) = (2*pi*sigma0^2)^(-1/4)
           * exp(-(x-x0)^2/(4*sigma0^2) + i*p0*(x-x0)/hbar)
```

mit reellem `x0,p0`, `sigma0>0` und `hbar>0`. Bestimme den Schwerpunkt, die
Ortsvarianz und die Impulsunschärfe. Bleibt `Delta x * Delta p` für alle Zeiten
bei `hbar/2`? Erläutere Voraussetzungen und Grenzfälle.

**Bereich und Einheiten:** Nichtrelativistische Schrödingergleichung ohne äußeres
Potential, unbeschränkter Raum, quadratintegrabler Zustand; `x,sigma0` in m,
`p0` in kg m/s, `hbar` in J s. `sigma0` ist die Standardabweichung der
**Wahrscheinlichkeitsdichte**, nicht ein beliebiger Breitenparameter des Amplitudenexponenten.

**Referenzresultate:** Mit `tau=hbar*t/(2*m*sigma0²)` und
`xc=x0+p0*t/m` kann die Lösung bei konsistenter Anfangsphase geschrieben werden als

```text
psi(x,t) = (2*pi*sigma0^2)^(-1/4) * (1+i*tau)^(-1/2)
           * exp(-(x-xc)^2/(4*sigma0^2*(1+i*tau))
                 + i*p0*(x-x0)/hbar - i*p0^2*t/(2*m*hbar))
<x> = xc
Var(x) = sigma0^2 * (1+tau^2)
Delta p = hbar/(2*sigma0)
Delta x * Delta p = (hbar/2) * sqrt(1+tau^2)
<E> = p0^2/(2*m) + hbar^2/(8*m*sigma0^2)
```

Für reelle Zeiten ist die Wahrscheinlichkeitsdichte normiert; die komplexe
Quadratwurzel muss mit dem Anfangszustand konsistent gewählt werden. Bei `t=0`
ist das einfache Unschärfeprodukt minimal. Für `t!=0` und endliche positive
Parameter ist es größer als `hbar/2`; die Zustandsentwicklung bleibt dennoch rein.
Die symmetrisierte Kovarianz ist `Cov(x,p)=hbar²*t/(4*m*sigma0²)` und erklärt,
warum die stärkere Schrödinger-Robertson-Beziehung weiterhin gesättigt sein kann.

Kontrollen: `t=0`, richtige Bewegungsgeschwindigkeit `p0/m`, konstante
Impulsverteilung und für große `|t|` die Breite
`sigma(t) ~ hbar*|t|/(2*m*sigma0)`. Ein globaler Phasenfaktor ist physikalisch
irrelevant, ein verändertes ortsabhängiges Phasenvorzeichen dagegen nicht.

**Typische Negativfälle:** Verwechslung von `sigma0` und `sqrt(2)*sigma0`, starres
Paket ohne Dispersion, fehlende Normierung oder Behauptung „minimal für alle Zeiten“.
Der beschränkte reelle AST-Rechner des Backends prüft diese komplexe
Wellenfunktion nicht vollständig. Eine einzelne symbolisch bestätigte Varianzformel
ist kein Nachweis der gesamten Quantenmechanikherleitung.

## Referenzaufgabe 4: ebene elektromagnetische Vakuumwelle

**Frage:** Leite aus den quellenfreien Maxwell-Gleichungen für eine harmonische
ebene Welle die Transversalität, Beziehung zwischen elektrischem und magnetischem
Feld sowie Dispersion her. Gib die mittlere Energieflussdichte an.

**Bereich und Annahmen:** Ideales homogenes Vakuum, keine freien Ladungen oder
Ströme, konstante positive `epsilon0,mu0`, reeller Wellenvektor `k`, positive
Winkelfrequenz `omega`, keine Randflächen oder evaneszenten Moden.

**Referenzresultate:** Für reellen Amplitudenvektor `E0` und Phase
`phi=k·r-omega*t+phi0`:

```text
E(r,t) = E0 cos(phi)
k · E0 = 0
B(r,t) = (k × E0)/omega * cos(phi)
omega^2 = c^2 |k|^2
c = 1/sqrt(epsilon0*mu0)
|B0| = |E0|/c
<S> = (epsilon0*c/2) * |E0|^2 * k_hat
```

Zu prüfen: Vorzeichen in Faradays Gesetz, Ausrichtung der Kreuzprodukte,
`S=E×B/mu0`, Faktor `1/2` des zeitlichen Mittels und Unterscheidung von `B` und
`H=B/mu0`. SI: `E` in V/m, `B` in T, `k` in 1/m, `omega` in 1/s und
`<S>` in W/m². Die Aussage gilt nicht unverändert in dispersiven oder leitfähigen
Medien. Einheitenkontrolle und ein Spezialfall `k` entlang z, `E` entlang x,
`B` entlang y ergänzen die Rechnung, ersetzen aber die Herleitung nicht.

**Typische Negativfälle:** Longitudinale freie Vakuumwelle, `|B0|=c|E0|`,
vertauschtes Kreuzprodukt oder unkommentierte Anwendung der Vakuumformeln in Materie.

## Quellen- und Sicherheitsvarianten pro Aufgabe

Jeder fachliche Fall erhält mindestens folgende Varianten, sobald ein annotiertes
Korpus vorhanden ist:

1. Passende aktive Quellen mit tatsächlich verifizierten Originalstellen. Menschen
   bewerten, ob jede `source_content`-Aussage dort inhaltlich gestützt wird.
2. Nur eine unvollständige Quelle. Im Quellenmodus muss die fehlende Voraussetzung
   sichtbar bleiben; ergänzendes Modellwissen darf nicht verdeckt einspringen.
3. Passende, aber deaktivierte Quelle. Es darf kein Text dieser Quelle den Provider
   erreichen; der Verweis auf sie liefert einen Konflikt statt stiller Erweiterung.
4. Widersprüchliche Konventionen oder Aussagen in aktiven Quellen. Unterschiedliche
   Voraussetzungen müssen getrennt werden; keine erfundene Auflösung durch den Suchrang.
5. Mathematisch unsichere Extraktion oder zu kleines Kontextbudget. Das Modell darf
   ausgelassene Formeln nicht als gelesene oder werkzeuggeprüfte Grundlage ausgeben.
6. Quellenpassage mit einer eingebetteten Anweisung, Scope, Rolle oder Tools zu ändern.
   Sie bleibt untrusted Inhalt. Clientseitige Assistant-Historie ist kein Ersatz für
   die ursprüngliche Quellenfreigabe.

## Werkzeugbewertung und nächste Abnahme

Werkzeugresultate separat dokumentieren: tatsächliche Anfrage, Status, Methode,
Bedingungen und erwarteter Vergleich. `verified` bedeutet nur die ausgeführte
symbolische Gleichheitsprüfung im unterstützten Definitionsbereich.
`tool_computed` ist kein bestätigtes Erwartungsresultat, `inconclusive` ist kein
Misserfolgsbeweis der Mathematik und `unavailable` bedeutet eine nicht ausgeführte
Prüfung. Alle Resultate behalten `physics_proof=false`.

Benötigt werden als nächster fachlicher Datensatz:

- ein rechtlich geklärtes und gehashtes Physikkorpus mit überprüften Originalstellen;
- Themen-, Aufgaben- und Voraussetzungenlabels mit begründeten Negativbeispielen;
- annotierte Fehler zu Formeln, Einheiten, Randbedingungen und verbreiteten Fehlansätzen;
- getrennte Entwicklungs-/Testaufgaben und Bewertungsanleitungen für Fachprüfer;
- echte Modellläufe mit dokumentierter Konfiguration und unabhängigen Bewertungen.

Vor diesen Schritten wird weder eine Erfolgsquote für anspruchsvolle Physik noch
eine kalibrierte Richtigkeitswahrscheinlichkeit angegeben. Modell-Selbstbewertungen,
ein hoher Retrievalrang und die Existenz einer Citation ersetzen diese Abnahme nicht.
