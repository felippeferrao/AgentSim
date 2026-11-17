"""Workspace Markdown knowledge and execution-scoped motor quote inputs."""

import json
import re
import uuid
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

EXAMPLE = Path(__file__).parent / "examples" / "insurance-pricing.md"
EDITORIAL = EXAMPLE.with_name("quote-editorial.md")
TABLES = {
    "Vehicles": ["Model", "Annual base (EUR)"],
    "Partners": ["Partner", "Discount (%)"],
}


def rows(markdown, section):
    match = re.search(rf"^## {section}[ \t]*\n(.*?)(?=^#|\Z)", markdown, re.M | re.S)
    if not match:
        return {}
    table = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in match[1].splitlines() if line.strip().startswith("|")
    ]
    if len(table) < 2 or table[0] != TABLES[section]:
        raise ValueError(f"Use the {section} table headers shown in the starter document.")
    if len(table[1]) != 2 or not all(re.fullmatch(r":?-{3,}:?", cell) for cell in table[1]):
        raise ValueError(f"Add a Markdown separator row under the {section} headers.")
    result = {}
    for row in table[2:]:
        if len(row) != 2 or not 0 < len(row[0]) <= 100 or row[0].casefold() in result:
            raise ValueError(f"Use unique names and two cells per row in {section}.")
        if not re.fullmatch(r"[0-9]{1,8}(?:\.[0-9]{1,2})?", row[1]):
            raise ValueError(f"Use a number with up to two decimal places in {section}.")
        value = Decimal(row[1])
        if section == "Partners" and value > 100:
            raise ValueError("Partner discounts must be between 0 and 100 percent.")
        result[row[0].casefold()] = (row[0], value)
    return result


def source_text(document):
    return "\n\n".join([document["markdown"], *(file["markdown"] for file in document.get("files", []))])


def public(document):
    markdown = source_text(document)
    return {
        **document,
        "files": document.get("files", []),
        "vehicles": [name for name, _ in rows(markdown, "Vehicles").values()],
        "partners": [name for name, _ in rows(markdown, "Partners").values()],
    }


def list_brains(db):
    return [public(json.loads(row[0])) for row in db.execute("SELECT data FROM brains ORDER BY rowid")]


def save_brain(db, body):
    name, markdown = body.get("name"), body.get("markdown")
    if not isinstance(name, str) or not 0 < len(name.strip()) <= 80:
        raise ValueError("Enter a Brain name up to 80 characters.")
    if not isinstance(markdown, str) or not 0 < len(markdown.strip()) <= 16000:
        raise ValueError("Provide Markdown up to 16,000 characters.")
    files = body.get("files", [])
    if not isinstance(files, list) or len(files) > 9:
        raise ValueError("A Brain can contain up to ten Markdown files.")
    normalized = []
    names = set()
    for file in files:
        if not isinstance(file, dict):
            raise ValueError("Each file needs a name and Markdown.")
        filename, content = file.get("name"), file.get("markdown")
        if (not isinstance(filename, str) or not 0 < len(filename.strip()) <= 120
            or not isinstance(content, str) or not 0 < len(content.strip()) <= 16000
            or filename.strip().casefold() in names):
            raise ValueError("Provide unique file names and Markdown up to 16,000 characters per file.")
        names.add(filename.strip().casefold())
        normalized.append({"name": filename.strip(), "markdown": content.replace("\r\n", "\n")})
    if len(markdown) + sum(len(file["markdown"]) for file in normalized) > 48000:
        raise ValueError("Use up to 48,000 Markdown characters per Brain.")
    ident = body.get("id") or str(uuid.uuid4())
    if not isinstance(ident, str):
        raise ValueError("Invalid Brain id.")
    row = db.execute("SELECT data FROM brains WHERE id = ?", (ident,)).fetchone()
    previous = json.loads(row[0]) if row else None
    if body.get("id") and (not previous or previous["revision"] != body.get("revision")):
        raise ValueError("This Brain changed. Reopen the editor and try again.")
    document = public({
        "id": ident, "name": name.strip(), "markdown": markdown.replace("\r\n", "\n"), "files": normalized,
        "revision": previous["revision"] + 1 if previous else 1,
    })
    from quote_pdf import palette

    joined = source_text(document)
    for heading in ("Vehicles", "Partners", "Palette"):
        if len(re.findall(rf"^## {heading}[ \t]*$", joined, re.M)) > 1:
            raise ValueError(f"Use only one {heading} section per Brain.")
    palette(joined)
    db.execute("INSERT OR REPLACE INTO brains VALUES (?, ?)", (ident, json.dumps(document)))
    return document


def pricing_documents(brains, team, agents):
    partner = team.get("quotePartner", "").casefold()
    manager = next((a for a in agents if a["id"] == team.get("manager")), {})
    analyst_grants = {
        ident for agent in agents
        if agent["id"] != manager.get("id") and "calculator" in agent["tools"]
        for ident in agent.get("brains", [])
    }
    return [
        document for document in brains
        if document["id"] in manager.get("brains", []) and document["id"] in analyst_grants
        and document["vehicles"] and any(name.casefold() == partner for name in document["partners"])
    ]


