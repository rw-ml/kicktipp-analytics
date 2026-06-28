"""
Lokales Dashboard zum Testen/Anschauen aller Pipeline-Features, ohne dafür
Power BI zu brauchen. Liest ausschließlich aus dem Star-Schema (siehe
data_access.py) - funktioniert deshalb identisch, egal ob die Daten von
MockKicktippDataSource (siehe scripts/seed_sample_data.py) oder vom echten
KicktippScraper stammen.

Start:
    python frontend/app.py
    # öffnet auf http://127.0.0.1:5000

Standardmäßig wird ./sample.db gelesen (SQLite). Um gegen die echten
Pipeline-Daten zu schauen, vor dem Start dieselbe SQL_CONNECTION_URL wie
in der .env der Pipeline setzen, z.B.:
    SQL_CONNECTION_URL=postgresql+psycopg2://user:pass@host:5432/kicktipp python frontend/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Erlaubt den Start direkt mit "python frontend/app.py", ohne dass das
# src-Package vorher installiert oder PYTHONPATH manuell gesetzt werden muss.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# .env automatisch laden (SQL_CONNECTION_URL, SEASON etc.) - damit
# funktioniert "python frontend/app.py" direkt ohne manuelle env-Exporte.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass  # python-dotenv nicht installiert - env-Variablen müssen manuell gesetzt sein

from flask import Flask, abort, redirect, render_template, url_for  # noqa: E402

import data_access  # noqa: E402

app = Flask(__name__)
app.jinja_env.add_extension("jinja2.ext.do")


@app.context_processor
def inject_globals():
    return {
        "latest_matchday": data_access.latest_matchday_number(),
        "all_matchdays": data_access.all_matchday_numbers(),
        "has_data": data_access.has_data(),
    }


@app.route("/")
def ranking():
    return render_template(
        "ranking.html",
        ranking=data_access.current_ranking(),
        formkurve=data_access.formkurve_series(),
        rank_history=data_access.rank_history_series(),
    )


@app.route("/spieltage")
def matchday_index():
    latest = data_access.latest_matchday_number()
    if latest is None:
        abort(404)
    return redirect(url_for("matchday", matchday_number=latest))


@app.route("/spieltage/<int:matchday_number>")
def matchday(matchday_number: int):
    available = data_access.all_matchdays()
    if matchday_number not in {m["number"] for m in available}:
        abort(404)
    detail = data_access.matchday_detail(matchday_number)
    current = next((m for m in available if m["number"] == matchday_number), None)
    return render_template(
        "matchday.html",
        matchday_number=matchday_number,
        matchday_title=current["title"] if current else f"Spieltag {matchday_number}",
        available_matchdays=available,
        **detail,
    )


@app.route("/details")
def details():
    return render_template("details.html", **data_access.details_data())


# Alte URLs weiterleiten damit bestehende Bookmarks nicht brechen
@app.route("/statistiken")
def statistics():
    return redirect(url_for("details"))


@app.route("/tippverhalten")
def tip_behavior_overview():
    return redirect(url_for("details"))


@app.route("/tippverhalten/<player_id>")
def tip_behavior_detail(player_id: str):
    players = data_access.list_players()
    if player_id not in {p["player_id"] for p in players}:
        abort(404)
    detail = data_access.tip_behavior_detail(player_id)
    return render_template(
        "tip_behavior_detail.html",
        detail=detail,
        players=players,
        player_id=player_id,
    )


if __name__ == "__main__":
    app.run(debug=True)