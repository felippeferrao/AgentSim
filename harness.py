"""Built-in integration harness: allowlisted tools, artifacts and public provenance."""

import base64
import io
import json
import re
import uuid
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

from crewai.tools import BaseTool
from openai import OpenAI
from pydantic import BaseModel, Field

import auth
from artifact_history import resolve_reference, reuse_event
from native_images import ChatGPTImageRuntime

CATALOG = [
    {"id": "calculator", "name": "Calculator", "description": "Calculate numbers with + - * /."},
    {
        "id": "web-research",
        "name": "Web Research",
        "description": "Search the web through the agent's connected Responses model and return cited sources.",
    },
    {
        "id": "pdf-generator",
        "name": "PDF Generator",
        "description": "Create a real PDF with ReportLab. For illustrated stories/comics, request JSON {pages:[{text: caption, image_url: generated_PNG_URL}]}. For ebooks use {cover:{image_url:URL,subtitle:TEXT},chapters:[{title:TITLE,text:FULL_CHAPTER,image_url:URL}]}. Reuse prior images or generate scenes first; reference_urls embeds images with plain text too.",
    },
    {
        "id": "image-generator",
        "name": "Image Generator",
        "description": "Generate PNG images with ChatGPT's native image runtime. Pass reference_urls from conversation history to reuse a character/style in a new scene. Results can be embedded by pdf_generator.",
    },
    {
        "id": "chart-generator",
        "name": "Chart Generator · Plotly",
        "description": "Create interactive Plotly charts plus high-resolution PNG and vector SVG. Bar, line, area, pie, heatmap, Sankey, treemap, 3D and more.",
    },
]


def artifact_root():
    return auth.LOCAL / "artifacts"


class ArtifactStore:
    def __init__(self, run_id, actor, emit):
        self.run_id, self.actor, self.emit = run_id, actor, emit

    def write(self, title, extension, data, metadata=None):
        ident = uuid.uuid4().hex
        folder = artifact_root() / self.run_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (ident + "." + extension)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())
        item = {
            "id": ident,
            "runId": self.run_id,
            "title": title[:160],
            "extension": extension,
            "url": f"/artifacts/{self.run_id}/{path.name}",
            "bytes": path.stat().st_size,
            "agentId": self.actor["id"],
            "agent": self.actor["name"],
            **(metadata or {}),
        }
        self.emit(
            "artifact_created",
            {
                **item,
                "implementation": "harness.ArtifactStore",
                "where": "Local artifact store",
                "explanation": "A real output file was created and is available to preview or download.",
            },
        )
        return item


class PDFGenerator:
    @staticmethod
    def render(title, content, images=None):
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer

        buffer = io.BytesIO()
        styles = getSampleStyleSheet()
        styles["Title"].textColor = colors.HexColor("#152653")
        styles["BodyText"].leading = 16
        styles["BodyText"].alignment = TA_LEFT
        story = [Paragraph(escape(title), styles["Title"]), Spacer(1, 0.5 * cm)]
        images = images or {}
        pages = None
        cover = None
        if content.lstrip().startswith("{"):
            try:
                spec = json.loads(content)
                pages = spec.get("chapters", spec.get("pages")) if isinstance(spec, dict) else None
                cover = spec.get("cover") if isinstance(spec, dict) else None
            except ValueError:
                pass
        if pages is not None and (
            not isinstance(pages, list)
            or not 1 <= len(pages) <= 40
            or any(not isinstance(p, dict) for p in pages)
        ):
            raise ValueError("Illustrated PDF needs 1–40 page objects with text and image_url.")

        def illustration(url):
            if url not in images:
                raise ValueError(
                    "PDF illustration must reference a generated PNG from this conversation."
                )
            from PIL import Image as PillowImage

            with PillowImage.open(images[url]) as source:
                width, height = source.size
            scale = min(17 * cm / width, 16 * cm / height)
            story.extend(
                [
                    Image(str(images[url]), width=width * scale, height=height * scale),
                    Spacer(1, 0.3 * cm),
                ]
            )

        if cover is not None:
            if not isinstance(cover, dict) or pages is None:
                raise ValueError("An ebook cover requires a chapters or pages list.")
            if cover.get("image_url"):
                illustration(cover["image_url"])
            if cover.get("subtitle"):
                story.extend(
                    [
                        Paragraph(escape(str(cover["subtitle"])), styles["Heading2"]),
                        Spacer(1, 0.5 * cm),
                    ]
                )
            story.append(PageBreak())
        for index, page in enumerate(pages or [{"text": content}]):
            if index:
                story.append(PageBreak())
            if page.get("title"):
                story.extend(
                    [Paragraph(escape(str(page["title"])), styles["Heading1"]), Spacer(1, 0.3 * cm)]
                )
            if page.get("image_url"):
                illustration(page["image_url"])
            for paragraph in str(page.get("text", "")).split("\n\n"):
                story.extend(
                    [
                        Paragraph(escape(paragraph).replace("\n", "<br/>"), styles["BodyText"]),
                        Spacer(1, 0.3 * cm),
                    ]
                )
        if pages is None:
            for url in images:
                story.append(PageBreak())
                illustration(url)

        def footer(canvas, document):
            canvas.setFont("Helvetica", 9)
            canvas.setFillColor(colors.HexColor("#657493"))
            canvas.drawString(2 * cm, 1.2 * cm, "WABIX AgentSim")
            canvas.drawRightString(19 * cm, 1.2 * cm, str(document.page))

        SimpleDocTemplate(
            buffer,
            title=title,
            author="WABIX AgentSim",
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        ).build(story, onFirstPage=footer, onLaterPages=footer)
        return buffer.getvalue()


