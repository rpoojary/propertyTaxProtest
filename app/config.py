"""County configuration (counties/config.yaml)."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "counties", "config.yaml")

REQUIRED = ("name", "cad_name", "cad_abbrev", "cad_address", "protest_url",
            "tax_year", "date_format", "db")

# Settings holding file paths, made absolute relative to the repo root.
PATH_KEYS = ("db", "source", "details", "parcels", "market_areas", "exemptions")

# Fields safe to expose to the browser.
PUBLIC = ("name", "cad_name", "cad_abbrev", "cad_address", "protest_url", "tax_year")


def load_counties(path=None):
    """Return {county_id: settings} with `db`/`source`/`details` made absolute."""
    import yaml

    with open(path or CONFIG_PATH) as f:
        raw = yaml.safe_load(f)
    return {cid: normalize(cid, cfg) for cid, cfg in raw.items()}


def normalize(cid, cfg):
    missing = [k for k in REQUIRED if cfg.get(k) in (None, "")]
    if missing:
        raise ValueError(f"county {cid!r} is missing {', '.join(missing)}")
    out = dict(cfg)
    out["id"] = cid
    out["tax_year"] = int(cfg["tax_year"])
    for key in PATH_KEYS:
        if out.get(key) and not os.path.isabs(out[key]):
            out[key] = os.path.join(ROOT, out[key])
    return out


def public_view(cfg):
    out = {k: cfg[k] for k in PUBLIC}
    out["id"] = cfg["id"]
    out["available"] = os.path.exists(cfg["db"])
    return out
