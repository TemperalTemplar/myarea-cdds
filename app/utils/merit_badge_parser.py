"""
Merit Badge Worksheet Parser
Extracts requirements from BSA merit badge workbooks (PDF or DOCX).

Strategy:
  1. Extract raw text from document
  2. Rule-based pass — handles standard BSA format
  3. If < 3 requirements found, fallback to gemma3:4b via Ollama
  4. Returns structured dict ready for Course/Module creation
"""
import re
import json
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

OLLAMA_URL  = "http://172.30.0.1:11434/api/generate"
OLLAMA_MODEL= "gemma3:4b"
FALLBACK_MODEL = "cnmoro/gemma2-2b-it-abliterated:q8_0"


# ── Text extraction ────────────────────────────────────────────────────────

def extract_text_from_pdf(path: str) -> str:
    try:
        from pdfminer.high_level import extract_text
        return extract_text(path)
    except ImportError:
        logger.warning("pdfminer not installed — trying pypdf")
        try:
            import pypdf
            reader = pypdf.PdfReader(path)
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception as e:
            raise ValueError(f"Could not extract PDF text: {e}")


def extract_text_from_docx(path: str) -> str:
    try:
        import docx
        doc = docx.Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    except ImportError:
        raise ValueError("python-docx not installed")


def extract_text(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        return extract_text_from_pdf(path)
    elif ext in ("docx", "doc"):
        return extract_text_from_docx(path)
    else:
        with open(path, "r", errors="replace") as f:
            return f.read()


# ── Badge name extraction ──────────────────────────────────────────────────

def extract_badge_name(text: str) -> str:
    """Extract merit badge name from worksheet header."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Look for pattern: title line followed by "Merit Badge Workbook"
    for i, line in enumerate(lines[:20]):
        if "Merit Badge Workbook" in line or "Merit Badge Work Book" in line:
            # Badge name is usually the line before
            if i > 0:
                name = lines[i - 1]
                # Clean up
                name = re.sub(r"Merit Badge.*", "", name, flags=re.IGNORECASE).strip()
                if name and len(name) < 100:
                    return name

    # Fallback: look for "X Merit Badge" pattern
    match = re.search(r"^(.+?)\s*Merit Badge", text[:500], re.MULTILINE | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return "Merit Badge"


# ── Rule-based requirement extraction ─────────────────────────────────────

def rule_based_extract(text: str) -> list:
    """
    Extract numbered requirements using regex.
    Handles formats:
      1. Requirement text
      1) Requirement text
      a. Sub-requirement
    """
    requirements = []

    # Split into lines and clean
    lines = [l.rstrip() for l in text.split("\n")]

    # Find numbered requirements (1. or 1) at start of line)
    req_pattern = re.compile(r"^\s*(\d+)[.)]\s+(.+)")
    sub_pattern = re.compile(r"^\s+([a-z])[.)]\s+(.+)")

    current_req = None
    current_content = []
    current_subs = []

    for line in lines:
        req_match = req_pattern.match(line)
        sub_match = sub_pattern.match(line)

        if req_match:
            # Save previous requirement
            if current_req is not None:
                requirements.append({
                    "number":          str(current_req),
                    "title":           _make_title(current_content[0] if current_content else ""),
                    "content":         "\n".join(current_content),
                    "sub_requirements": current_subs,
                })
            current_req     = req_match.group(1)
            current_content = [req_match.group(2).strip()]
            current_subs    = []

        elif sub_match and current_req is not None:
            letter  = sub_match.group(1)
            content = sub_match.group(2).strip()
            current_subs.append({"letter": letter, "content": content})
            current_content.append(f"  {letter}. {content}")

        elif current_req is not None and line.strip():
            # Continuation of current requirement
            stripped = line.strip()
            # Skip workspace lines (just dashes or underscores)
            if not re.match(r"^[-_\s]+$", stripped):
                current_content.append(stripped)

    # Save last requirement
    if current_req is not None:
        requirements.append({
            "number":          str(current_req),
            "title":           _make_title(current_content[0] if current_content else ""),
            "content":         "\n".join(current_content),
            "sub_requirements": current_subs,
        })

    return requirements


def _make_title(text: str) -> str:
    """Turn requirement text into a short title."""
    # Take first sentence or first 60 chars
    text = text.strip()
    sentence = re.split(r"[.!?]", text)[0].strip()
    if len(sentence) > 60:
        sentence = sentence[:57] + "..."
    return sentence or text[:60]


# ── Ollama AI extraction ───────────────────────────────────────────────────

def ollama_extract(text: str) -> list:
    """
    Use gemma3:4b to extract requirements when rule-based fails.
    Returns list of requirement dicts.
    """
    # Truncate to keep prompt manageable
    truncated = text[:6000]

    prompt = f"""You are a document parser. Extract all numbered requirements from this BSA merit badge worksheet.

Return ONLY valid JSON, no other text. Format:
{{
  "requirements": [
    {{
      "number": "1",
      "title": "Short title (max 60 chars)",
      "content": "Full requirement text",
      "sub_requirements": [
        {{"letter": "a", "content": "Sub-requirement text"}}
      ]
    }}
  ]
}}

Document text:
{truncated}

JSON only:"""

    for model in [OLLAMA_MODEL, FALLBACK_MODEL]:
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=120,
            )
            if resp.status_code != 200:
                continue

            raw = resp.json().get("response", "")

            # Extract JSON from response
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not json_match:
                continue

            data = json.loads(json_match.group())
            reqs = data.get("requirements", [])
            if reqs:
                logger.info("Ollama extracted %d requirements using %s", len(reqs), model)
                return reqs

        except Exception as exc:
            logger.warning("Ollama extraction failed with %s: %s", model, exc)
            continue

    return []


# ── Main parse function ────────────────────────────────────────────────────

def parse_merit_badge_worksheet(path: str) -> dict:
    """
    Parse a merit badge worksheet and return structured course data.

    Returns:
    {
        "badge_name": "Bird Study",
        "title": "Bird Study Merit Badge",
        "description": "...",
        "category": "Scouting",
        "tags": ["merit-badge", "scouting", "bird-study"],
        "version": "2024",
        "requirements": [
            {
                "number": "1",
                "title": "...",
                "content": "...",
                "sub_requirements": [...]
            }
        ],
        "parser_method": "rule_based" | "ollama"
    }
    """
    logger.info("Parsing merit badge worksheet: %s", path)

    # Extract text
    text = extract_text(path)

    # Get badge name
    badge_name = extract_badge_name(text)

    # Try rule-based first
    requirements = rule_based_extract(text)
    method = "rule_based"

    logger.info("Rule-based extracted %d requirements", len(requirements))

    # Fallback to Ollama if too few found
    if len(requirements) < 3:
        logger.info("Falling back to Ollama for extraction")
        requirements = ollama_extract(text)
        method = "ollama"

    if not requirements:
        raise ValueError(f"Could not extract requirements from worksheet. Found 0 requirements.")

    # Extract year if present
    year_match = re.search(r"(20\d{2})", text[:500])
    version = year_match.group(1) if year_match else "1.0"

    slug_name = badge_name.lower().replace(" ", "-")

    return {
        "badge_name":   badge_name,
        "title":        f"{badge_name} Merit Badge",
        "description":  f"BSA Merit Badge worksheet for {badge_name}. "
                        f"Complete all {len(requirements)} requirements to earn this badge.",
        "category":     "Scouting",
        "tags":         ["merit-badge", "scouting", slug_name],
        "version":      version,
        "requirements": requirements,
        "parser_method":method,
        "req_count":    len(requirements),
    }
