"""JSON API. Owner names are not stored in the app DB and never returned."""
import os

from flask import Blueprint, abort, current_app, g, jsonify, request

from app import comps
from app.config import public_view
from app.db import connect_ro

bp = Blueprint("api", __name__, url_prefix="/api")


def county_cfg(county):
    cfg = current_app.config["COUNTIES"].get(county)
    if cfg is None or not os.path.exists(cfg["db"]):
        abort(404, description=f"county {county!r} is not available")
    return cfg


def county_db(county):
    cfg = county_cfg(county)
    if "db" not in g:
        g.db = connect_ro(cfg["db"])
    return cfg, g.db


@bp.teardown_app_request
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@bp.errorhandler(404)
def not_found(e):
    return jsonify({"error": e.description}), 404


@bp.get("/counties")
def counties():
    return jsonify([public_view(c) for c in current_app.config["COUNTIES"].values()])


@bp.get("/<county>/search")
def search(county):
    _, db = county_db(county)
    return jsonify(comps.search(db, request.args.get("q", "")))


@bp.get("/<county>/property/<account>")
def property_detail(county, account):
    _, db = county_db(county)
    prop = comps.get_property(db, account)
    if prop is None:
        abort(404, description="property not found")
    return jsonify(prop)


@bp.get("/<county>/comps/<account>")
def comparables(county, account):
    cfg, db = county_db(county)
    subject = comps.get_property(db, account)
    if subject is None:
        abort(404, description="property not found")
    return jsonify(comps.find_comps(db, subject, cfg["tax_year"]))
