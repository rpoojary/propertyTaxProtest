"""Protest letter: content computed from data, rendered to PDF with reportlab.

Every statement comes from the equity analysis, the comparison sets, the
county config, or what the owner typed (name, conditions, repair costs).
build() returns plain blocks; render_pdf() escapes all text before it
reaches reportlab's markup parser.
"""
import io
from datetime import date
from xml.sax.saxutils import escape

SET_TITLES = {
    "neighborhood": "Recently transferred homes in my neighborhood",
    "zip": "Similar recently transferred homes in my ZIP code",
    "all_similar": "All similar homes in my ZIP code",
}


class NoReduction(ValueError):
    """The data does not support a lower value, so no letter is produced."""


def money(v):
    return f"${v:,.0f}"


def clean_owner_input(body):
    """Validate and trim the owner's input from the request body."""
    name = str(body.get("owner_name") or "").strip()[:120] or "Property Owner"
    conditions = [str(c).strip()[:300] for c in (body.get("conditions") or []) if str(c).strip()][:20]
    repairs = []
    for r in (body.get("repairs") or [])[:20]:
        try:
            cost = float(r.get("cost") or 0)
        except (TypeError, ValueError, AttributeError):
            continue
        if 0 < cost < 10_000_000:
            repairs.append({"desc": str(r.get("desc") or "").strip()[:200] or "Repair", "cost": round(cost)})
    return {"name": name, "conditions": conditions, "repairs": repairs}


def opinion_of_value(subject, equity, sets, repair_total):
    """Requested value and its basis. Mirrors updateProtest() in static/index.html."""
    if equity.get("available") and equity.get("supports_reduction"):
        base, basis = equity["median_adjusted"], "equity"
    else:
        medians = [s["stats"]["median"] for s in sets.values() if s["stats"]["count"]]
        if not medians:
            raise NoReduction("no comparable properties were found")
        base, basis = round(sum(medians) / len(medians) / 1000) * 1000, "set_medians"
    requested = base - repair_total
    if requested >= subject["appraised_val"]:
        raise NoReduction("the comparable appraised values do not support a lower value")
    return {"base": base, "basis": basis, "requested": requested, "reduction": subject["appraised_val"] - requested}


