"""One chunk per bullet, each prefixed with the document title and section heading."""

from __future__ import annotations

import re

PER_BULLET_SOURCES: tuple[str, ...] = ("data/pull_sheet/menu/food.md",)

_TITLE = re.compile(r"^#\s+\S")
_H2 = re.compile(r"^##\s+\S")


def _split_title(lines: list[str]) -> tuple[str | None, list[str]]:
    """Return the first `# ` title line and the remaining lines."""
    for index, line in enumerate(lines):
        if _TITLE.match(line):
            return line.strip(), lines[:index] + lines[index + 1 :]
    return None, lines


def _split_sections(lines: list[str]) -> list[tuple[str | None, list[str]]]:
    """Split into (heading line or None for the preamble, body lines)."""
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in lines:
        if _H2.match(line):
            sections.append((line.strip(), []))
        else:
            sections[-1][1].append(line)
    return sections


def _blocks(body: list[str]) -> list[str]:
    """Split a section body into bullets (with continuations) and text blocks."""
    blocks: list[list[str]] = []
    current: list[str] | None = None
    for line in body:
        if not line.strip():
            if current is not None:
                current.append(line)
            continue
        if line.startswith("- "):
            current = [line]
            blocks.append(current)
        elif line[0] in " \t" and current is not None:
            current.append(line)
        elif current is not None and not current[0].startswith("- "):
            current.append(line)
        else:
            current = [line]
            blocks.append(current)
    return [text for text in ("\n".join(b).strip() for b in blocks) if text]


def _join(title: str | None, heading: str | None, content: str | None) -> str:
    return "\n\n".join(part for part in (title, heading, content) if part)


def chunk_per_bullet(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    title, lines = _split_title(text.splitlines())
    sections = _split_sections(lines)
    chunks: list[str] = []
    for heading, body in sections:
        blocks = _blocks(body)
        if heading is None:
            # Preamble: kept whole, with the title.
            content = "\n".join(body).strip()
            if content or (title and len(sections) == 1):
                chunks.append(_join(title, None, content))
        elif not blocks:
            chunks.append(_join(title, heading, None))
        else:
            chunks.extend(_join(title, heading, block) for block in blocks)
    return chunks