class ChartGenerator:
    @staticmethod
    def render(spec):
        import plotly.graph_objects as go
        import plotly.io as pio

        if (
            not isinstance(spec, dict)
            or len(json.dumps(spec)) > 500_000
            or not isinstance(spec.get("data"), list)
            or len(spec["data"]) > 40
        ):
            raise ValueError("Provide a Plotly figure object with data (up to 40 traces / 500 KB).")

        # No external image resources/Mapbox URLs; declarative chart data only.
        def check(value):
            if isinstance(value, str) and re.search(r"https?://|javascript:|<script", value, re.I):
                raise ValueError("Charts must contain local data, not remote URLs or scripts.")
            if isinstance(value, dict):
                for child in value.values():
                    check(child)
            if isinstance(value, list):
                for child in value:
                    check(child)

        check(spec)
        fig = go.Figure(spec, skip_invalid=False)
        fig.update_layout(
            template="plotly_white",
            font={"family": "Arial", "size": 16},
            colorway=["#08a49e", "#1873f4", "#ff872d", "#8b79fa", "#d63b55"],
            paper_bgcolor="white",
            margin={"l": 80, "r": 50, "t": 80, "b": 75},
        )
        html = pio.to_html(
            fig,
            full_html=True,
            include_plotlyjs=True,
            config={"responsive": True, "displaylogo": False},
        )
        return (
            html,
            fig.to_image(format="png", width=1600, height=1000, scale=2),
            fig.to_image(format="svg", width=1600, height=1000),
        )