def quote(document, vehicle, partner):
    vehicles = rows(source_text(document), "Vehicles")
    partners = rows(source_text(document), "Partners")
    if not isinstance(vehicle, str) or not isinstance(partner, str):
        raise ValueError("Choose a vehicle and a partner.")
    if vehicle.casefold() not in vehicles or partner.casefold() not in partners:
        raise ValueError("Choose a vehicle and a partner from the selected Brain.")
    vehicle, base = vehicles[vehicle.casefold()]
    partner, discount = partners[partner.casefold()]
    net = (base * (1 - discount / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "brainId": document["id"], "brain": document["name"], "revision": document["revision"],
        "vehicle": vehicle, "partner": partner, "base": f"{base:.2f}",
        "discount": str(discount), "discountAmount": f"{base - net:.2f}",
        "total": f"{net:.2f}", "currency": "EUR",
        "formula": f"EUR {base:.2f} × (1 − {discount}/100) = EUR {net:.2f}",
    }


def reusable_illustration(runs, document, vehicle):
    from artifact_history import artifact_path

    explicit = re.search(
        rf"^\|\s*{re.escape(vehicle)}\s*\|\s*(/artifacts/[A-Za-z0-9-]+/[a-f0-9]{{32}}\.png)\s*\|",
        source_text(document), re.I | re.M,
    )
    if explicit:
        url = explicit[1]
        _, _, run_id, filename = url.split("/")
        selected = {"id": filename[:-4], "runId": run_id, "title": vehicle + " illustration",
                    "extension": "png", "url": url}
        try:
            artifact_path(selected)
        except ValueError:
            pass
        else:
            return selected
    for run in reversed(runs):
        request = run.get("quoteRequest") or {}
        if not run.get("completed") or (request.get("brainId"), request.get("vehicle")) != (document["id"], vehicle):
            continue
        for event in reversed(run.get("events", [])):
            item = event["data"]
            if event["type"] != "artifact_created" or item.get("extension") != "png":
                continue
            try:
                artifact_path(item)
            except ValueError:
                continue
            return item
    return None


def tools(actor, config, emit):
    from crewai.tools import tool

    documents = {d["id"]: d for d in config.get("brains", []) if d["id"] in actor.get("brains", [])}
    if not documents:
        return []
    quote_request = config.get("quoteRequest")
    from quote_pdf import palette

    editorial = next((d for d in documents.values() if palette(source_text(d))), None) if quote_request else None

    def evidence(name, details, implementation):
        emit("tool_completed", {
            "actorId": actor["id"], "agentId": actor["id"], "agent": actor["name"],
            "name": name, "output": details, "where": "AgentSim Brain snapshot",
            "implementation": implementation,
        })

    @tool("read_brain")
    def read_brain(brain_id: str) -> str:
        """Read one granted Brain's Markdown and revision using its listed ID."""
        if brain_id not in documents:
            return "That Brain is outside this agent's permissions."
        document = documents[brain_id]
        evidence("Read Brain", {
            "brainId": brain_id, "brain": document["name"], "revision": document["revision"],
            "text": f'{document["name"]} · revision {document["revision"]}',
        }, "brain.tools.read_brain")
        return json.dumps({
            "name": document["name"], "revision": document["revision"], "markdown": document["markdown"], "files": document.get("files", []),
        }, ensure_ascii=False)

    @tool("calculate_quote")
    def calculate_quote() -> str:
        """Calculate the current selected vehicle and partner quote using the granted source tables."""
        document = documents[quote_request["brainId"]]
        result = quote(document, quote_request["vehicle"], quote_request["partner"])
        config["quoteProgress"]["result"] = result
        evidence("Calculate quote", {**result, "text": result["formula"]}, "brain.quote")
        return json.dumps(result, ensure_ascii=False)

    @tool("publish_quote")
    def publish_quote() -> str:
        """Publish the verified calculation as a real one-page PDF using the granted editorial Brain."""
        from artifact_history import artifact_path, reuse_event
        from harness import ArtifactStore
        from quote_pdf import render

        progress = config["quoteProgress"]
        if not progress.get("result"):
            return "Ask the pricing analyst to call calculate_quote first."
        if progress.get("pdf"):
            return progress["pdf"]["url"]
        evidence("Read editorial Brain", {
            "brainId": editorial["id"], "revision": editorial["revision"],
            "text": f'{editorial["name"]} · revision {editorial["revision"]}',
        }, "brain.tools.publish_quote")
        item = config.get("quoteIllustration")
        image = (item, artifact_path(item)) if item else None
        if item:
            reuse_event(emit, actor, [item], "quote PDF")
        pdf = render(progress["result"], {**editorial, "markdown": source_text(editorial)}, image)
        progress["pdf"] = ArtifactStore(config["run_id"], actor, emit).write(
            "Motor insurance quote", "pdf", pdf,
            {"document": {"layout": "motor-quote", "pages": 1, "illustrated": bool(image)}},
        )
        config["conversationArtifacts"].append(progress["pdf"])
        evidence("Publish quote PDF", {"text": progress["pdf"]["url"]}, "quote_pdf.render")
        return progress["pdf"]["url"]

    assigned = [read_brain]
    if quote_request and quote_request["brainId"] in documents and "calculator" in actor["tools"]:
        assigned.append(calculate_quote)
    if editorial and "pdf-generator" in actor["tools"]:
        assigned.append(publish_quote)
    return assigned
