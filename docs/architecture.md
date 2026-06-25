# Architektur: Kicktipp-Analytics

## Ziel

Pipeline, die Tipps/Ergebnisse einer Kicktipp-WM-Runde periodisch ausliest,
nach den Liga-eigenen Punkteregeln bewertet, Rankings/Statistiken berechnet
und in einer Form ablegt, die Power BI unabhängig von der gewählten
Power-BI-Variante (Desktop oder Pro/Premium mit Gateway) konsumieren kann.

## Schichten

```
extraction/    Kicktipp-Scraper (Playwright) hinter IKicktippDataSource
calculation/   Punkteregeln, Ranking, Statistiken - reine, testbare Logik
persistence/   IDataSink-Implementierungen (SQL, CSV)
pipeline/      Orchestrator, der alles per Dependency Injection verbindet
config/        Settings aus Umgebungsvariablen/.env
domain/        Reine Datenklassen, von keiner anderen Schicht abhängig
scheduler/     Entry-Point (Composition Root) für cron/systemd
```

Abhängigkeitsrichtung: `domain` hängt von nichts ab. `calculation` hängt
nur von `domain`. `extraction` und `persistence` hängen von `domain` und
ihren eigenen Interfaces ab. `pipeline` kennt nur Interfaces, keine
konkreten Implementierungen. Nur `scheduler/run_pipeline.py` kennt
konkrete Klassen und verdrahtet sie (Composition Root).

## Warum kein direkter API-Zugriff

Kicktipp bietet keine offizielle Daten-API an. Alle bekannten
Community-Tools lesen die Daten per Browser-Automatisierung von den
HTML-Seiten. `KicktippScraper` ist deshalb hinter `IKicktippDataSource`
versteckt: Sollte sich das Datenzugriffsmodell ändern, wird nur eine neue
Implementierung registriert, der Rest der Pipeline bleibt unverändert.

**Wichtig:** Die CSS-Selektoren in `KicktippSelectors` und
`KicktippAuthenticator` sind gegen reale Kicktipp-Seitenstrukturen
recherchiert (öffentlich einsehbare Tippübersicht-Seite + Quellcode-Abgleich
mit mehreren aktiv gepflegten Open-Source-Kicktipp-Bots) und größtenteils
verifiziert. Offen ist noch die exakte HTML-Struktur einzelner
Tippübersicht-Zellen, wenn Tipp und Punkte-Badge ohne Trennzeichen direkt
hintereinander stehen - siehe den Stand-der-Verifizierung-Block am Anfang
von `kicktipp_scraper.py` sowie `scripts/inspect_tip_cell.py` und
`tests/integration/README.md`.

## Punkteregeln der Liga

| Tendenz | Tordifferenz | Ergebnis |
|---|---|---|
| Sieg: 2 | 3 | 4 |
| Unentschieden: 2 | - | 4 |

Zusätzlich bei K.o.-Spielen: ein separater Tipp "Wer gewinnt nach
Elfmeterschießen?", flach mit 4 Punkten bei richtiger Antwort bewertet
(Reihenfolge irrelevant).

Bei Punktgleichstand in der Gesamtpunktzahl entscheidet die Anzahl der
Spieltagssiege über die Platzierung.

Diese Regeln sind als zwei austauschbare `IPointsCalculator`-Strategien
implementiert (`TendenzTordifferenzErgebnisCalculator`,
`PenaltyWinnerCalculator`), die der `ScoringResolver` je nach Spieltyp
kombiniert. Eine neue Sonderregel bedeutet: neue Klasse schreiben und in
`scheduler/run_pipeline.py` registrieren - kein bestehender Code wird
verändert (Open/Closed Principle).

Das "Strategieverbot" (max. 2/3 gleiche Tipps ab 9 Spielen pro Spieltag)
und die 0-Minuten-Abgabefrist werden bewusst **nicht** nachgebaut, da diese
Regeln von Kicktipp selbst bei der Tippabgabe durchgesetzt werden.

## Datenmodell (Star-Schema)

`dim_player`, `dim_team`, `dim_match` als Dimensionen. `fact_tip` (ein
Tipp inkl. Punkteaufschlüsselung), `fact_ranking_snapshot` (eine Zeile pro
Spieler und Spieltag mit kumulierten Werten - deckt Formkurve,
Ranking-Verlauf und aktuelle Bestenliste in einer Tabelle ab) und
`fact_player_statistics` (inkl. Aufschlüsselung der Tendenz-Treffer nach
Heimsieg/Remis/Auswärtssieg) als Fakten.

## Power-BI-Unabhängigkeit

`IDataSink` ist die einzige Schnittstelle, mit der Power BI in Berührung
kommt. `SqlDataSink` (SQLAlchemy Core, funktioniert identisch gegen SQLite
und PostgreSQL) und `CsvDataSink` (eine Datei pro Tabelle) lassen sich
beide gleichzeitig aktivieren. Power BI Desktop kann gegen die
CSV-Dateien oder direkt gegen die DB-Datei laufen, Power BI Pro/Premium
später per On-Premises-Gateway gegen dieselbe PostgreSQL-Instanz - ohne
dass sich am Pipeline-Code etwas ändert.

## Lokales Test-Dashboard

`frontend/` ist ein kleines Flask-Dashboard, das ausschließlich gegen das
Star-Schema liest (dieselben Tabellen, die später auch Power BI sieht).
Es kennt weder `pipeline` noch `extraction` - dadurch ist es egal, ob die
Daten von `MockKicktippDataSource` (für Tests ohne echten Kicktipp-Zugang,
siehe `scripts/seed_sample_data.py`) oder vom echten `KicktippScraper`
stammen. Das Dashboard ist damit eine 1:1-Vorschau auf das, was später in
Power BI ankommt, und der schnellste Weg, neue Berechnungslogik visuell zu
prüfen, bevor ein Power-BI-Report aufgesetzt wird.

## Bekannte Vereinfachungen (bewusstes YAGNI)

- Alle `write_*`-Methoden in `SqlDataSink` ersetzen den kompletten
  Tabelleninhalt (Delete + Insert) statt inkrementeller Upserts. Bei der
  Datenmenge eines privaten Tippspiels unkritisch.
- Die K.o.-Phasen-Erkennung in `KicktippScraper.get_matches` ist als TODO
  markiert (aktuell hartcodiert `MatchType.GROUP`).