class ProviderTools:
    def __init__(self, llm, emit, actor):
        self.llm, self.emit, self.actor = llm, emit, actor

    def request(self, prompt, tool_type):
        conf = self.llm.config
        key = auth.access() if conf["provider"] == "chatgpt" else conf.get("api_key")
        base = "https://api.openai.com/v1" if conf["provider"] == "chatgpt" else conf["base_url"]
        client = OpenAI(api_key=key, base_url=base, max_retries=0, timeout=180)
        self.emit(
            "provider_tool_started",
            {
                "agentId": self.actor["id"],
                "model": self.llm.model,
                "name": tool_type,
                "implementation": "harness.ProviderTools",
                "where": urlsplit(base).netloc,
                "explanation": "The selected agent model was asked to use its provider-hosted tool.",
            },
        )
        result = None
        completed_items = {}
        try:
            with client.responses.create(
                model=self.llm.model,
                input=[{"role": "user", "content": prompt}],
                tools=[{"type": tool_type}],
                tool_choice="required",
                store=False,
                stream=True,
            ) as stream:
                for event in stream:
                    if event.type == "response.output_item.done":
                        completed_items[event.output_index] = event.item
                    elif event.type == "response.completed":
                        result = event.response
                    elif event.type in ("response.failed", "response.incomplete", "error"):
                        error = getattr(getattr(event, "response", None), "error", None)
                        raise ValueError(
                            getattr(error, "code", None)
                            or "Provider stream did not complete the tool request."
                        )
                    elif (
                        event.type.startswith(
                            ("response.web_search_call.", "response.image_generation_call.")
                        )
                        and "partial_image" not in event.type
                    ):
                        self.emit(
                            "provider_activity",
                            {
                                "agentId": self.actor["id"],
                                "name": event.type,
                                "implementation": "harness.ProviderTools",
                                "where": urlsplit(base).netloc,
                                "explanation": "The provider reported this hosted-tool activity.",
                            },
                        )
        except Exception as exc:
            body = getattr(exc, "body", {})
            error = body.get("error", body) if isinstance(body, dict) else {}
            detail = error.get("message", "") if isinstance(error, dict) else ""
            if isinstance(exc, ValueError):
                detail = str(exc)
            detail = str(detail).replace(key or "no-key-value", "[credential removed]")[:500]
            status = getattr(exc, "status_code", None)
            raise ValueError(
                f"{tool_type} failed with the selected model"
                + (f" (HTTP {status})" if status else "")
                + ". "
                + (detail or "Check provider tool support, account permissions and usage limits.")
            ) from None
        if result is None or result.status != "completed":
            raise ValueError("The provider tool stream ended without a completed response.")
        if completed_items and not getattr(result, "output", None):
            result = result.model_copy(
                update={"output": [completed_items[i] for i in sorted(completed_items)]}
            )
        usage = result.usage
        record = {
            "step": self.llm.current,
            "input": usage.input_tokens if usage else None,
            "output": usage.output_tokens if usage else None,
        }
        self.llm.usage.append(record)
        self.emit("usage", record)
        return result


class IntegrationArgs(BaseModel):
    request: str = Field(
        description="For web-research: search query. For image-generator: image prompt. For PDF: report body text. For chart: a JSON string containing a Plotly figure object with data and layout."
    )
    title: str = Field(default="Agent result", description="Output title")
    reference_urls: list[str] = Field(
        default_factory=list,
        max_length=12,
        description="Exact prior generated PNG URLs to reuse. Image: visual references for a new variation. PDF: embed illustrations; request can be JSON {pages:[{text: caption, image_url: URL}]} for an illustrated comic. Other tools: leave empty.",
    )


