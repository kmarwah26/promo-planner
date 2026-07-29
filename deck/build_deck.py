"""Generate the Promo 1YP pitch deck as a real .pptx — stdlib only (no python-pptx).

A .pptx is an OOXML package (a ZIP of XML parts). This script emits a minimal but
valid 16:9 PowerPoint styled in the app's AB InBev gold-on-dark theme. Slides are
data-driven (see SLIDES): each is a list of shape dicts placed with EMU coordinates.

    python deck/build_deck.py            # writes deck/Promo1YP.pptx
"""
import os
import zipfile

# ── Geometry (EMU: 914400 per inch; 16:9 = 13.333in × 7.5in) ──
EMU = 914400
W, H = 12192000, 6858000

def IN(v):  # inches → EMU
    return int(v * EMU)

# ── Palette (matches frontend/src/index.css) ──
BG        = "17150F"
CARD      = "201D15"
CARD2     = "2B2718"
GOLD      = "E2A72E"
GOLD_DK   = "B8860B"
RED       = "C8102E"
TEXT      = "F7F2E7"
TEXT_SEC  = "B9B199"
TEXT_TER  = "857D66"
GREEN     = "4ADE80"
BORDER    = "3A3527"

# ─────────────────────────── XML helpers ───────────────────────────

def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))

def _runs(runs):
    out = []
    for r in runs:
        col = r.get("color", TEXT)
        b = ' b="1"' if r.get("bold") else ""
        i = ' i="1"' if r.get("italic") else ""
        sz = r.get("size", 18)
        spc = f' spc="{r["spc"]}"' if r.get("spc") else ""
        out.append(
            f'<a:r><a:rPr lang="en-US" sz="{int(sz*100)}"{b}{i}{spc} dirty="0">'
            f'<a:solidFill><a:srgbClr val="{col}"/></a:solidFill>'
            f'<a:latin typeface="+mn-lt"/></a:rPr>'
            f'<a:t>{esc(r["t"])}</a:t></a:r>'
        )
    return "".join(out)

def _para(p):
    algn = p.get("align", "l")
    bullet = p.get("bullet", False)
    lvl = p.get("lvl", 0)
    before = p.get("space_before", 600)
    buf = (f'<a:buChar char="{"—" if lvl else "▸"}"/>' if bullet
           else '<a:buNone/>')
    pPr = (f'<a:pPr algn="{algn}" lvl="{lvl}" marL="{IN(0.3) if bullet else 0}" '
           f'indent="{-IN(0.3) if bullet else 0}">'
           f'<a:spcBef><a:spcPts val="{before}"/></a:spcBef>'
           f'<a:buClr><a:srgbClr val="{GOLD}"/></a:buClr>'
           f'<a:buSzPct val="90000"/>{buf}</a:pPr>')
    return f'<a:p>{pPr}{_runs(p["runs"])}</a:p>'

_sid = [0]
def _nid():
    _sid[0] += 1
    return _sid[0] + 1

def shape(x, y, w, h, *, fill=None, line=None, line_w=1, paras=None,
          anchor="t", round_=False, name="sp", shadow=False):
    """A rectangle (optional fill/border) that may also hold text paragraphs."""
    geom = "roundRect" if round_ else "rect"
    fill_xml = (f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
                if fill else '<a:noFill/>')
    if line:
        ln_xml = (f'<a:ln w="{IN(line_w/72.0)}"><a:solidFill>'
                  f'<a:srgbClr val="{line}"/></a:solidFill></a:ln>')
    else:
        ln_xml = '<a:ln><a:noFill/></a:ln>'
    eff = ('<a:effectLst><a:outerShdw blurRad="90000" dist="40000" dir="5400000" '
           'rotWithShape="0"><a:srgbClr val="000000"><a:alpha val="42000"/>'
           '</a:srgbClr></a:outerShdw></a:effectLst>') if shadow else ''
    body = ""
    if paras:
        body = "".join(_para(p) for p in paras)
    tx = (f'<p:txBody><a:bodyPr wrap="square" anchor="{anchor}" '
          f'lIns="{IN(0.14)}" rIns="{IN(0.14)}" tIns="{IN(0.08)}" bIns="{IN(0.08)}">'
          f'<a:normAutofit/></a:bodyPr><a:lstStyle/>'
          f'{body if body else "<a:p><a:endParaRPr/></a:p>"}</p:txBody>')
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{_nid()}" name="{name}"/>'
        f'<p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="{geom}"><a:avLst/></a:prstGeom>'
        f'{fill_xml}{ln_xml}{eff}</p:spPr>{tx}</p:sp>'
    )

