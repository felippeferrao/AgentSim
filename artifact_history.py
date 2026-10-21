"""Read and reuse only generated files owned by this persisted conversation."""

import json
import re

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

import auth


def artifact_path(item):
    match = re.fullmatch(
        r"/artifacts/([A-Za-z0-9-]+)/([a-f0-9]{32}\.(pdf|png|svg|html))", item.get("url", "")
    )
    if not match:
        raise ValueError("Invalid generated file reference.")
    root = auth.LOCAL / "artifacts"
    path = root / match[1] / match[2]
    if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
        raise ValueError("This generated file is no longer available locally.")
    size_limit = 120_000_000 if match[3] == "pdf" else 30_000_000
    if not path.resolve().is_relative_to(root.resolve()) or path.stat().st_size > size_limit:
        raise ValueError("Generated file is outside the local store or exceeds the size limit.")
    return path


def resolve_reference(config, url):
    item = next((a for a in config.get("conversationArtifacts", []) if a.get("url") == url), None)
    if not item:
        raise ValueError("Choose a generated file from this conversation's history.")
    return item, artifact_path(item)


def reuse_event(emit, actor, items, purpose):
    emit(
        "artifact_reused",
        {
            "agentId": actor["id"],
            "agent": actor["name"],
            "references": [{"title": a["title"], "url": a["url"]} for a in items],
            "implementation": "artifact_history.resolve_reference",
            "where": "Local conversation artifact store → " + purpose,
            "explanation": "Previously generated files were selected as actual inputs for this step.",
        },
    )


class ReadArgs(BaseModel):
    url: str = Field(
        description="Exact generated file URL from this conversation's artifact history."
    )


class ArtifactReader(BaseTool):
    name: str = "read_generated_file"
    description: str = "Read a prior generated PDF's text or a chart's original Plotly data before creating a follow-up. When source is available, it contains original generator arguments: reuse source.request and source.reference_urls unchanged to recompile a PDF while preserving the exact narrative. Images can be used directly by image_generator or pdf_generator with reference_urls."
    args_schema: type[BaseModel] = ReadArgs
    config: dict = Field(exclude=True)
    actor: dict = Field(exclude=True)
    event_sink: object = Field(exclude=True)

    def _run(self, url):
        from pypdf import PdfReader

        item, path = resolve_reference(self.config, url)
        reuse_event(self.event_sink, self.actor, [item], "read_generated_file")
        source_data = None
        source = path.with_suffix(".source.json")
        if source.is_file():
            if (
                source.is_symlink()
                or source.resolve().parent != path.resolve().parent
                or source.stat().st_size > 1_000_000
            ):
                raise ValueError("Invalid stored generator source.")
            raw = source.read_text()
            if len(raw) <= 40000:
                source_data = json.loads(raw)
        inspection = {}
        if item["extension"] == "pdf":
            document = PdfReader(path)
            text = "\n".join(page.extract_text() or "" for page in document.pages)
            inspection = {
                "pages": len(document.pages),
                "embeddedImages": sum(len(page.images) for page in document.pages),
            }
        elif item["extension"] == "png":
            import hashlib

            from PIL import Image

            with Image.open(path) as image:
                inspection = {
                    "width": image.width,
                    "height": image.height,
                    "sha256": hashlib.sha256(image.convert("RGB").tobytes()).hexdigest(),
                }
            text = "Verified local PNG dimensions and pixel fingerprint. The source contains the recorded generation prompt when available. This metadata check is not a visual inspection of image contents."
        elif path.with_suffix(".source.json").is_file():
            source = path.with_suffix(".source.json")
            if (
                source.is_symlink()
                or source.resolve().parent != path.resolve().parent
                or source.stat().st_size > 1_000_000
            ):
                raise ValueError("Invalid stored chart source.")
            text = source.read_text()
        elif item["extension"] == "png":
            text = "Image available: pass this URL in reference_urls to image_generator to create a variation or pdf_generator to embed it."
        else:
            text = "Generated file available to open/download; original structured source was not saved for this older output."
        return json.dumps(
            {
                "title": item["title"],
                "url": url,
                "content": text[:40000],
                "source": source_data,
                "inspection": inspection,
                "truncated": len(text) > 40000,
            }
        )