class IntegrationTool(BaseTool):
    args_schema: type[BaseModel] = IntegrationArgs
    tool_id: str
    actor: dict = Field(exclude=True)
    llm_adapter: object = Field(exclude=True)
    event_sink: object = Field(exclude=True)
    run_id: str

    def _run(self, request, title="Agent result", reference_urls=None):
        if not isinstance(request, str) or not 0 < len(request) <= 100_000:
            raise ValueError("Tool request must contain 1-100000 characters.")
        where = (
            "Provider via selected agent model"
            if self.tool_id in ("web-research", "image-generator")
            else "Local Python harness"
        )
        implementation = {
            "pdf-generator": "harness.PDFGenerator",
            "chart-generator": "harness.ChartGenerator",
            "web-research": "harness.ProviderTools",
            "image-generator": "harness.ProviderTools",
        }[self.tool_id]
        native_images = (
            self.tool_id == "image-generator"
            and self.llm_adapter.config["provider"] == "chatgpt"
            and ChatGPTImageRuntime.settings()["configured"]
        )
        if native_images:
            implementation = "native_images.ChatGPTImageRuntime"
            where = "Local Codex CLI → ChatGPT native image service"
        elif self.tool_id == "image-generator" and ImageProvider.settings()["configured"]:
            implementation = "harness.ImageProvider"
            where = "Image provider: " + urlsplit(ImageProvider.settings()["base_url"]).netloc
        metadata = {
            "agentId": self.actor["id"],
            "agent": self.actor["name"],
            "name": self.tool_id,
            "implementation": implementation,
            "where": where,
        }
        self.event_sink(
            "tool_started",
            {
                **metadata,
                "input": request,
                "explanation": "The agent explicitly called this assigned integration.",
            },
        )
        store = ArtifactStore(self.run_id, self.actor, self.event_sink)
        try:
            urls = list(reference_urls or [])
            if self.tool_id == "pdf-generator" and request.lstrip().startswith("{"):
                try:
                    spec = json.loads(request)
                    if isinstance(spec, dict) and isinstance(
                        spec.get("chapters", spec.get("pages")), list
                    ):
                        if isinstance(spec.get("cover"), dict) and spec["cover"].get("image_url"):
                            urls.append(spec["cover"]["image_url"])
                        urls.extend(
                            p["image_url"]
                            for p in spec.get("chapters", spec.get("pages"))
                            if isinstance(p, dict) and p.get("image_url")
                        )
                except ValueError:
                    pass
            urls = list(dict.fromkeys(urls))
            if len(urls) > 40:
                raise ValueError("Use at most 40 generated illustrations per document.")
            references = [resolve_reference(self.llm_adapter.config, url) for url in urls]
            if any(item["extension"] != "png" for item, path in references):
                raise ValueError(
                    "Image references and PDF illustrations must be generated PNG files."
                )
            if references:
                if self.tool_id not in ("image-generator", "pdf-generator"):
                    raise ValueError("This integration does not accept image references.")
                if self.tool_id == "image-generator" and not native_images:
                    raise ValueError("Image references require the native ChatGPT image session.")
                reuse_event(
                    self.event_sink, self.actor, [item for item, _ in references], self.tool_id
                )
            image_paths = {item["url"]: path for item, path in references}
            if self.tool_id == "pdf-generator":
                try:
                    document = json.loads(request)
                except ValueError:
                    document = {}
                if not isinstance(document, dict):
                    document = {}
                chapters = document.get("chapters", [])
                structure = {
                    "hasCover": isinstance(document.get("cover"), dict),
                    "coverIllustrated": bool((document.get("cover") or {}).get("image_url"))
                    if isinstance(document.get("cover"), dict)
                    else False,
                    "chapterCount": len(chapters) if isinstance(chapters, list) else 0,
                    "illustratedChapters": sum(
                        bool(c.get("image_url")) for c in chapters if isinstance(c, dict)
                    )
                    if isinstance(chapters, list)
                    else 0,
                }
                result = {
                    "artifacts": [
                        store.write(
                            title,
                            "pdf",
                            PDFGenerator.render(title, request, image_paths),
                            {"document": structure},
                        )
                    ]
                }
            elif self.tool_id == "chart-generator":
                html, png, svg = ChartGenerator.render(json.loads(request))
                result = {
                    "artifacts": [
                        store.write(title, "html", html),
                        store.write(title, "png", png),
                        store.write(title, "svg", svg),
                    ]
                }
            elif native_images:
                images = ChatGPTImageRuntime.generate(
                    request,
                    self.llm_adapter,
                    self.event_sink,
                    self.actor,
                    list(image_paths.values()),
                )
                result = {"artifacts": [store.write(title, "png", data) for data in images]}
            elif self.tool_id == "image-generator" and ImageProvider.settings()["configured"]:
                images = ImageProvider.generate(
                    request, self.llm_adapter, self.event_sink, self.actor
                )
                result = {"artifacts": [store.write(title, "png", data) for data in images]}
            elif (
                self.tool_id == "image-generator"
                and self.llm_adapter.config["provider"] == "chatgpt"
            ):
                raise ValueError(
                    "Connect the native ChatGPT image session in Tools → Image Generator. No API key is required."
                )
            else:
                response = ProviderTools(self.llm_adapter, self.event_sink, self.actor).request(
                    request, "web_search" if self.tool_id == "web-research" else "image_generation"
                )
                data = response.model_dump()
                if self.tool_id == "web-research":
                    sources = []
                    for output in data.get("output", []):
                        for content in output.get("content", []):
                            for annotation in content.get("annotations", []):
                                if annotation.get("type") == "url_citation":
                                    sources.append(
                                        {
                                            "title": annotation.get("title", "Source"),
                                            "url": annotation.get("url", ""),
                                        }
                                    )
                    if not any(o.get("type") == "web_search_call" for o in data.get("output", [])):
                        raise ValueError("The provider returned no actual web search call.")
                    result = {"text": response.output_text, "sources": sources}
                else:
                    images = [
                        o
                        for o in data.get("output", [])
                        if o.get("type") == "image_generation_call" and o.get("result")
                    ]
                    if not images:
                        raise ValueError("The provider returned no generated image.")
                    result = {
                        "artifacts": [
                            store.write(title, "png", base64.b64decode(o["result"], validate=True))
                            for o in images
                        ]
                    }
        except Exception as exc:
            message = (
                str(exc)
                if isinstance(exc, ValueError)
                else "Integration failed. Check the request and available runtime dependencies."
            )
            self.event_sink(
                "tool_failed",
                {
                    **metadata,
                    "error": message,
                    "explanation": "No success result was substituted for this failed tool.",
                },
            )
            raise ValueError(message) from None
        for item in result.get("artifacts", []):
            self.llm_adapter.config.setdefault("conversationArtifacts", []).append(item)
            if self.tool_id in ("pdf-generator", "chart-generator"):
                from artifact_history import artifact_path

                artifact_path(item).with_suffix(".source.json").write_text(
                    json.dumps({"request": request, "reference_urls": urls}, ensure_ascii=False)
                )
        if self.tool_id == "image-generator":
            if not hasattr(self.llm_adapter, "generated_images"):
                self.llm_adapter.generated_images = []
            self.llm_adapter.generated_images.extend(result["artifacts"])
        self.event_sink(
            "tool_completed",
            {
                **metadata,
                "output": result,
                "explanation": "The integration completed and its actual output was returned to the agent.",
            },
        )
        return json.dumps(result, ensure_ascii=False)


