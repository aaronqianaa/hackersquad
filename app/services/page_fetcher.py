from __future__ import annotations

import json
import re
from html import unescape
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.request import Request, urlopen


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.meta: dict[str, str] = {}
        self._in_title = False
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() == "meta":
            key = attr_map.get("property") or attr_map.get("name")
            content = attr_map.get("content", "")
            if key and content:
                self.meta[key.lower()] = content

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        cleaned = data.strip()
        if not cleaned:
            return
        if self._in_title:
            self.title += cleaned
        self._text_parts.append(cleaned)

    @property
    def visible_text(self) -> str:
        text = " ".join(self._text_parts)
        return re.sub(r"\s+", " ", text).strip()


def _extract_metric(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        pattern = rf"(\d[\d,\.]*\s*[kKmM]?)\s+{label}"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _first_non_empty(*values: str | None) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def fetch_page_snapshot(source_url: str) -> dict:
    request = Request(source_url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=10) as response:
            raw_html = response.read().decode("utf-8", errors="ignore")
            final_url = response.geturl()
    except (URLError, ValueError):
        return {
            "source_url": source_url,
            "final_url": source_url,
            "title": "",
            "description": "",
            "visible_text": "",
            "likes": None,
            "comments": None,
            "views": None,
            "followers": None,
            "selling_points": [],
            "offer": "",
            "fetch_ok": False,
        }

    parser = _MetaParser()
    parser.feed(raw_html)
    meta = parser.meta
    text = unescape(parser.visible_text)
    title = _first_non_empty(parser.title, meta.get("og:title"), meta.get("twitter:title"))
    description = _first_non_empty(
        meta.get("description"),
        meta.get("og:description"),
        meta.get("twitter:description"),
    )
    combined_text = " ".join(part for part in [title, description, text] if part)
    selling_points = [part.strip() for part in re.split(r"[.!?]", description) if part.strip()][:3]

    return {
        "source_url": source_url,
        "final_url": final_url,
        "title": title,
        "description": description,
        "visible_text": text[:4000],
        "likes": _extract_metric(combined_text, ("likes", "like")),
        "comments": _extract_metric(combined_text, ("comments", "comment")),
        "views": _extract_metric(combined_text, ("views", "view")),
        "followers": _extract_metric(combined_text, ("followers", "followers")),
        "selling_points": selling_points,
        "offer": selling_points[0] if selling_points else description[:180],
        "fetch_ok": True,
        "meta": {
            "og_title": meta.get("og:title", ""),
            "og_description": meta.get("og:description", ""),
        },
    }


def snapshot_for_prompt(snapshot: dict) -> str:
    prompt_payload = {
        "title": snapshot.get("title"),
        "description": snapshot.get("description"),
        "likes": snapshot.get("likes"),
        "comments": snapshot.get("comments"),
        "views": snapshot.get("views"),
        "followers": snapshot.get("followers"),
        "offer": snapshot.get("offer"),
        "selling_points": snapshot.get("selling_points"),
        "visible_text_excerpt": snapshot.get("visible_text", "")[:1200],
    }
    return json.dumps(prompt_payload, ensure_ascii=True)
