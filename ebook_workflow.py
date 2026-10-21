"""Visible, per-request budget for multi-chapter illustrated book workflows."""

import re


def plan(goal):
    if not re.search(r"\b(e-?book|livro|cap[ií]tulos?|chapters?)\b", goal, re.I) or not re.search(
        r"\b(ilustr\w*|illustr\w*|capa|cover)\b", goal, re.I
    ):
        return None
    count = re.search(r"(\d{1,2})\s*(?:cap[ií]tulos?|chapters?)", goal, re.I)
    chapters = int(count[1]) if count else 5
    return {
        "chapters": chapters,
        "illustrations": chapters + 1,
        "maxExecutionSeconds": min(3600, (chapters + 1) * 120 + 180),
        "maxIterations": min(60, (chapters + 1) * 2 + 8),
    }


def instructions(goal):
    workflow = plan(goal)
    if not workflow:
        return ""
    return (
        f"\nIllustrated ebook workflow: write {workflow['chapters']} complete chapters about the user's subject. "
        "Use image_generator to produce a cover and an actual illustration for EACH chapter, with distinct scene prompts. "
        "Use previous generated images as reference_urls to preserve characters and style when relevant. "
        "If a suitable illustration already exists and the user asks to reuse it, reuse its real URL. "
        "Then call pdf_generator with JSON {cover:{image_url:URL,subtitle:TEXT},chapters:[{title:CHAPTER_TITLE,text:FULL_CHAPTER,image_url:URL}]}. "
        "Do not return just an outline, prompts or links: the final result must be a real illustrated PDF with cover. "
        "Keep all generated images and documents in the conversation history. If a required tool is not granted, explain which permission is missing.\n"
    )