def integration_tools(actor, llm, emit, run_id):
    return [
        IntegrationTool(
            name=c["id"].replace("-", "_"),
            description=c["description"],
            tool_id=c["id"],
            actor=actor,
            llm_adapter=llm,
            event_sink=emit,
            run_id=run_id,
        )
        for c in CATALOG
        if c["id"] in actor["tools"] and c["id"] != "calculator"
    ]


class ImageProvider:
    """Optional image-model account when ChatGPT plan tools cannot generate images."""

    @staticmethod
    def settings():
        conf = auth.load("image-provider")
        return {
            "configured": bool(conf.get("api_key")),
            "base_url": conf.get("base_url", "https://api.openai.com/v1"),
            "model": conf.get("model", ""),
        }

    @staticmethod
    def models(base, key):
        import httpx

        parsed = urlsplit(base)
        if (
            parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not parsed.hostname
            or not (
                parsed.scheme == "https"
                or parsed.scheme == "http"
                and parsed.hostname in ("127.0.0.1", "localhost")
            )
        ):
            raise ValueError("Use a clean HTTPS provider URL, or local loopback HTTP.")
        try:
            response = httpx.get(
                base.rstrip("/") + "/models",
                headers={"Authorization": "Bearer " + key},
                timeout=20,
                follow_redirects=False,
            )
            response.raise_for_status()
            models = response.json().get("data", [])
        except Exception:
            raise ValueError("Could not verify the image-provider key/model catalog.") from None
        return [
            {"id": m["id"], "name": m["id"]}
            for m in models
            if isinstance(m.get("id"), str) and "gpt-image" in m["id"]
        ]

    @staticmethod
    def generate(prompt, llm, emit, actor):
        conf = auth.load("image-provider")
        if not conf.get("api_key"):
            return None
        emit(
            "provider_tool_started",
            {
                "agentId": actor["id"],
                "name": "image_generation",
                "model": conf["model"],
                "implementation": "harness.ImageProvider",
                "where": urlsplit(conf["base_url"]).netloc,
                "explanation": "The agent's image prompt was sent to the separately configured image model; its ChatGPT connection remains unchanged.",
            },
        )
        try:
            response = OpenAI(
                api_key=conf["api_key"], base_url=conf["base_url"], max_retries=0, timeout=180
            ).images.generate(model=conf["model"], prompt=prompt, size="1536x1024", quality="high")
            images = [
                base64.b64decode(item.b64_json, validate=True)
                for item in response.data
                if item.b64_json
            ]
            if not images:
                raise ValueError("No generated image data returned.")
            usage = getattr(response, "usage", None)
            record = {
                "step": llm.current,
                "input": getattr(usage, "input_tokens", None),
                "output": getattr(usage, "output_tokens", None),
            }
            llm.usage.append(record)
            emit("usage", record)
            return images
        except Exception:
            raise ValueError(
                "The configured image provider could not generate the image. Check its model, key, usage and content policy."
            ) from None
