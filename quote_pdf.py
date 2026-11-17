"""One-page quote publication using editable editorial Brain palette values."""

import re
from html import escape
from pathlib import Path

import editorial_html

ROLES = ("Primary", "Secondary", "Ink", "Tint", "Border", "Paper")


def palette(markdown):
    heading = re.search(r"^## Palette[ \t]*\n(.*?)(?=^#|\Z)", markdown, re.M | re.S)
    if not heading:
        return None
    colors = dict(re.findall(r"^\|\s*(\w+)\s*\|\s*(#[0-9A-Fa-f]{6})\s*\|", heading[1], re.M))
    if set(colors) != set(ROLES):
        raise ValueError("The Palette table needs Primary, Secondary, Ink, Tint, Border and Paper hex colors.")
    return colors


def render(result, editorial, image=None):
    colors = palette(editorial["markdown"])
    if colors is None:
        raise ValueError("The editorial Brain needs a Palette table.")
    primary, secondary, ink, tint, border, paper = (colors[role] for role in ROLES)
    q = {key: escape(str(value)) for key, value in result.items()}
    logo = "/branding/wabix-logo.png"
    images = {logo: Path(__file__).parent / "static" / "wabix-logo.png"}
    image_markup = ""
    if image:
        item, path = image
        url = item["url"]
        images[url] = path
        image_markup = f'<img class="vehicle-image" src="{escape(url, quote=True)}" alt="Vehicle illustration">'
    title = "Motor Insurance Coach"
    html = f"""<!doctype html><html lang="en"><meta charset="utf-8">
    <style>
      @page {{size: A4; margin: 0;}}
      * {{box-sizing: border-box;}}
      body {{margin: 0; color: {ink}; background: {paper}; font: 11pt EditorialText, sans-serif;}}
      .brand {{display:flex; align-items:center; height: 24mm; gap: 3mm; padding: 0 17mm; color: {primary};}}
      .brand img {{width: 27mm; height: 27mm; object-fit: contain; margin-left: -5mm;}}
      header {{background: {primary}; color: white; padding: 9mm 17mm 11mm;}}
      .wordmark {{font-size: 12pt; font-weight: 700; letter-spacing: .08em;}}
      h1 {{font: 33pt EditorialDisplay, serif; margin: 0 0 2mm;}}
      header p {{font-size: 10pt; margin: 0;}}
      main {{padding: 12mm 17mm;}}
      .meta {{display: grid; grid-template-columns: 2fr 1fr; gap: 5mm;}}
      .meta div {{padding-bottom: 4mm; border-bottom: 1px solid {border}; overflow-wrap: anywhere;}}
      dt {{font-size: 8pt; font-weight: 700; letter-spacing: .09em; text-transform: uppercase;}}
      dd {{margin: 1.2mm 0 0; font-size: 16pt; font-weight: 700;}}
      .premium {{margin: 10mm 0 7mm; background: {tint}; padding: 5mm 7mm; border-left: 3mm solid {secondary}; color: {primary};}}
      .premium strong {{display: block; font: 33pt EditorialDisplay, serif; margin-top: 1mm;}}
      h2 {{font: 19pt EditorialDisplay, serif; color: {primary}; margin: 0 0 2mm;}}
      table {{border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums;}}
      th, td {{border-bottom: 1px solid {border}; padding: 2.75mm 0;}}
      th {{text-align: left; font-weight: 400;}} td {{text-align: right;}}
      .vehicle-image {{display:block; margin: 5mm 0 0; width: 100%; height: 46mm; object-fit: contain;}}
      footer {{position: fixed; bottom: 11mm; left: 17mm; right: 17mm; border-top: 1px solid {border}; padding-top: 3mm; font-size: 9pt;}}
      footer p {{margin: 0 0 1.4mm;}}
    </style>
    <div class="brand"><img src="{logo}" alt="WABIX"><div class="wordmark">WABIX AGENT SIM</div></div>
    <header><h1>{title}</h1><p>Fictional training example · Comprehensive cover</p></header>
    <main>
      <dl class="meta"><div><dt>Vehicle</dt><dd>{q['vehicle']}</dd></div><div><dt>Partner</dt><dd>{q['partner']}</dd></div></dl>
      <section class="premium">Final annual premium<strong>€{q['total']}</strong></section>
      <h2>Premium breakdown</h2>
      <table>
        <tr><th>Annual base premium</th><td>€{q['base']}</td></tr>
        <tr><th>Partner discount ({q['discount']}%)</th><td>−€{q['discountAmount']}</td></tr>
        <tr><th><b>Final annual premium</b></th><td><b>€{q['total']}</b></td></tr>
      </table>{image_markup}
    </main>
    <footer><p>Pricing revision {q['revision']} · Editorial revision {editorial['revision']}</p>
    <p>Illustrative calculation for an internal demonstration.</p></footer>
    </html>"""
    return editorial_html.render(title, {"html": html, "page_count": 1}, images)
