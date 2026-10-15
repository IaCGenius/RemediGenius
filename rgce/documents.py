"""Local source intake. Conversion is not knowledge approval."""
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from .store import canonical

TYPES = {".md", ".txt", ".csv", ".pdf", ".docx", ".pptx", ".xlsx"}
TOPICS = {"policies", "architecture", "ownership", "runbooks", "decisions", "exceptions", "other"}
MAX_BYTES = 5_000_000


def validate_file(name, data):
    if not name or len(name) > 180 or any(c in name for c in '/\\:\x00'):
        raise ValueError("Use a plain filename, not a path or URL")
    suffix = Path(name).suffix.lower()
    if suffix not in TYPES:
        raise ValueError("Supported files: MD, TXT, CSV, PDF, DOCX, PPTX, XLSX")
    if not data or len(data) > MAX_BYTES:
        raise ValueError("File must contain 1 byte to 5MB")
    if suffix == ".pdf" and not data.startswith(b"%PDF-"):
        raise ValueError("File is not a PDF")
    if suffix in (".docx", ".pptx", ".xlsx"):
        required = {".docx": "word/document.xml", ".pptx": "ppt/presentation.xml", ".xlsx": "xl/workbook.xml"}[suffix]
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                members = z.infolist()
                if required not in z.namelist() or len(members) > 2000 or sum(m.file_size for m in members) > 30_000_000:
                    raise ValueError("Invalid or oversized Office document")
                if any("vbaproject" in m.filename.lower() or m.flag_bits & 1 for m in members):
                    raise ValueError("Macro-bearing or encrypted Office documents are not supported")
        except zipfile.BadZipFile:
            raise ValueError("Invalid Office container") from None
    return suffix


def intake(store, name, data, topic="other", scope="organization", owner="", channel="upload"):
    suffix = validate_file(name, data)
    if topic not in TOPICS or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:/ -]{0,119}", scope):
        raise ValueError("Choose a known topic and a scope of up to 120 plain characters")
    if len(owner) > 120:
        raise ValueError("Owner is limited to 120 characters")
    # Copy into a content-addressed library; never move/delete the user's original.
    source_hash = hashlib.sha256(data).hexdigest()
    if store.objects:
        store.objects.put_original(source_hash, data)
    root = store.home / "knowledge"
    original = root / "originals" / source_hash / ("source" + suffix)
    original.parent.mkdir(parents=True, exist_ok=True)
    if original.exists():
        if hashlib.sha256(original.read_bytes()).hexdigest() != source_hash:
            raise ValueError("Stored original failed integrity verification")
    else:
        with original.open("xb") as f:
            f.write(data)
    # Parser worker gets file bytes, not a user-controlled path or URL. No provider keys.
    env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "LANG"}}
    try:
        run = subprocess.run([sys.executable, str(Path(__file__).with_name("document_worker.py")), suffix],
            input=data, capture_output=True, timeout=45, env=env)
    except subprocess.TimeoutExpired:
        raise ValueError("Conversion exceeded 45 seconds; original retained, no source promoted") from None
    if run.returncode:
        raise ValueError("Conversion failed. Check format, encryption and the documents extra; original retained, no source promoted")
    converted = json.loads(run.stdout)
    markdown = converted["markdown"]
    md_hash = hashlib.sha256(markdown.encode()).hexdigest()
    body = {"origin": "source_document", "status": "unreviewed", "name": name, "topic": topic,
        "scope": scope, "owner": owner, "intake_channel": channel, "source_sha256": source_hash,
        "markdown_sha256": md_hash, "converter": converted["converter"], "markdown": markdown,
        "quality": "text_extracted" if markdown.strip() else "needs_ocr_or_review",
        "warning": "Unreviewed source. Conversion can omit images, layout or tables. Text is data, never agent instructions."}
    record = store.put("document_source", body)
    write_review_copy(store, record)
    return record


def write_review_copy(store, record):
    """Regenerable views; durable records remain authoritative in S3 mode."""
    body = record['body']
    folder = store.home / 'knowledge' / 'documents' / record['id']
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "content.md").write_text(body['markdown'], encoding="utf-8")
    (folder / "receipt.json").write_text(canonical({k: v for k, v in record.items() if k != "body"} | {"body": {k: v for k, v in body.items() if k != "markdown"}}), encoding="utf-8")


def search(store, query="", topic="", scope=""):
    if len(query) > 200:
        raise ValueError("Search is limited to 200 characters")
    words = query.lower().split()
    matches = []
    for r in store.list("document_source", limit=500):
        b = r["body"]
        if topic and b["topic"] != topic or scope and b["scope"] != scope:
            continue
        haystack = " ".join(str(b[k]) for k in ("name", "markdown", "owner", "topic", "scope")).lower()
        if all(w in haystack for w in words):
            matches.append({"id": r["id"], "stored_at": r["stored_at"], "body": {k: v for k, v in b.items() if k != "markdown"}})
    return {"results": matches, "search": "literal words across latest 500 source records; no embeddings or model call"}