def slide_xml(shapes):
    _sid[0] = 0
    bg = shape(0, 0, W, H, fill=BG, name="bg")
    tree = bg + "".join(shapes)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:cSld><p:spTree>'
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
        '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        f'{tree}</p:spTree></p:cSld>'
        '<p:clrMapOvr><a:overrideClrMapping '
        'bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
        'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" '
        'hlink="hlink" folHlink="folHlink"/></p:clrMapOvr></p:sld>'
    )

# ─────────────────────── reusable slide furniture ───────────────────────

def header(kicker, title, subtitle=None):
    """Top gold kicker bar + title + optional subtitle. Returns shape list."""
    s = [
        shape(IN(0.7), IN(0.55), IN(0.9), IN(0.11), fill=GOLD, name="bar"),
        shape(IN(0.66), IN(0.72), IN(11.5), IN(0.5), name="kicker", paras=[
            {"runs": [{"t": kicker.upper(), "color": GOLD, "bold": True, "size": 12, "spc": 220}]}]),
        shape(IN(0.66), IN(1.05), IN(11.5), IN(1.0), name="title", paras=[
            {"runs": [{"t": title, "color": TEXT, "bold": True, "size": 32}]}]),
    ]
    if subtitle:
        s.append(shape(IN(0.66), IN(1.75), IN(11.5), IN(0.5), name="sub", paras=[
            {"runs": [{"t": subtitle, "color": TEXT_SEC, "size": 15}]}]))
    return s

def footer(n):
    return [
        shape(IN(0.66), IN(7.02), IN(6), IN(0.3), name="fl", paras=[
            {"runs": [{"t": "Promo 1YP · Wholesale Pricing Planner", "color": TEXT_TER, "size": 9}]}]),
        shape(IN(11.4), IN(7.02), IN(1.2), IN(0.3), name="fr", anchor="t", paras=[
            {"runs": [{"t": f"{n}", "color": TEXT_TER, "size": 9, "align": "r"}], "align": "r"}]),
    ]

def card(x, y, w, h, title, lines, *, accent=GOLD, big=None):
    """A titled card. `lines` = list of strings (bullets). `big` = large stat string."""
    paras = [{"runs": [{"t": title, "color": accent, "bold": True, "size": 15}]}]
    if big:
        paras.append({"runs": [{"t": big, "color": TEXT, "bold": True, "size": 30}], "space_before": 500})
    for ln in lines:
        paras.append({"runs": [{"t": ln, "color": TEXT_SEC, "size": 12.5}],
                      "bullet": True, "space_before": 460})
    return shape(x, y, w, h, fill=CARD, line=BORDER, round_=True, paras=paras,
                 anchor="t", shadow=True, name="card")

def chip(x, y, w, label, sub, *, fill=CARD2, accent=GOLD):
    return shape(x, y, w, IN(1.0), fill=fill, line=BORDER, round_=True, anchor="ctr",
                 shadow=True, name="chip", paras=[
        {"runs": [{"t": label, "color": accent, "bold": True, "size": 15}], "align": "ctr"},
        {"runs": [{"t": sub, "color": TEXT_SEC, "size": 10.5}], "align": "ctr", "space_before": 300}])

def arrow(x, y):
    return shape(x, y, IN(0.5), IN(0.5), anchor="ctr", name="arr", paras=[
        {"runs": [{"t": "→", "color": GOLD, "bold": True, "size": 24}], "align": "ctr"}])

# ─────────────────────────────── slides ───────────────────────────────

