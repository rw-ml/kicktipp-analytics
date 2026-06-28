"""
Einmaliges Diagnose-Skript zur Klärung der letzten offenen Frage im
Kicktipp-Scraper: Wie genau ist eine Tippübersicht-Zelle aufgebaut, wenn ein
Spiel bereits ausgewertet ist (Tipp + Punkte-Badge, z.B. Rohtext "3:03" für
Tipp "3:0" + 3 Punkte)?

Das lässt sich von der Entwicklungsumgebung aus nicht klären, da dort kein
Netzwerkzugriff auf kicktipp.de besteht und ein einfacher Seitenabruf (ohne
echten Browser) nur Text ohne HTML-Struktur liefert. Dieses Skript loggt sich
mit deinen echten Zugangsdaten ein, öffnet die Tippübersicht und schreibt das
rohe HTML der ersten paar bereits ausgewerteten Tipp-Zellen in eine Datei.

Verwendung:
    python scripts/inspect_tip_cell.py [--matchday N]

Voraussetzung: .env mit KICKTIPP_USERNAME, KICKTIPP_PASSWORD,
KICKTIPP_COMMUNITY_URL ist im Projektverzeichnis vorhanden (siehe
.env). Es wird bewusst ein bereits gespielter Spieltag benötigt,
da nur dort Punkte-Badges überhaupt auftreten können - bei Spieltag 1
würde das Skript ggf. nur unausgewertete Tipps ohne Badge zeigen.

Ergebnis: `tip_cell_inspection.html` im Projektverzeichnis. Diese Datei kann
entweder selbst im Texteditor angeschaut werden (die Tipp-Struktur ist meist
auch im rohen HTML gut lesbar), oder einfach das Ergebnis dieses Skripts
zurückmelden, dann kann `_extract_tip_score` in kicktipp_scraper.py gezielt
auf die echte Struktur angepasst werden.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Erlaubt den direkten Aufruf "python scripts/inspect_tip_cell.py", ohne
# dass das src-Package vorher installiert oder PYTHONPATH gesetzt werden muss.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from kicktipp_analytics.extraction.auth import KicktippAuthenticator, KicktippCredentials
from kicktipp_analytics.extraction.kicktipp_scraper import KicktippSelectors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matchday",
        type=int,
        default=1,
        help="Spieltag-Nummer, der bereits ausgewertete Spiele enthält (Default: 1).",
    )
    args = parser.parse_args()

    load_dotenv()
    username = os.environ["KICKTIPP_USERNAME"]
    password = os.environ["KICKTIPP_PASSWORD"]
    community_url = os.environ["KICKTIPP_COMMUNITY_URL"]
    headless = os.environ.get("HEADLESS_BROWSER", "true").lower() != "false"

    credentials = KicktippCredentials(
        username=username, password=password, community_url=community_url
    )
    authenticator = KicktippAuthenticator(credentials)
    selectors = KicktippSelectors()

    output_lines: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        print("Logge ein...")
        authenticator.login(page)

        url = f"{community_url}{selectors.TIPPUEBERSICHT_PATH.format(matchday=args.matchday)}"
        print(f"Öffne Tippübersicht: {url}")
        page.goto(url)

        rows = page.locator(selectors.RANKING_ROW_SELECTOR)
        row_count = rows.count()
        print(f"{row_count} Spielerzeilen gefunden.")
        if row_count == 0:
            print(
                f"WARNUNG: Keine Zeilen mit Selektor '{selectors.RANKING_ROW_SELECTOR}' "
                "gefunden. Entweder ist die Tabellen-ID anders als angenommen, "
                "oder der Spieltag hat noch keine Daten. Schreibe trotzdem das "
                "komplette Seiten-HTML zur manuellen Inspektion."
            )
            output_lines.append("=== KOMPLETTE SEITE (kein table#ranking gefunden) ===")
            output_lines.append(page.content())
        else:
            # Erste Zeile mit mindestens einer ausgewerteten Zelle (Text mit ':')
            # suchen und deren Tipp-Zellen roh ausgeben.
            inspected = 0
            for i in range(min(row_count, 10)):
                row = rows.nth(i)
                player_name = row.locator("div.mg_name").inner_text().strip()

                # Erst mit dem bisher angenommenen Selektor versuchen
                cells = row.locator("td.spieltag")
                cell_count = cells.count()
                output_lines.append(f"=== Zeile {i}: Spieler '{player_name}' ({cell_count} Tipp-Zellen via td.spieltag) ===")

                if cell_count == 0:
                    # Selektor stimmt nicht - gesamte Zeile als HTML ausgeben
                    # damit die echten td-Klassen sichtbar werden
                    output_lines.append("--- ALLE td-Elemente dieser Zeile (rohe Klassen) ---")
                    all_tds = row.locator("td")
                    for t in range(min(all_tds.count(), 20)):
                        td = all_tds.nth(t)
                        cls = td.get_attribute("class") or "(keine Klasse)"
                        text = td.inner_text().strip()[:40]
                        output_lines.append(f"  td[{t}] class={cls!r}  text={text!r}")
                    output_lines.append("")
                    output_lines.append("--- Vollständiges HTML der ersten Zeile ---")
                    output_lines.append(row.inner_html())
                    output_lines.append("")
                else:
                    for c in range(cell_count):
                        cell = cells.nth(c)
                        text = cell.inner_text().strip()
                        html = cell.inner_html()
                        output_lines.append(f"--- Zelle {c}: Text={text!r} ---")
                        output_lines.append(html)
                        output_lines.append("")

                inspected += 1
                if inspected >= 3:
                    break

        context.close()
        browser.close()

    output_path = Path(__file__).resolve().parent.parent / "tip_cell_inspection.html"
    output_path.write_text("\n".join(output_lines), encoding="utf-8")
    print(f"\nFertig. Ergebnis geschrieben nach: {output_path}")
    print(
        "Bitte den Inhalt dieser Datei anschauen oder mir zurückmelden - "
        "damit kann _extract_tip_score() in kicktipp_scraper.py final auf "
        "die echte Zellenstruktur angepasst werden."
    )


if __name__ == "__main__":
    main()