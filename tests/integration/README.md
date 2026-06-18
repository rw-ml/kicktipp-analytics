# Integrationstests

`test_sql_sink.py` und `test_csv_sink.py` laufen vollständig lokal (SQLite
in einem temporären Verzeichnis bzw. CSV-Dateien in `tmp_path`) und
benötigen keinen Netzwerkzugriff.

Es gibt bewusst **keinen** Integrationstest gegen die echte Kicktipp-Seite
(`KicktippScraper`): Die Entwicklungsumgebung, in der dieses Projekt erstellt
wurde, hatte keinen Netzwerkzugriff auf kicktipp.de. Die Selektoren in
`KicktippSelectors` und `KicktippAuthenticator` sind deshalb ein fachlich
plausibler, aber unverifizierter Entwurf.

Empfehlung für den ersten echten Lauf:

1. `HEADLESS_BROWSER=false` in der `.env` setzen.
2. `python scheduler/run_pipeline.py` einmal mit echten Zugangsdaten
   ausführen und beobachten, ob Login und Tabellen-Navigation funktionieren.
3. Bei Abweichungen die Konstanten in `KicktippSelectors`
   (`src/kicktipp_analytics/extraction/kicktipp_scraper.py`) sowie die
   Login-Selektoren in `KicktippAuthenticator`
   (`src/kicktipp_analytics/extraction/auth.py`) an die tatsächliche
   Seitenstruktur anpassen.
4. Danach lohnt sich ein eigener Integrationstest mit `pytest.mark.skipif`
   (z.B. abhängig von gesetzten Env-Variablen), der gegen die echte Liga
   läuft, ohne dass er in CI-Umgebungen ohne Zugangsdaten fehlschlägt.