def s_title():
    return [
        shape(0, IN(2.55), W, IN(0.06), fill=GOLD, name="rule"),
        shape(IN(0.9), IN(1.5), IN(11), IN(1.0), name="t", paras=[
            {"runs": [{"t": "PROMO 1YP", "color": GOLD, "bold": True, "size": 15, "spc": 400}]}]),
        shape(IN(0.86), IN(1.95), IN(11.4), IN(1.1), name="t2", paras=[
            {"runs": [{"t": "Wholesale Pricing Planner", "color": TEXT, "bold": True, "size": 48}]}]),
        shape(IN(0.9), IN(2.75), IN(11), IN(0.7), name="t3", paras=[
            {"runs": [{"t": "Plan 52 weeks of promotional pricing across every wholesaler, "
                            "brand and pack — fast, governed, and multi-user.", "color": TEXT_SEC, "size": 17}]}]),
        chip(IN(0.9), IN(4.2), IN(2.6), "Databricks Apps", "React + FastAPI front end", accent=GOLD),
        chip(IN(3.75), IN(4.2), IN(2.6), "Lakebase", "instant edit sandbox", accent=GOLD),
        chip(IN(6.6), IN(4.2), IN(2.6), "Unity Catalog", "governed source of truth", accent=GOLD),
        chip(IN(9.45), IN(4.2), IN(2.0), "Genie-ready", "governed semantics", accent=RED),
        shape(IN(0.9), IN(6.0), IN(11), IN(0.4), name="tag", paras=[
            {"runs": [{"t": "Replacing a slow Sigma / Palantir workflow — performance first.",
                       "color": TEXT_TER, "size": 12, "italic": True}]}]),
    ]

def s_problem():
    return header("The problem", "Revenue management pricing had outgrown its tools") + [
        card(IN(0.66), IN(2.35), IN(3.7), IN(3.9), "Scale", [
            "~1.2M SKU lines (wholesaler × brand × pack)",
            "52 ISO weeks per line, promos span multiple weeks",
            "30–50 commercial directors editing concurrently"], big="1.2M"),
        card(IN(4.5), IN(2.35), IN(3.7), IN(3.9), "Pain today", [
            "Sigma row-level edits are slow & expensive",
            "Palantir is performant but siloed from DBX",
            "Slow tools push planners back to Excel"], accent=RED),
        card(IN(8.34), IN(2.35), IN(3.5), IN(3.9), "The ask", [
            "Low latency at full scale",
            "Sandbox edits → submit → CSO approval",
            "API hand-off to Pricing Hub; scale to zero",
            "Runs ~6 weeks/year (Aug–Sep planning)"], accent=GREEN),
    ] + footer(2)

def s_app():
    return header("The app", "A calendarized pricing workspace on Databricks") + [
        card(IN(0.66), IN(2.35), IN(5.6), IN(3.9), "What planners do", [
            "Edit weekly REC PPTR / discounts in a 52-week grid",
            "Filter by wholesaler (multi-select), brand, PRC group",
            "Mass-apply discounts to selected rows or the whole filter",
            "Regional coordinators review rows before submission",
            "Always-on budget bar rolls up the filtered set"]),
        card(IN(6.4), IN(2.35), IN(5.45), IN(3.9), "Why it lands", [
            "Virtualized grid stays fast over ~400K+ lines",
            "Edits are instant — written to Lakebase, not the warehouse",
            "Governed: Unity Catalog is the single source of truth",
            "Everything explainable — no black box",
            "Same team, same budget, better decisions"], accent=GREEN),
    ] + footer(3)

