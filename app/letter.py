"""Protest letter: content computed from data, rendered to PDF with reportlab.

Every statement comes from the equity analysis, the comparison sets, the
county config, or what the owner typed (name, conditions, repair costs).
Owner text is escaped before it reaches reportlab's markup parser.
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
    """Structured letter content (also used by tests)."""
    repair_total = sum(r["cost"] for r in owner["repairs"])
    op = opinion_of_value(subject, equity, sets, repair_total)
    val = subject["appraised_val"]
    street = f"{subject['street_num']} {subject['street_name']}".strip()
    addr = ", ".join(x for x in (street, subject.get("city"), f"TX {subject.get('zip') or ''}".strip()) if x)
    grounds = []
    if equity.get("available") and equity.get("supports_reduction"):
        grounds.append(
            f"Unequal appraisal (Texas Tax Code §41.41(a)(2), §42.26(a)(3)): my appraised value of {money(val)} "
            f"exceeds the median appraised value of {equity['count']} comparable properties, appropriately "
            f"adjusted, which is {money(equity['median_adjusted'])}.")
    above = [k for k, s in sets.items() if s["stats"]["count"] and val > s["stats"]["median"]]
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
    return {
        "date": (today or date.today()).strftime("%B %d, %Y").replace(" 0", " "),
        "cfg": cfg, "subject": subject, "address": addr, "owner": owner,
        "equity": equity, "sets": sets, "opinion": op, "repair_total": repair_total, "grounds": grounds,
    }


def render_pdf(content):
    """PDF bytes for build() output."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    c, s, eq, op = content["cfg"], content["subject"], content["equity"], content["opinion"]
    val = s["appraised_val"]
    ss = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=ss["BodyText"], fontName="Times-Roman", fontSize=10.5, leading=14)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10, textColor=colors.HexColor("#555555"))
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontName="Times-Bold", fontSize=17)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Times-Bold", fontSize=12, spaceBefore=10)
    cell = ParagraphStyle("cell", parent=body, fontName="Helvetica", fontSize=7, leading=8.5)

    def p(text, style=body):
        return Paragraph(text, style)

    def e(text):
        return escape(str(text))

    def grid(rows, widths, header_rows=1, bold_rows=()):
        t = Table([[p(x, cell) if isinstance(x, str) else x for x in r] for r in rows], colWidths=widths,
                  repeatRows=header_rows)
        style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
                 ("BACKGROUND", (0, 0), (-1, header_rows - 1), colors.HexColor("#e8edf3")),
                 ("VALIGN", (0, 0), (-1, -1), "TOP")]
        style += [("BACKGROUND", (0, i), (-1, i), colors.HexColor("#e8f5e9")) for i in bold_rows]
        t.setStyle(TableStyle(style))
        return t

    story = [p("Property Tax Protest", h1),
             p(f"{c['tax_year']} Appraisal Year · {e(c['cad_name'])}<br/>{content['date']}", small), Spacer(1, 8),
             p(f"<b>To:</b> Appraisal Review Board, {e(c['cad_name'])}, {e(c['cad_address'])}"),
             p(f"<b>From:</b> {e(content['owner']['name'])}<br/><b>Re:</b> Account {e(s['account'])}, "
               f"{e(content['address'])}"),
             Spacer(1, 6),
             p("Dear Members of the Appraisal Review Board,"),
             p(f"I am protesting the {c['tax_year']} appraised value of <b>{money(val)}</b> for my property at "
               f"{e(content['address'])} and request that it be reduced to <b>{money(op['requested'])}</b>, "
               f"a reduction of {money(op['reduction'])} ({op['reduction'] / val * 100:.1f}%)."),
             p("This protest is based on the following grounds:")]
    story += [p(f"{i}. {e(g)}") for i, g in enumerate(content["grounds"], 1)]

    story.append(p("Subject property", h2))
    yr = s.get("year_built") or "—"
    eff = f" (effective {s['eff_year_built']})" if s.get("eff_year_built") else ""
    rooms = f"{s['beds']} bedrooms, " if s.get("beds") is not None else ""
    baths = ""
    if s.get("full_baths") is not None:
        baths = f"{s['full_baths']} full / {s.get('half_baths') or 0} half baths, "
    story.append(p(
        f"Account {e(s['account'])}. {rooms}{baths}{s['living_sqft']:,.0f} sq ft living area, built {yr}{eff}"
        + (f", quality {e(s['quality'])}" if s.get("quality") else "")
        + (f", lot {s['lot_sqft']:,.0f} sq ft" if s.get("lot_sqft") else "")
        + f". Appraised at {money(val)}: improvements {money(s['improvement_val'] or 0)}, "
          f"land {money(s['land_val'] or 0)}."))
    story.append(p(f"<i>All values are appraised values from the {e(c['cad_name'])} {c['tax_year']} appraisal "
                   "roll, not sale prices.</i>", small))

    n = 1
    if eq.get("available"):
        cr, prm = eq["criteria"], eq["params"]
        radius = eq["search"].get("radius_mi")
        where = (f"within {radius:g} {'mile' if radius == 1 else 'miles'} of my property"
                 if eq["search"]["method"] == "radius" else f"in neighborhood {e(eq['search'].get('nbhd'))}")
        grades = [f"quality grade ({e(cr['quality'])})" if cr.get("quality") else "",
                  f"condition rating ({e(cr['condition'])})" if cr.get("condition") else ""]
        grades = " and ".join(g for g in grades if g)
        story.append(p(f"Evidence {n}: Comparable properties, appropriately adjusted", h2))
        story.append(p(
            f"I selected the {eq['count']} most similar properties {where} in the same property category"
            + (f" and the same {grades}" if grades else "")
            + f", with {cr['sqft_low']:,}–{cr['sqft_high']:,} sq ft of living area and {cr['year_basis']} between "
            f"{cr['year_low']} and {cr['year_high']}. Each comparable's appraised value is adjusted to my property: "
            "living area at the comparable's own improvement value per square foot; age at "
            f"{prm['age_rate'] * 100:.1f}% of its improvement value per year of difference; land by the difference "
            "in appraised land value."))
        rows = [["Address", "Miles", "Sq ft", "Year", "Appraised", "Size adj.", "Age adj.", "Land adj.", "Adjusted"]]
        year_key = "eff_year_built" if cr["year_basis"].startswith("effective") else "year_built"
        rows.append([f"<b>{e(s['street_num'])} {e(s['street_name'])} (subject)</b>", "", f"{s['living_sqft']:,.0f}",
                     str(s.get(year_key) or ""), money(val), "", "", "", ""])
        for r in eq["comps"]:
            rows.append([e(r["address"]), "" if r.get("distance_mi") is None else f"{r['distance_mi']:.2f}",
                         f"{r['living_sqft']:,.0f}", str(r.get(year_key) or ""), money(r["appraised_val"]),
                         f"{r['size_adj']:+,}", f"{r['age_adj']:+,}", f"{r['land_adj']:+,}", money(r["adjusted_val"])])
        rows.append(["<b>Median adjusted value</b>"] + [""] * 7 + [f"<b>{money(eq['median_adjusted'])}</b>"])
        story.append(grid(rows, [1.55 * inch, 0.45 * inch, 0.5 * inch, 0.4 * inch, 0.75 * inch, 0.7 * inch,
                                 0.65 * inch, 0.7 * inch, 0.75 * inch], bold_rows=(1, len(rows) - 1)))
        verdict = (f"My appraised value is {money(eq['difference'])} more than this median."
                   if eq["supports_reduction"] else "My appraised value is not above this median.")
        story.append(p(f"The median of the {eq['count']} adjusted values is <b>{money(eq['median_adjusted'])}</b> "
                       f"(unadjusted median {money(eq['unadjusted_median'])}). {verdict}"))
        n += 1

    for key, title in SET_TITLES.items():
        st = content["sets"][key]["stats"]
        if not st["count"]:
            continue
        story.append(p(f"Evidence {n}: {title} (appraised value)", h2))
        story.append(p(f"{st['count']} properties on the {e(c['cad_abbrev'])} {c['tax_year']} roll match "
                       f"{e(describe(content['sets'][key]['criteria']))}. Median appraised value "
                       f"<b>{money(st['median'])}</b>; range {money(st['low'])} to {money(st['high'])}."))
        n += 1

    owner = content["owner"]
    if owner["conditions"]:
        story.append(p("Property-specific conditions", h2))
        story += [p(f"• {e(x)}") for x in owner["conditions"]]
    if owner["repairs"]:
        story.append(p("Repair costs", h2))
        rows = [["Description", "Estimated cost"]] + [[e(r["desc"]), money(r["cost"])] for r in owner["repairs"]]
        rows.append(["<b>Total</b>", f"<b>{money(content['repair_total'])}</b>"])
        story.append(grid(rows, [4.5 * inch, 1.5 * inch], bold_rows=(len(rows) - 1,)))
        story.append(p("Copies of the estimates are attached.", small))

    story.append(p("Requested value", h2))
    base_label = ("Median adjusted value of comparable properties (Evidence 1)" if op["basis"] == "equity"
                  else "Average of the comparison-set median appraised values, rounded to $1,000")
    rows = [["Basis", "Value"], [base_label, money(op["base"])]]
    if content["repair_total"]:
        rows.append(["Less: repair costs", f"-{money(content['repair_total'])}"])
    rows.append(["<b>Requested appraised value</b>", f"<b>{money(op['requested'])}</b>"])
    story.append(grid(rows, [4.5 * inch, 1.5 * inch], bold_rows=(len(rows) - 1,)))

    story += [Spacer(1, 6),
              p(f"Based on the evidence above, I respectfully request that the Appraisal Review Board reduce the "
                f"appraised value of my property from {money(val)} to {money(op['requested'])}. Thank you for your "
                "time and consideration."),
              Spacer(1, 18), p("Respectfully submitted,"), Spacer(1, 26),
              p(f"______________________________<br/>{e(owner['name'])}<br/>{e(content['address'])}"),
              Spacer(1, 14),
              p(f"Data source: {e(c['cad_name'])}, {c['tax_year']} appraisal roll. Prepared with a free self-help "
                "tool; not legal or appraisal advice.", small)]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, leftMargin=0.7 * inch, rightMargin=0.7 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                            title=f"Property Tax Protest - {content['address']}", author=owner["name"])
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
