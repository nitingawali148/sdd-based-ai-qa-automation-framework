"""Requirement ingestion: Markdown (primary), YAML, JSON, PDF, DOCX.

Every format is normalised into a `ParsedDocument`: metadata, raw text and named sections. The
Requirement Analysis Agent turns this into a `StructuredRequirement`.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class ParsedDocument:
    source_file: str
    source_hash: str
    meta: dict[str, Any]
    title: str
    text: str
    sections: dict[str, str] = field(default_factory=dict)  # lower-case heading -> body

    def section(self, *names: str) -> str:
        for name in names:
            for key, body in self.sections.items():
                if key == name or key.startswith(name):
                    return body
        return ""

    def to_payload(self) -> dict[str, Any]:
        return {"source_file": self.source_file, "source_hash": self.source_hash, "meta": self.meta,
                "title": self.title, "sections": self.sections, "text": self.text}


# ---------------------------------------------------------------------------- markdown helpers
def parse_table(body: str) -> list[dict[str, str]]:
    rows = [ln.strip() for ln in body.splitlines() if ln.strip().startswith("|")]
    if len(rows) < 2:
        return []
    def cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]
    header = [h.lower().replace(" ", "_") for h in cells(rows[0])]
    out = []
    for line in rows[1:]:
        if re.fullmatch(r"\|?[\s:\-|]+\|?", line):
            continue
        vals = cells(line)
        out.append({h: (vals[i] if i < len(vals) else "") for i, h in enumerate(header)})
    return out


def parse_bullets(body: str) -> list[tuple[str, list[str]]]:
    """Return top-level bullets with their nested sub-bullets."""
    items: list[tuple[str, list[str]]] = []
    for line in body.splitlines():
        if not line.strip():
            continue
        m = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
        if not m:
            continue
        indent, text = len(m.group(1).replace("\t", "    ")), m.group(2).strip()
        if indent >= 2 and items:
            items[-1][1].append(text)
        else:
            items.append((text, []))
    return items


def split_sections(text: str) -> tuple[str, dict[str, str]]:
    title, sections, current, buf = "", {}, None, []
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            level, heading = len(m.group(1)), m.group(2).strip()
            if level == 1 and not title:
                title = heading
                continue
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current, buf = heading.lower(), []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return title, sections


# ---------------------------------------------------------------------------- format readers
def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PDF ingestion needs 'pypdf' (pip install pypdf)") from exc
    return "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)


def _read_docx(path: Path) -> str:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("DOCX ingestion needs 'python-docx' (pip install python-docx)") from exc
    document = docx.Document(str(path))
    lines: list[str] = []
    for para in document.paragraphs:
        style = (para.style.name or "").lower() if para.style is not None else ""
        text = para.text.strip()
        if not text:
            continue
        if style.startswith("heading"):
            level = int(re.sub(r"\D", "", style) or 1)
            lines.append("#" * level + " " + text)
        elif style.startswith("list"):
            lines.append(f"- {text}")
        else:
            lines.append(text)
    for table in document.tables:
        rows = [[c.text.strip() for c in row.cells] for row in table.rows]
        if rows:
            lines.append("| " + " | ".join(rows[0]) + " |")
            lines.append("|" + "---|" * len(rows[0]))
            lines.extend("| " + " | ".join(r) + " |" for r in rows[1:])
    return "\n".join(lines)


def _plain_text_to_markdown(text: str) -> str:
    """Best-effort heading recovery for PDF text: 'Acceptance Criteria' lines become headings."""
    known = ("user story", "objective", "business rules", "input fields", "acceptance criteria", "ui",
             "api", "non-functional", "dependencies", "open questions", "functional requirements")
    out = []
    for line in text.splitlines():
        stripped = line.strip().rstrip(":")
        if stripped.lower() in known or stripped.lower().startswith(known[-3]):
            out.append(f"## {stripped}")
        elif re.match(r"^(REQ-\d+)\b", stripped) and not out:
            out.append(f"# {stripped}")
        elif re.match(r"^[•●▪]\s*", stripped):
            out.append("- " + re.sub(r"^[•●▪]\s*", "", stripped))
        else:
            out.append(line)
    return "\n".join(out)


def parse_requirement(path: Path) -> ParsedDocument:
    raw_bytes = path.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()[:16]
    suffix = path.suffix.lower()
    meta: dict[str, Any] = {}

    if suffix in (".yaml", ".yml", ".json"):
        data = yaml.safe_load(raw_bytes.decode("utf-8")) if suffix != ".json" else json.loads(raw_bytes)
        if not isinstance(data, dict):
            raise ValueError(f"{path.name}: expected a mapping at the top level")
        meta = {k: data[k] for k in ("id", "title", "feature", "feature_code", "priority") if k in data}
        sections = {str(k).lower().replace("_", " "): (v if isinstance(v, str) else yaml.safe_dump(v))
                    for k, v in data.items() if k not in meta}
        text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        return ParsedDocument(str(path), digest, meta, str(data.get("title", path.stem)), text, sections)

    if suffix == ".md":
        text = raw_bytes.decode("utf-8")
    elif suffix == ".pdf":
        text = _plain_text_to_markdown(_read_pdf(path))
    elif suffix == ".docx":
        text = _read_docx(path)
    else:
        raise ValueError(f"Unsupported requirement format: {suffix}")

    fm = _FRONT_MATTER.match(text)
    if fm:
        meta = yaml.safe_load(fm.group(1)) or {}
        text = text[fm.end():]
    title, sections = split_sections(text)
    m = re.match(r"(REQ-\d+)\s*[:\-–]\s*(.*)", title)
    if m:
        meta.setdefault("id", m.group(1))
        title = m.group(2).strip()
    meta.setdefault("id", path.stem.upper())
    return ParsedDocument(str(path), digest, meta, meta.get("title", title) or path.stem, text, sections)