def s_workflow():
    y = IN(2.6)
    tabs = [("2026 Promotions Ran", "committed history"),
            ("2027 Plan Builder", "editable sandbox"),
            ("Final Plan", "CSO-approved")]
    row1 = []
    x = IN(0.9)
    for i, (t, s) in enumerate(tabs):
        row1.append(chip(x, y, IN(3.0), t, s, accent=GOLD))
        x += IN(3.0)
        if i < 2:
            row1.append(arrow(x, y + IN(0.25)))
            x += IN(0.55)
    steps = [("Edit", "Lakebase draft — instant"),
             ("Submit for Review", "draft → pending"),
             ("Final Submission", "pending → approved"),
             ("Sync to UC", "flush to governed table"),
             ("Downstream", "API → Pricing Hub")]
    y2 = IN(4.5)
    row2 = []
    x = IN(0.72)
    cw = IN(2.05)
    for i, (t, s) in enumerate(steps):
        acc = GREEN if i >= 3 else GOLD
        row2.append(chip(x, y2, cw, t, s, fill=CARD, accent=acc))
        x += cw
        if i < len(steps) - 1:
            row2.append(arrow(x - IN(0.03), y2 + IN(0.25)))
            x += IN(0.42)
    return header("Workflow", "Three plan stages, one fast edit loop") + [
        shape(IN(0.9), IN(2.25), IN(6), IN(0.35), name="l1", paras=[
            {"runs": [{"t": "TABS", "color": TEXT_TER, "bold": True, "size": 11, "spc": 200}]}]),
        shape(IN(0.72), IN(4.15), IN(6), IN(0.35), name="l2", paras=[
            {"runs": [{"t": "EDIT LIFECYCLE (all Lakebase-first)", "color": TEXT_TER, "bold": True, "size": 11, "spc": 200}]}]),
    ] + row1 + row2 + [
        shape(IN(0.72), IN(5.85), IN(11.4), IN(0.6), fill=CARD2, round_=True, name="note", anchor="ctr", paras=[
            {"runs": [{"t": "Edits, submit and approval are instant Lakebase writes. Only ",
                       "color": TEXT_SEC, "size": 12.5},
                      {"t": "Sync to UC", "color": GOLD, "size": 12.5, "bold": True},
                      {"t": " touches the warehouse — one deliberate, batched write.",
                       "color": TEXT_SEC, "size": 12.5}]}]),
    ] + footer(4)

def s_arch():
    layers = [
        ("Front end", "Databricks App", "React 19 + TypeScript + Tailwind, served by FastAPI", GOLD),
        ("Edit sandbox", "Lakebase (Postgres)", "Every edit / review / approval — instant, multi-user", GOLD),
        ("Compute", "Serverless SQL Warehouse", "Windowed grid reads + the batched Sync-to-UC write", TEXT_SEC),
        ("Source of truth", "Unity Catalog (Delta)", "Governed pricing tables + semantics + lineage", GREEN),
    ]
    shapes = header("Architecture", "One governed lakehouse, two speeds of storage")
    y = IN(2.35)
    for i, (kick, name, desc, acc) in enumerate(layers):
        shapes.append(shape(IN(0.66), y, IN(11.9), IN(0.92), fill=CARD, line=BORDER,
                            round_=True, anchor="ctr", shadow=True, name="lay", paras=[
            {"runs": [{"t": kick.upper() + "   ", "color": TEXT_TER, "bold": True, "size": 10.5, "spc": 150},
                      {"t": name, "color": acc, "bold": True, "size": 17}]},
            {"runs": [{"t": desc, "color": TEXT_SEC, "size": 12}], "space_before": 200}]))
        y += IN(1.06)
    shapes.append(shape(IN(0.66), IN(6.55), IN(11.9), IN(0.35), name="flow", paras=[
        {"runs": [{"t": "Lakeflow ingest  →  Unity Catalog (govern)  →  App reads/edits via Lakebase  →  Sync to UC  →  Genie / downstream API",
                   "color": TEXT_TER, "size": 11}]}]))
    return shapes + footer(5)

def s_apps():
    return header("Databricks Apps", "Secure, managed web apps next to your data") + [
        card(IN(0.66), IN(2.35), IN(5.8), IN(3.95), "What it is", [
            "Host full-stack web apps directly in the workspace",
            "Runs your code (FastAPI + React) on managed compute",
            "OAuth built in — users sign in with their workspace identity",
            "On-behalf-of-user or service-principal data access",
            "Scales down to zero when idle — no always-on cost"]),
        card(IN(6.6), IN(2.35), IN(5.25), IN(3.95), "Why it fits Promo 1YP", [
            "No separate app infra to provision or secure",
            "Governed access to Unity Catalog + Lakebase in-platform",
            "Ships with the data — one deploy, one permission model",
            "Idle auto-stop suits a 6-week/year planning cycle"], accent=GREEN),
    ] + footer(6)

