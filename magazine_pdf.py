"""Declarative, offline magazine layout inspired by MiniMax's MIT PDF design skill."""

import io
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BalancedColumns,
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


def render(title, spec, images):
    """Use only conversation-resolved image paths, escaped text and bounded design tokens."""
    sections = spec.get("chapters", spec.get("pages"))
    if not isinstance(sections, list) or not 1 <= len(sections) <= 40:
        raise ValueError("Magazine layout requires 1–40 chapters or pages.")
    if any(not isinstance(s, dict) for s in sections):
        raise ValueError("Magazine sections must be objects.")
    cover = spec.get("cover") or {}
    if not isinstance(cover, dict):
        raise ValueError("Magazine cover must be an object.")
    design = spec.get("design") or {}
    if not isinstance(design, dict):
        raise ValueError("Magazine design must be an object.")
    accent = str(design.get("accent", "#1C3557"))
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        raise ValueError("Magazine accent must be a six-digit hexadecimal color.")
    accent = colors.HexColor(accent)
    ink, muted, paper = (colors.HexColor(c) for c in ["#0D1A2B", "#62666A", "#F2F0EC"])
    width, height = A4
    margin = 56
    available = width - 2 * margin
    styles = {
        "cover": ParagraphStyle(
            "MagazineCover",
            fontName="Times-Bold",
            fontSize=40,
            leading=43,
            textColor=ink,
            alignment=TA_CENTER,
            spaceAfter=18,
        ),
        "title": ParagraphStyle(
            "MagazineTitle",
            fontName="Times-Bold",
            fontSize=29,
            leading=33,
            textColor=ink,
            spaceAfter=14,
        ),
        "subtitle": ParagraphStyle(
            "MagazineSubtitle",
            fontName="Times-Italic",
            fontSize=16,
            leading=21,
            textColor=muted,
            alignment=TA_CENTER,
            spaceAfter=14,
        ),
        "body": ParagraphStyle(
            "MagazineBody",
            fontName="Helvetica",
            fontSize=10.5,
            leading=15.5,
            textColor=ink,
            alignment=TA_LEFT,
            spaceAfter=10,
            allowWidows=0,
            allowOrphans=0,
        ),
        "label": ParagraphStyle(
            "MagazineLabel",
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=12,
            textColor=accent,
            spaceAfter=12,
        ),
        "caption": ParagraphStyle(
            "MagazineCaption",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=muted,
            spaceAfter=12,
        ),
        "quote": ParagraphStyle(
            "MagazineQuote",
            fontName="Times-Italic",
            fontSize=18,
            leading=23,
            textColor=accent,
            spaceBefore=10,
            spaceAfter=15,
        ),
    }

    def paragraph(text, style):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), styles[style])

    def picture(url, max_width, max_height):
        if url not in images:
            raise ValueError("Magazine images must be generated PNGs from this conversation.")
        from PIL import Image as PillowImage

        with PillowImage.open(images[url]) as source:
            w, h = source.size
        scale = min(max_width / w, max_height / h)
        return Image(str(images[url]), width=w * scale, height=h * scale, hAlign="CENTER")

    publication = str(spec.get("publication") or "WABIX AgentSim")[:100]
    issue = str(spec.get("issue") or "EDITORIAL EDITION")[:80]
    story = [
        Spacer(1, 25),
        paragraph(publication.upper(), "label"),
        HRFlowable(width="100%", thickness=1.5, color=accent),
        Spacer(1, 28),
        paragraph(title, "cover"),
    ]
    if cover.get("subtitle"):
        story.append(paragraph(cover["subtitle"], "subtitle"))
    if cover.get("image_url"):
        story.extend([picture(cover["image_url"], available, 365), Spacer(1, 14)])
    if cover.get("abstract"):
        story.append(paragraph(cover["abstract"], "body"))
    story.extend([Spacer(1, 12), paragraph(issue.upper(), "label")])
    for index, section in enumerate(sections):
        story.extend(
            [
                PageBreak(),
                paragraph(f"{index + 1:02d} / {publication.upper()}", "label"),
                paragraph(section.get("title") or f"Feature {index + 1}", "title"),
            ]
        )
        if section.get("standfirst"):
            story.append(paragraph(section["standfirst"], "subtitle"))
        if section.get("image_url"):
            story.extend([picture(section["image_url"], available, 230), Spacer(1, 9)])
            if section.get("caption"):
                story.append(paragraph(section["caption"], "caption"))
        body = []
        if section.get("pull_quote"):
            body.append(paragraph(section["pull_quote"], "quote"))
        for text in str(section.get("text", "")).split("\n\n"):
            if text.strip():
                body.append(paragraph(text, "body"))
        if body:
            story.append(BalancedColumns(body, nCols=2, innerPadding=12, needed=80))

    def decoration(canvas, document):
        canvas.saveState()
        canvas.setFillColor(paper if document.page == 1 else colors.white)
        canvas.rect(0, 0, width, height, fill=1, stroke=0)
        canvas.setFillColor(accent)
        canvas.rect(0, height - 7, width, 7, fill=1, stroke=0)
        canvas.setStrokeColor(accent)
        canvas.setLineWidth(0.5)
        canvas.line(margin, 38, width - margin, 38)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(muted)
        canvas.drawString(margin, 25, publication[:70])
        canvas.drawRightString(width - margin, 25, f"{document.page:02d}")
        canvas.restoreState()

    result = io.BytesIO()
    SimpleDocTemplate(
        result,
        pagesize=A4,
        title=title,
        author="WABIX AgentSim",
        leftMargin=margin,
        rightMargin=margin,
        topMargin=50,
        bottomMargin=55,
    ).build(story, onFirstPage=decoration, onLaterPages=decoration)
    return result.getvalue()
