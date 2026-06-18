# Kicktipp Analytics

Pipeline, die eine Kicktipp-WM-Tippspielrunde periodisch ausliest, nach den
Liga-eigenen Punkteregeln bewertet und für Power BI aufbereitet - egal ob
später Power BI Desktop oder Power BI Pro/Premium mit Gateway verwendet
wird. Details zur Architektur stehen in `docs/architecture.md`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# .env mit echten Kicktipp-Zugangsdaten und DB-/CSV-Konfiguration befüllen
```

## Tests ausführen

```bash
pytest
```

Die Unit-Tests (`tests/unit/`) prüfen die komplette Punkteregel-,
Ranking- und Statistik-Logik ohne externe Abhängigkeiten. Die
Integrationstests (`tests/integration/`) prüfen beide `IDataSink`-
Implementierungen lokal (SQLite, CSV). Es gibt bewusst keinen
automatisierten Test gegen die echte Kicktipp-Seite - siehe
`tests/integration/README.md` für den empfohlenen ersten manuellen Lauf.

## Dashboard zum Testen aller Features (ohne Power BI)

Bevor Power BI angebunden wird, lässt sich die komplette Pipeline lokal
in einem kleinen Web-Dashboard anschauen - Bestenliste mit Formkurve,
Spieltag-Details inkl. Tippverteilung, die Statistik-/Bremsfett-Seite,
Ranking-Verlauf über die Saison sowie einen Tippverhalten-Tab mit
Tendenz-Vergleich, Spielervergleich und Team-Tendenzen pro Spieler.

Mit Testdaten starten (kein Kicktipp-Zugang nötig):

```bash
python scripts/seed_sample_data.py   # erzeugt sample.db mit Beispieldaten
python frontend/app.py                # http://127.0.0.1:5000
```

Mit echten Pipeline-Daten starten: einfach dieselbe `SQL_CONNECTION_URL`
setzen, die auch in der `.env` der Pipeline steht, dann den Server
starten:

```bash
SQL_CONNECTION_URL=postgresql+psycopg2://user:pass@host:5432/kicktipp python frontend/app.py
```

Das Dashboard liest ausschließlich aus den Star-Schema-Tabellen
(`dim_*`/`fact_*`) - exakt das, was später auch Power BI sieht. Es ist
also eine 1:1-Vorschau, unabhängig davon, ob die Daten von
`MockKicktippDataSource` oder vom echten `KicktippScraper` stammen.

## Pipeline ausführen

```bash
python scheduler/run_pipeline.py
```

Für den ersten Lauf empfiehlt sich `HEADLESS_BROWSER=false` in der `.env`,
um zu sehen, ob Login und Navigation auf der echten Kicktipp-Seite
funktionieren, und die Selektoren in
`src/kicktipp_analytics/extraction/kicktipp_scraper.py` ggf. anzupassen.

## Automatisierung auf dem Server

Per cron (täglich, z.B. nachts):

```cron
0 3 * * * cd /pfad/zum/projekt && .venv/bin/python scheduler/run_pipeline.py >> /var/log/kicktipp-analytics.log 2>&1
```

Alternativ ein systemd-Timer, falls auf dem Server bereits andere Dienste
so verwaltet werden.

## Power BI anbinden

**Desktop (ohne eigenen DB-Server):** `CSV_OUTPUT_DIR` in der `.env`
setzen, in Power BI Desktop "Daten abrufen" → "Ordner" auf das
CSV-Verzeichnis zeigen, oder "SQLite-Datenbank" direkt auf die
`.db`-Datei, falls `SQL_CONNECTION_URL=sqlite:///...` verwendet wird.

**Pro/Premium mit On-Premises-Gateway:** `SQL_CONNECTION_URL` auf die
PostgreSQL-Instanz des eigenen Servers zeigen lassen, Gateway auf
demselben Server installieren, in Power BI Service als Datenquelle die
PostgreSQL-DB über das Gateway verbinden.

Beide Varianten lesen aus demselben Star-Schema (`docs/architecture.md`),
der Pipeline-Code muss dafür nicht verändert werden.

## Projektstruktur

```
src/kicktipp_analytics/
  domain/        Reine Datenklassen (Match, Tip, Player, ...)
  extraction/     IKicktippDataSource + Playwright-Scraper + Mock-Datenquelle
  calculation/    Punkteregeln (Strategy), Ranking, Statistiken
  persistence/    IDataSink + SQL-/CSV-Implementierung, Star-Schema
  pipeline/       Orchestrator (Dependency Injection)
  config/         Settings aus .env
frontend/          Lokales Dashboard (Flask) zum Testen aller Features
scripts/           seed_sample_data.py - Pipeline mit Testdaten füllen
scheduler/        Entry-Point für cron/systemd
tests/unit/       Reine Logik-Tests
tests/integration/ Tests gegen SQLite/CSV (kein Live-Kicktipp-Zugriff)
docs/             Architektur-Dokumentation
```

## Bekannte offene Punkte

- **Schema-Änderungen erfordern eine frische Datenbank-Datei.** `SqlDataSink`
  nutzt `metadata.create_all()`, das nur fehlende Tabellen anlegt, aber
  niemals bestehende Tabellen ändert. Wenn sich das Schema ändert (z.B. neue
  Spalten in `fact_player_statistics`), gegen eine bereits existierende
  SQLite-Datei aber die alte Struktur bestehen bleibt → Fehler wie
  `no such column`. Abhilfe: die `.db`-Datei löschen und die Pipeline/das
  Seed-Skript neu laufen lassen (unkritisch, da ohnehin nichts dauerhaft
  historisiert wird - jeder Lauf schreibt die Fakten-Tabellen komplett neu).

- Scraper-Selektoren (`KicktippSelectors`, `KicktippAuthenticator`) sind
  unverifiziert, da aus der Entwicklungsumgebung kein Zugriff auf
  kicktipp.de möglich war - vor dem ersten Produktivlauf gegen die echte
  Seite prüfen.
- K.o.-Phasen-Erkennung in `KicktippScraper.get_matches` ist als TODO
  markiert.