def s_lakebase():
    return header("Lakebase", "A managed Postgres OLTP database in the lakehouse") + [
        card(IN(0.66), IN(2.35), IN(5.8), IN(3.95), "What it is", [
            "Fully-managed Postgres (transactional / OLTP)",
            "Millisecond reads & writes — built for app state",
            "Separated storage & compute; scales independently",
            "Integrated with Unity Catalog governance & identity"]),
        card(IN(6.6), IN(2.35), IN(5.25), IN(3.95), "How Promo 1YP uses it", [
            "plan_edit — in-progress edits (draft/pending/approved)",
            "plan_review — coordinator sign-off flags",
            "plan_activity + plan_sync_log — audit & sync trail",
            "uc_promo_week_mirror — fast local copy of UC rows"], accent=GREEN),
    ] + footer(7)

def s_perf():
    return header("Lakebase-first", "Instant editing, one deliberate warehouse write") + [
        chip(IN(0.9), IN(2.5), IN(3.3), "~15 ms", "Submit for Review\n(Lakebase status flip)", accent=GOLD),
        chip(IN(4.5), IN(2.5), IN(3.3), "~13 ms", "Final Submission\n(approve in Lakebase)", accent=GOLD),
        chip(IN(8.1), IN(2.5), IN(3.3), "~2.4 s", "Sync to UC\n(batched governed write)", accent=GREEN),
        shape(IN(0.66), IN(4.05), IN(11.9), IN(2.2), fill=CARD, line=BORDER, round_=True,
              anchor="t", shadow=True, name="explain", paras=[
            {"runs": [{"t": "Why it feels instant", "color": GOLD, "bold": True, "size": 15}]},
            {"runs": [{"t": "Every edit, submit and approval writes only to Lakebase — the slow warehouse round-trip is off the interactive path.",
                       "color": TEXT_SEC, "size": 13}], "bullet": True, "space_before": 520},
            {"runs": [{"t": "The governed Unity Catalog table is updated by a separate, batched “Sync to UC” step — the one warehouse write, on the user’s command.",
                       "color": TEXT_SEC, "size": 13}], "bullet": True, "space_before": 460},
            {"runs": [{"t": "Both sync directions are logged and shown live in the app, so the round-trip is visible and auditable.",
                       "color": TEXT_SEC, "size": 13}], "bullet": True, "space_before": 460},
        ]),
    ] + footer(8)

def s_summary():
    return header("Summary", "Promote with purpose — at lakehouse speed") + [
        card(IN(0.66), IN(2.35), IN(3.7), IN(3.6), "Fast", [
            "Instant edits & approvals",
            "Virtualized grid at scale",
            "Scales to zero when idle"], accent=GOLD),
        card(IN(4.5), IN(2.35), IN(3.7), IN(3.6), "Governed", [
            "Unity Catalog source of truth",
            "Full audit + sync trail",
            "CSO approval before downstream"], accent=GREEN),
        card(IN(8.34), IN(2.35), IN(3.5), IN(3.6), "In-platform", [
            "One deploy, one identity model",
            "Lakebase + UC + Apps together",
            "API hand-off to Pricing Hub"], accent=RED),
        shape(IN(0.66), IN(6.15), IN(11.9), IN(0.55), fill=GOLD, round_=True, anchor="ctr", name="cta", paras=[
            {"runs": [{"t": "Replace the slow tools — plan wholesale pricing where the data already lives.",
                       "color": "17150F", "bold": True, "size": 14}], "align": "ctr"}]),
    ] + footer(9)

SLIDES = [s_title(), s_problem(), s_app(), s_workflow(), s_arch(),
          s_apps(), s_lakebase(), s_perf(), s_summary()]

# ─────────────────────── package scaffolding (OOXML) ───────────────────────

def content_types(n):
    ov = "".join(
        f'<Override PartName="/ppt/slides/slide{i}.xml" '
        f'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        for i in range(1, n + 1))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
        '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
        f'{ov}</Types>')

ROOT_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
    '</Relationships>')

def presentation_xml(n):
    sldids = "".join(f'<p:sldId id="{255 + i}" r:id="rId{i}"/>' for i in range(1, n + 1))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" saveSubsetFonts="1">'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1000"/></p:sldMasterIdLst>'
        f'<p:sldIdLst>{sldids}</p:sldIdLst>'
        f'<p:sldSz cx="{W}" cy="{H}" type="screen16x9"/>'
        '<p:notesSz cx="6858000" cy="9144000"/></p:presentation>')

