"""Bounded offline HTML/CSS PDF renderer; composition belongs to the agent."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin

BASE = "https://agentsim.invalid/"
FONTS = Path(__file__).parent / "skills/magazine-layout/fonts"


def render(title, spec, images):
    html = spec.get("html")
    if not isinstance(html, str) or not 0 < len(html.encode()) <= 100_000:
        raise ValueError("Editorial HTML requires a self-contained html string up to 100 KB.")
    payload = json.dumps(
        {
            "title": str(title)[:200],
            "html": html,
            "images": {url: str(path.resolve()) for url, path in images.items()},
        }
    )
    environment = dict(os.environ)
    if sys.platform == "darwin":
        environment["DYLD_FALLBACK_LIBRARY_PATH"] = "/opt/homebrew/lib:/usr/local/lib"
    try:
        done = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--worker"],
            input=payload.encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            timeout=45,
        )
    except subprocess.TimeoutExpired:
        raise ValueError(
            "Editorial PDF rendering exceeded 45 seconds; simplify the HTML/CSS."
        ) from None
    if done.returncode or not done.stdout.startswith(b"%PDF"):
        message = done.stderr.decode(errors="replace").split("AGENTSIM_ERROR:")[-1].strip()
        if not done.returncode:
            message = "The renderer did not return a PDF."
        raise ValueError(
            "Editorial PDF: "
            + (
                message[:400]
                if "AGENTSIM_ERROR:" in done.stderr.decode(errors="replace")
                else "Rendering failed. Check HTML/CSS and the installed WeasyPrint/Pango runtime."
            )
        )
    from pypdf import PdfReader

    if len(done.stdout) > 120_000_000 or len(PdfReader(io.BytesIO(done.stdout)).pages) > 40:
        raise ValueError("Editorial PDF exceeds 40 pages or 120 MB.")
    expected = spec.get("page_count")
    if expected is not None and (
        not isinstance(expected, int) or expected != len(PdfReader(io.BytesIO(done.stdout)).pages)
    ):
        raise ValueError(
            "Editorial PDF page count differs from page_count. Adjust the composition and render again."
        )
    return done.stdout


def _worker(payload):
    import re
    from html.parser import HTMLParser

    from weasyprint import CSS, HTML
    from weasyprint.text.fonts import FontConfiguration
    from weasyprint.urls import URLFetcher, URLFetcherResponse

    class DocumentCheck(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag in {"script", "iframe", "object", "embed", "base", "link"}:
                raise ValueError(
                    "Only self-contained HTML/CSS is allowed; no scripts, embeds or external stylesheets."
                )
            if tag == "meta" and "http-equiv" in attrs:
                raise ValueError("HTML refresh and HTTP metadata are not allowed.")
            if any(k.lower().startswith("on") for k in attrs):
                raise ValueError("HTML event handlers are not allowed.")
            if tag == "a" and attrs.get("href") and not attrs["href"].startswith("#"):
                raise ValueError("External hyperlinks are not supported in this renderer.")

    html = payload["html"]
    DocumentCheck().feed(html)
    if re.search(r"@import\b", html, re.I):
        raise ValueError("Inline all CSS. External CSS imports are not allowed.")
    resources = {urljoin(BASE, key): Path(value) for key, value in payload["images"].items()}
    resources.update(
        {
            BASE + "fonts/display.ttf": FONTS / "Display.ttf",
            BASE + "fonts/text.ttf": FONTS / "Text.ttf",
        }
    )
    denied = []

    def fetch(url, *args, **kwargs):
        path = resources.get(url)
        if path is None:
            denied.append(url)
            raise ValueError("Resource is not an authorized generated image or bundled font.")
        return URLFetcherResponse(
            url,
            path.read_bytes(),
            {
                "Content-Type": "font/ttf" if path.suffix == ".ttf" else "image/png",
            },
        )

    class OfflineFetcher(URLFetcher):
        def fetch(self, url, headers=None):
            return fetch(url)

    fetcher = OfflineFetcher()

    fonts = FontConfiguration()
    css = """@font-face {font-family: EditorialDisplay; src: url("https://agentsim.invalid/fonts/display.ttf");}
    @font-face {font-family: EditorialText; src: url("https://agentsim.invalid/fonts/text.ttf"); font-weight: 100 900;}"""
    document = HTML(string=html, base_url=BASE, url_fetcher=fetcher).render(
        stylesheets=[CSS(string=css, base_url=BASE, url_fetcher=fetcher, font_config=fonts)],
        font_config=fonts,
    )
    if denied:
        raise ValueError(
            "A resource was blocked. Use only exact PNG URLs supplied in reference_urls and the bundled EditorialDisplay/EditorialText fonts."
        )
    if not 1 <= len(document.pages) <= 40:
        raise ValueError("Compose between 1 and 40 pages.")
    # PDF metadata belongs to this generated document, not source page scripts.
    document.metadata.title = payload["title"]
    document.metadata.authors = ["WABIX AgentSim"]
    return document.write_pdf()


if __name__ == "__main__":
    try:
        if sys.platform != "win32":
            import resource

            resource.setrlimit(resource.RLIMIT_CPU, (35, 35))
        sys.stdout.buffer.write(_worker(json.loads(sys.stdin.buffer.read(800_000))))
    except Exception as exc:
        print("AGENTSIM_ERROR:" + str(exc)[:400], file=sys.stderr)
        raise SystemExit(1)
