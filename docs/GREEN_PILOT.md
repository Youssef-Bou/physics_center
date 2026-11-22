# Green-Pilot: ein Fall, zwei Prompts, zwei Methoden

Ziel ist eine begrenzte erste Fallprüfung von `ELECTROSTATIC_GREEN_DIRICHLET`,
keine allgemeine Rangfolge oder Qualitätsbehauptung über Modelle. Pro Methode
werden v1 und v2 mit derselben Frage, denselben Quellen und denselben
Generierungsparametern verglichen. Isoliert erhält der Tutor den festgelegten
Kontext; End-to-end durchläuft er Upload, Analyse, Scope, Suche und Tutor.
Ein Methodenvergleich selbst ist kein kontrollierter Promptvergleich.

## Referenz und Annahmen

Der erweiterte [Datensatz](../apps/api/app/modules/evaluation/data/physics_adaptive_v1.json)
hat jetzt Version **1.1.1**. Gegenüber 1.1.0 sind ausschließlich Beschreibung,
Green-Aufgabe/-Referenz und `em_notes`, Seite 3, präzisiert: planare Symmetrie,
homogene konstante Permittivität und stetige Volumenladungsdichte auf dem
**abgeschlossenen** Intervall. Die ursprünglichen 24 Fälle und alle anderen
Quellenseiten bleiben unverändert. Alte Berichte behalten ihren alten Hash und
dürfen nicht mit dem korrigierten Fall als identischer Versuch verglichen werden.

Es gelten \(L>0\), \(\epsilon>0\), \(\rho\in C([0,L])\),

\[
-\phi''(x)=\rho(x)/\epsilon,\qquad \phi(0)=V_a,\quad \phi(L)=V_b.
\]

Die physikalische Interpretation setzt Translationssymmetrie in den beiden
übrigen Raumrichtungen voraus. Die Dichte hat Einheit C/m³; eine Linienladung,
variable Permittivität und allgemeine dreidimensionale Geometrie sind andere
Probleme. Bloße Stetigkeit auf dem offenen Intervall garantiert keine endlichen
Randwerte. Beispielsweise ist \(\rho(x)=c/x^3\) für \(c>0\) dort stetig, aber mit
dieser singulären Quelle lässt sich kein endlicher linker Dirichletwert herstellen.
Für die SI-Deutung hat \(c\) die Einheit C.

Für \(0<\xi<L\) erfüllen die Zweige

\[
G_-(x,\xi)=\frac{x(L-\xi)}L,\qquad
G_+(x,\xi)=\frac{\xi(L-x)}L
\]