def presentation_rels(n):
    slide_rels = "".join(
        f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>'
        for i in range(1, n + 1))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{slide_rels}'
        '<Relationship Id="rId1000" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
        '<Relationship Id="rId1001" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>'
        '</Relationships>')

def _fill3():
    # fillStyleLst needs 3 entries; lnStyleLst 3; effectStyleLst 3; bgFillStyleLst 3.
    solid = '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    ln = ('<a:ln w="9525" cap="flat" cmpd="sng" algn="ctr"><a:solidFill>'
          '<a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln>')
    eff = '<a:effectStyle><a:effectLst/></a:effectStyle>'
    return (f'<a:fillStyleLst>{solid}{solid}{solid}</a:fillStyleLst>'
            f'<a:lnStyleLst>{ln}{ln}{ln}</a:lnStyleLst>'
            f'<a:effectStyleLst>{eff}{eff}{eff}</a:effectStyleLst>'
            f'<a:bgFillStyleLst>{solid}{solid}{solid}</a:bgFillStyleLst>')

def theme_xml():
    def clr(v):
        return f'<a:srgbClr val="{v}"/>'
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Promo1YP">'
        '<a:themeElements><a:clrScheme name="Promo1YP">'
        f'<a:dk1>{clr("F7F2E7")}</a:dk1><a:lt1>{clr("17150F")}</a:lt1>'
        f'<a:dk2>{clr("B9B199")}</a:dk2><a:lt2>{clr("201D15")}</a:lt2>'
        f'<a:accent1>{clr(GOLD)}</a:accent1><a:accent2>{clr(RED)}</a:accent2>'
        f'<a:accent3>{clr(GREEN)}</a:accent3><a:accent4>{clr(GOLD_DK)}</a:accent4>'
        f'<a:accent5>{clr("CBB88A")}</a:accent5><a:accent6>{clr("8A1220")}</a:accent6>'
        f'<a:hlink>{clr(GOLD)}</a:hlink><a:folHlink>{clr(GOLD_DK)}</a:folHlink></a:clrScheme>'
        '<a:fontScheme name="Promo1YP">'
        '<a:majorFont><a:latin typeface="Inter"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
        '<a:minorFont><a:latin typeface="Inter"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>'
        '</a:fontScheme>'
        f'<a:fmtScheme name="Promo1YP">{_fill3()}</a:fmtScheme>'
        '</a:themeElements></a:theme>')

SLIDE_MASTER = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
    '<p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="17150F"/></a:solidFill>'
    '<a:effectLst/></p:bgPr></p:bg>'
    '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
    '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>'
    '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
    'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
    '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst></p:sldMaster>')

SLIDE_MASTER_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>'
    '</Relationships>')

SLIDE_LAYOUT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">'
    '<p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
    '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>'
    '<p:clrMapOvr><a:overrideClrMapping bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" '
    'accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" '
    'accent6="accent6" hlink="hlink" folHlink="folHlink"/></p:clrMapOvr></p:sldLayout>')

SLIDE_LAYOUT_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>'
    '</Relationships>')

def slide_rels():
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
        '</Relationships>')

def main():
    n = len(SLIDES)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Promo1YP.pptx")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types(n))
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("ppt/presentation.xml", presentation_xml(n))
        z.writestr("ppt/_rels/presentation.xml.rels", presentation_rels(n))
        z.writestr("ppt/theme/theme1.xml", theme_xml())
        z.writestr("ppt/slideMasters/slideMaster1.xml", SLIDE_MASTER)
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", SLIDE_MASTER_RELS)
        z.writestr("ppt/slideLayouts/slideLayout1.xml", SLIDE_LAYOUT)
        z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", SLIDE_LAYOUT_RELS)
        for i, shapes in enumerate(SLIDES, start=1):
            z.writestr(f"ppt/slides/slide{i}.xml", slide_xml(shapes))
            z.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", slide_rels())
    print(f"✓ wrote {out} ({n} slides)")

if __name__ == "__main__":
    main()