def build(cfg, subject, equity, sets, owner, today=None):
    """Letter content as renderer-neutral blocks (static/js/engine.js builds the same list).

    Block types: {"t": "title"|"small"|"h2", "text"}, {"t": "p", "runs": [[text, bold], ...]},
    {"t": "table", "rows", "widths" (inches), "highlight" (row indexes)}, {"t": "space", "h" (points)}.
    """
    repair_total = sum(r["cost"] for r in owner["repairs"])
    op = opinion_of_value(subject, equity, sets, repair_total)
    s, c, eq, val = subject, cfg, equity, subject["appraised_val"]
    street = f"{s['street_num']} {s['street_name']}".strip()
    addr = ", ".join(x for x in (street, s.get("city"), f"TX {s.get('zip') or ''}".strip()) if x)

    grounds = []
    if eq.get("available") and eq.get("supports_reduction"):
        grounds.append(
            f"Unequal appraisal (Texas Tax Code §41.41(a)(2), §42.26(a)(3)): my appraised value of {money(val)} "
            f"exceeds the median appraised value of {eq['count']} comparable properties, appropriately "
            f"adjusted, which is {money(eq['median_adjusted'])}.")
    above = [k for k in SET_TITLES if sets[k]["stats"]["count"] and val > sets[k]["stats"]["median"]]
    if above and not grounds:
        grounds.append(
            "Unequal appraisal (Texas Tax Code §41.41(a)(2)): my appraised value is higher than the median "
            "appraised value of " + "; ".join(
                f"{sets[k]['stats']['count']} {SET_TITLES[k].lower()} ({money(sets[k]['stats']['median'])})"
                for k in above) + ".")
    if owner["conditions"]:
        grounds.append("Property-specific conditions, described below.")
    if repair_total:
        grounds.append(f"Repair costs totaling {money(repair_total)}, based on the estimates listed below.")

    def p(*runs):
        return {"t": "p", "runs": [[r, False] if isinstance(r, str) else list(r) for r in runs]}

    blocks = [
        {"t": "title", "text": "Property Tax Protest"},
        {"t": "small", "text": f"{c['tax_year']} Appraisal Year · {c['cad_name']}\n"
                               f"{(today or date.today()).strftime('%B %d, %Y').replace(' 0', ' ')}"},
        {"t": "space", "h": 8},
        p(("To:", True), f" Appraisal Review Board, {c['cad_name']}, {c['cad_address']}"),
        p(("From:", True), f" {owner['name']}\n", ("Re:", True), f" Account {s['account']}, {addr}"),
        {"t": "space", "h": 6},
        p("Dear Members of the Appraisal Review Board,"),
        p(f"I am protesting the {c['tax_year']} appraised value of ", (money(val), True),
          f" for my property at {addr} and request that it be reduced to ", (money(op["requested"]), True),
          f", a reduction of {money(op['reduction'])} ({op['reduction'] / val * 100:.1f}%)."),
        p("This protest is based on the following grounds:"),
    ]
    blocks += [p(f"{i}. {g}") for i, g in enumerate(grounds, 1)]

    yr = s.get("year_built") or "—"
    eff = f" (effective {s['eff_year_built']})" if s.get("eff_year_built") else ""
    rooms = f"{s['beds']} bedrooms, " if s.get("beds") is not None else ""
    baths = ""
    if s.get("full_baths") is not None:
        baths = f"{s['full_baths']} full / {s.get('half_baths') or 0} half baths, "
    blocks += [
        {"t": "h2", "text": "Subject property"},
        p(f"Account {s['account']}. {rooms}{baths}"
          + (f"{s['living_sqft']:,.0f} sq ft living area" if s.get("living_sqft") else "living area not recorded")
          + f", built {yr}{eff}"
          + (f", quality {s['quality']}" if s.get("quality") else "")
          + (f", lot {s['lot_sqft']:,.0f} sq ft" if s.get("lot_sqft") else "")
          + f". Appraised at {money(val)}: improvements {money(s['improvement_val'] or 0)}, "
            f"land {money(s['land_val'] or 0)}."),
        {"t": "small", "text": f"All values are appraised values from the {c['cad_name']} {c['tax_year']} "
                               "appraisal roll, not sale prices."},
    ]

    n = 1
    if eq.get("available"):
        cr, prm = eq["criteria"], eq["params"]
        radius = eq["search"].get("radius_mi")
        where = (f"within {radius:g} {'mile' if radius == 1 else 'miles'} of my property"
                 if eq["search"]["method"] == "radius" else f"in neighborhood {eq['search'].get('nbhd')}")
        grades = " and ".join(g for g in (f"quality grade ({cr['quality']})" if cr.get("quality") else "",
                                          f"condition rating ({cr['condition']})" if cr.get("condition") else "") if g)
        year_key = "eff_year_built" if cr["year_basis"].startswith("effective") else "year_built"
        rows = [["Address", "Miles", "Sq ft", "Year", "Appraised", "Size adj.", "Age adj.", "Land adj.", "Adjusted"],
                [f"{street} (subject)", "", f"{s['living_sqft']:,.0f}", str(s.get(year_key) or ""), money(val),
                 "", "", "", ""]]
        rows += [[r["address"], "" if r.get("distance_mi") is None else f"{r['distance_mi']:.2f}",
                  f"{r['living_sqft']:,.0f}", str(r.get(year_key) or ""), money(r["appraised_val"]),
                  f"{r['size_adj']:+,}", f"{r['age_adj']:+,}", f"{r['land_adj']:+,}", money(r["adjusted_val"])]
                 for r in eq["comps"]]
        rows.append(["Median adjusted value"] + [""] * 7 + [money(eq["median_adjusted"])])
        verdict = (f"My appraised value is {money(eq['difference'])} more than this median."
                   if eq["supports_reduction"] else "My appraised value is not above this median.")
        blocks += [
            {"t": "h2", "text": f"Evidence {n}: Comparable properties, appropriately adjusted"},
            p(f"I selected the {eq['count']} most similar properties {where} in the same property category"
              + (f" and the same {grades}" if grades else "")
              + f", with {cr['sqft_low']:,}–{cr['sqft_high']:,} sq ft of living area and {cr['year_basis']} between "
              f"{cr['year_low']} and {cr['year_high']}. Each comparable's appraised value is adjusted to my "
              "property: living area at the comparable's own improvement value per square foot; age at "
              f"{prm['age_rate'] * 100:.1f}% of its improvement value per year of difference; land by the "
              "difference in appraised land value."),
            {"t": "table", "rows": rows, "widths": [1.55, 0.45, 0.5, 0.4, 0.75, 0.7, 0.65, 0.7, 0.75],
             "highlight": [1, len(rows) - 1]},
            p(f"The median of the {eq['count']} adjusted values is ", (money(eq["median_adjusted"]), True),
              f" (unadjusted median {money(eq['unadjusted_median'])}). {verdict}"),
        ]
        n += 1

    for key, title in SET_TITLES.items():
        st = sets[key]["stats"]
        if st["count"]:
            blocks += [{"t": "h2", "text": f"Evidence {n}: {title} (appraised value)"},
                       p(f"{st['count']} properties on the {c['cad_abbrev']} {c['tax_year']} roll match "
                         f"{describe(sets[key]['criteria'])}. Median appraised value ", (money(st["median"]), True),
                         f"; range {money(st['low'])} to {money(st['high'])}.")]
            n += 1

    if owner["conditions"]:
        blocks.append({"t": "h2", "text": "Property-specific conditions"})
        blocks += [p(f"• {x}") for x in owner["conditions"]]
    if owner["repairs"]:
        rows = [["Description", "Estimated cost"]] + [[r["desc"], money(r["cost"])] for r in owner["repairs"]]
        rows.append(["Total", money(repair_total)])
        blocks += [{"t": "h2", "text": "Repair costs"},
                   {"t": "table", "rows": rows, "widths": [4.5, 1.5], "highlight": [len(rows) - 1]},
                   {"t": "small", "text": "Copies of the estimates are attached."}]

    base_label = ("Median adjusted value of comparable properties (Evidence 1)" if op["basis"] == "equity"
                  else "Average of the comparison-set median appraised values, rounded to $1,000")
    rows = [["Basis", "Value"], [base_label, money(op["base"])]]
    if repair_total:
        rows.append(["Less: repair costs", f"-{money(repair_total)}"])
    rows.append(["Requested appraised value", money(op["requested"])])
    blocks += [
        {"t": "h2", "text": "Requested value"},
        {"t": "table", "rows": rows, "widths": [4.5, 1.5], "highlight": [len(rows) - 1]},
        {"t": "space", "h": 6},
        p(f"Based on the evidence above, I respectfully request that the Appraisal Review Board reduce the "
          f"appraised value of my property from {money(val)} to {money(op['requested'])}. Thank you for your "
          "time and consideration."),
        {"t": "space", "h": 18},
        p("Respectfully submitted,"),
        {"t": "space", "h": 26},
        p(f"______________________________\n{owner['name']}\n{addr}"),
        {"t": "space", "h": 14},
        {"t": "small", "text": f"Data source: {c['cad_name']}, {c['tax_year']} appraisal roll. Prepared with a "
                               "free self-help tool; not legal or appraisal advice."},
    ]
    return {"opinion": op, "address": addr, "owner_name": owner["name"], "blocks": blocks}


