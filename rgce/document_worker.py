"""Bounded local conversion worker, not an OS sandbox. Plugins and cloud OCR are off."""
import io
import json
import sys
from importlib.metadata import version


def main():
    data = sys.stdin.buffer.read(5_000_001)
    if len(data) > 5_000_000:
        raise ValueError("Input too large")
    suffix = sys.argv[1]
    if suffix in (".md", ".txt"):
        markdown = data.decode("utf-8-sig")
        converter = "utf8-pass-through/1"
    else:
        from markitdown import MarkItDown
        converter = "markitdown/" + version("markitdown")
        # Narrow byte-stream API: no URI resolution, plugins, LLM client or cloud endpoint.
        result = MarkItDown(enable_plugins=False).convert_stream(io.BytesIO(data), file_extension=suffix)
        markdown = result.text_content
    if len(markdown.encode()) > 2_000_000:
        raise ValueError("Converted text exceeds 2MB")
    sys.stdout.buffer.write(json.dumps({"markdown": markdown, "converter": converter}, ensure_ascii=False).encode())


if __name__ == "__main__":
    main()