die jeweiligen Nullränder. Stetigkeit bei \(x=\xi\) verhindert einen
\(\delta'\)-Term; der Ableitungssprung ist \(-1\). Damit gilt distributionell
\(-\partial_x^2G=\delta(x-\xi)\). Dies folgt aus der Ableitungsregel für
stückweise glatte Funktionen und ist getrennt von einer Computerrechnung zu
begründen.

Die vollständige Lösung lautet

\[
\phi(x)=V_a(1-x/L)+V_bx/L+
\frac1\epsilon\int_0^L G(x,\xi)\rho(\xi)\,d\xi.
\]

Durch Aufspalten des Integrals bei \(\xi=x\) und zweimaliges Ableiten folgt die
Gleichung; der Integralteil verschwindet an beiden Rändern. Die Stetigkeit der
Quelle liefert eine klassische Lösung in \(C^2([0,L])\). Die Differenz zweier
Lösungen ist linear mit zwei Nullrändern, also identisch null. Ohne Randbedingungen
bleibt eine lineare homogene Ergänzung unbestimmt.

Für konstantes \(\rho_0\) sind zusätzliche Kontrollen

\[
\phi=V_a(1-x/L)+V_bx/L+\frac{\rho_0x(L-x)}{2\epsilon},\qquad
E=-\phi'=\frac{V_a-V_b}L-\frac{\rho_0(L-2x)}{2\epsilon}.
\]

Es gelten \(E'=\rho_0/\epsilon\),
\(\int_0^L E\,dx=V_a-V_b\), \([G]=\mathrm m\) und
\([\rho/\epsilon]=\mathrm{V/m^2}\). Der Integralterm hat somit die Einheit V.

Die Prüfung wurde durch KI-Zweitprüfung und symbolische Identitäten unterstützt.
**Referenz und synthetische Quellen bleiben `unvalidated`.** Eine unabhängige
menschliche Fachabnahme und ein authentisches Lehrdokument fehlen weiterhin.

## Reproduzierbare lokale Prüfung

In `apps/api`, nach der [Installation](DEVELOPMENT.md):

```sh
uv run --frozen --extra math python scripts/green_reference_check.py \
  --output .local/evaluations/green-reference.json
```

Das [Prüfskript](../apps/api/scripts/green_reference_check.py) kontrolliert 20
Identitäten, Einheitenzuordnungen und Negativkontrollen. Es bindet Ergebnis,
Referenz, Datensatz, Quellenseite und Skript durch Hashes. Die Formeln stehen als
vertrauenswürdiger Entwicklercode im Skript; es führt weder Modellcode aus noch
prüft es automatisch sämtliche Aussagen eines Referenztexts oder Modellantworten.

Der folgende Probelauf verwendet ausschließlich simulierte Antworten. End-to-end
benötigt `DATABASE_URL` auf einer migrierten lokalen Entwicklungsdatenbank; siehe
[Entwicklungsanleitung](DEVELOPMENT.md). Vorhandene Berichte werden nie überschrieben.

```sh
for method in isolated end_to_end; do
  uv run --frozen --extra math physics-eval compare-prompts \
    --provider mock \
    --dataset app/modules/evaluation/data/physics_adaptive_v1.json \
    --method "$method" --case-id ELECTROSTATIC_GREEN_DIRICHLET --limit 1 \
    --explanation-depth AUTO --max-output-tokens 4096 --timeout-seconds 120 \
    --output ".local/evaluations/green-$method-mock.json"
done
```

## Begrenzter realer Lauf

Die Freigabe für diesen Piloten umfasst **höchstens vier reale Requestversuche**:
zweimal zwei Promptarme. Fehlversuche zählen; keine automatische Wiederholung.
Vorher muss `PHYSICS_LLM_API_KEY` sicher in der Laufzeit gebunden sein. Die
[Aktivierungsbedingungen](REAL_MODEL_EVALUATION.md) gelten unverändert; der
Schlüssel gehört weder in Chat, Befehlsargumente, Git noch Berichte.

```sh
export PHYSICS_LLM_ENABLE_REAL=1
for method in isolated end_to_end; do
  uv run --frozen --extra math physics-eval compare-prompts \
    --provider openai_responses --model gpt-6.1-sol --reasoning-effort medium \
    --dataset app/modules/evaluation/data/physics_adaptive_v1.json \
    --method "$method" --case-id ELECTROSTATIC_GREEN_DIRICHLET --limit 1 \
    --explanation-depth AUTO --max-output-tokens 4096 --timeout-seconds 120 \
    --allow-paid --allow-unvalidated --max-calls 2 \
    --output ".local/evaluations/green-$method-real.json"
done
```

Die beiden CLI-Prozesse haben jeweils Budget 2. Es gibt keinen über Neustarts
persistierenden Budgetzähler: vorhandene Berichte und Versuche vor Fortsetzung
prüfen; den ganzen Block nicht erneut ausführen. 4096 Outputtokens umfassen auch
Reasoning und garantieren keine vollständige sichtbare Herleitung. Ein abgebrochener
Output ist ein Laufproblem, kein erfundenes wissenschaftliches Fehlurteil.

`--allow-unvalidated` erlaubt hier ausdrücklich einen explorativen Versuch mit
synthetischen Kandidaten; es ersetzt keine Fachabnahme. Ein Lauf ist erst technisch
verwertbar, wenn beide Arme abgeschlossen sind, die Kontext-Hashes innerhalb des
Paars übereinstimmen und `controlled_comparison_eligible=true` vorliegt.

## Auswertung und Abnahme

Die [sechs Bewertungsdimensionen](TUTOR_EVALUATION.md) werden je Antwort separat
mit Methode, Begründung und Antwort-Hash erfasst. Zusätzlich werden alle neun
Pflichtschritte des Falls sowie Erklärungsökonomie geprüft. Besonders zu prüfen:
Sprungvorzeichen, Randlift, vollständige Randwerte, Quellenpositionen,
Herkunftskennzeichnung und unzulässige Verallgemeinerungen. Eine richtige Endformel
allein erfüllt die Herleitung nicht. Auflösbare Citations beweisen keine Stützung.

Ratings bleiben bis zu einer tatsächlichen Beurteilung `not_reviewed`; weder
Mock-Ergebnisse noch die Prüfung der Referenz erhalten erfundene Antwortnoten.
Ein späteres KI-Urteil ist `model_judgment`, keine menschliche Validierung.

## Ausgeführter Stand vom 22. November 2026

- 20/20 Offline-Referenzchecks bestanden; menschliche Fachabnahme offen.
- 435/435 Backend-Tests gegen PostgreSQL bestanden, ohne Fehler oder Skips;
  Ruff und Formatprüfung ebenfalls bestanden.
- Vier Mock-Varianten abgeschlossen, zwei kontrollierte Promptpaare, echte Aufrufe 0.
- Finale lokale Berichte zur präzisierten Version 1.1.1 liegen in
  `apps/api/.local/evaluations/green-pilot-1.1.1-*.json`; sie bleiben außerhalb von Git.
- Reale Generierung und wissenschaftliche Bewertung stehen aus, weil in dieser
  Laufzeit kein `PHYSICS_LLM_API_KEY` gebunden ist.

Für die nächste Phase fehlen ein sicher gebundener Modellzugang, eine unabhängige
fachliche Prüfung des Falls samt Quellen und anschließend rechtlich nutzbare,
annotierte reale Skriptseiten. Vier Aufrufe liefern selbst dann nur eine Fallstudie.