def render_pdf(content):
    """PDF bytes for build() output (reportlab). static/js/pdf.js renders the same blocks in the browser."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ss = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=ss["BodyText"], fontName="Times-Roman", fontSize=10.5, leading=14)
    styles = {
        "p": body,
        "small": ParagraphStyle("small", parent=body, fontSize=8, leading=10, textColor=colors.HexColor("#555555")),
        "title": ParagraphStyle("title", parent=ss["Title"], fontName="Times-Bold", fontSize=17),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Times-Bold", fontSize=12, spaceBefore=10),
    }
    cell = ParagraphStyle("cell", parent=body, fontName="Helvetica", fontSize=7, leading=8.5)

    def markup(text):
        return escape(text).replace("\n", "<br/>")

    story = []
    for b in content["blocks"]:
        if b["t"] == "p":
            story.append(Paragraph("".join(f"<b>{markup(t)}</b>" if bold else markup(t) for t, bold in b["runs"]),
                                   body))
        elif b["t"] in styles:
            story.append(Paragraph(markup(b["text"]), styles[b["t"]]))
        elif b["t"] == "space":
            story.append(Spacer(1, b["h"]))
        elif b["t"] == "table":
            hl = b.get("highlight", [])
            data = [[Paragraph(f"<b>{markup(x)}</b>" if i in hl else markup(x), cell) for x in row]
                    for i, row in enumerate(b["rows"])]
            t = Table(data, colWidths=[w * inch for w in b["widths"]], repeatRows=1)
            style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
                     ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf3")),
                     ("VALIGN", (0, 0), (-1, -1), "TOP")]
            style += [("BACKGROUND", (0, i), (-1, i), colors.HexColor("#e8f5e9")) for i in hl]
            t.setStyle(TableStyle(style))
            story.append(t)
        else:
            raise ValueError(f"unknown block type {b['t']!r}")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, leftMargin=0.7 * inch, rightMargin=0.7 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                            title=f"Property Tax Protest - {content['address']}", author=content["owner_name"])
    doc.build(story)
    return buf.getvalue()


def describe(c):
    parts = []
    if c.get("nbhd"):
        parts.append(f"neighborhood code {c['nbhd']}")
    if c.get("zip"):
        parts.append(f"ZIP {c['zip']}")
    if c.get("beds") is not None:
        parts.append(f"{c['beds']} bedrooms")
    if c.get("min_full_baths") is not None:
        parts.append(f"at least {c['min_full_baths']} full baths")
    if c.get("full_baths") is not None:
        parts.append(f"{c['full_baths']} full / {c['half_baths']} half baths")
    if c.get("sqft_low") is not None:
        parts.append(f"{c['sqft_low']:,}–{c['sqft_high']:,} sq ft living area")
    if c.get("deed_since"):
        parts.append(f"deed recorded on or after {c['deed_since']}")
    return ", ".join(parts)
