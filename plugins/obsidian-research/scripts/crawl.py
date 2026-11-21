#!/usr/bin/env python3
"""Fetch a small, same-host set of public HTML pages for cited research."""

from __future__ import annotations

import argparse
import html
import ipaddress
import json
import re
import socket
import time
from collections import deque
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser


USER_AGENT = "ObsidianResearch/0.1 (+https://github.com/ThomasMarsflier)"
MAX_BYTES = 1_000_000
SKIP_TAGS = {"script", "style", "nav", "footer", "header", "aside", "form", "svg"}
BLOCK_TAGS = {"p", "div", "article", "section", "h1", "h2", "h3", "h4", "li", "blockquote", "br", "tr"}


def validate_url(url: str, expected_host: str | None = None) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only HTTP(S) URLs are supported")
    host = parsed.hostname.lower().rstrip(".")
    if expected_host and host != expected_host:
        raise ValueError("Cross-host navigation is outside this crawl")
    if parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
        raise ValueError("Credentials and nonstandard ports are not supported")
    try:
        addresses = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError(f"Cannot resolve host: {exc}") from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("Private or non-global network target is blocked")
    return urldefrag(url).url


class SameHostRedirect(HTTPRedirectHandler):
    def __init__(self, host: str):
        self.host = host
        self.robots: RobotFileParser | None = None

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl, self.host)
        if self.robots is not None and not self.robots.can_fetch(USER_AGENT, newurl):
            raise ValueError("Redirect target blocked by robots.txt")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PageParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self.images: list[dict] = []
        self.skip_depth = 0
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("property") in {"og:image", "og:image:secure_url"} and attrs.get("content"):
            self._add_image(attrs["content"], "", "social-preview")
        if tag in SKIP_TAGS:
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True
        if self.skip_depth == 0 and tag in BLOCK_TAGS:
            self.text_parts.append("\n")
        if self.skip_depth == 0 and tag == "a" and attrs.get("href") and len(self.links) < 200:
            self.links.append(urljoin(self.base_url, html.unescape(attrs["href"])))
        if self.skip_depth == 0 and tag == "img":
            srcset = attrs.get("srcset", "")
            candidates = []
            for part in srcset.split(","):
                tokens = part.strip().split()
                if tokens:
                    scale = tokens[1] if len(tokens) > 1 else ""
                    match = re.fullmatch(r"([0-9.]+)(w|x)", scale)
                    score = float(match.group(1)) if match else 0
                    candidates.append((score, tokens[0]))
            source = max(candidates)[1] if candidates else attrs.get("data-src") or attrs.get("src")
            if source:
                self._add_image(source, attrs.get("alt", ""), "inline")

    def _add_image(self, source: str, alt: str, role: str) -> None:
        if len(self.images) < 100:
            self.images.append({"url": urljoin(self.base_url, html.unescape(source)), "alt": alt.strip(), "role": role})

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif self.skip_depth == 0 and tag in BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        elif self.skip_depth == 0:
            self.text_parts.append(data)

    def result(self) -> tuple[str, str, list[str], list[dict]]:
        title = " ".join(" ".join(self.title_parts).split())
        text = "".join(self.text_parts)
        lines = [" ".join(line.split()) for line in text.splitlines()]
        text = "\n".join(line for line in lines if line)
        return title, text[:100_000], self.links, self.images


def read_limited(response, limit: int = MAX_BYTES) -> bytes:
    data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Page exceeds the size limit")
    return data


def robots_for(opener, origin: str) -> RobotFileParser:
    url = origin + "/robots.txt"
    parser = RobotFileParser()
    parser.set_url(url)
    try:
        with opener.open(Request(url, headers={"User-Agent": USER_AGENT}), timeout=10) as response:
            raw = read_limited(response, 200_000)
        parser.parse(raw.decode("utf-8", errors="replace").splitlines())
    except HTTPError as exc:
        if exc.code == 404:
            parser.parse([])
        else:
            raise ValueError(f"robots.txt returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise ValueError(f"robots.txt unavailable: {exc}") from exc
    return parser


def crawl(seed: str, max_pages: int = 8, depth: int = 1, delay: float = 1.0) -> dict:
    seed = validate_url(seed)
    parts = urlsplit(seed)
    host = parts.hostname.lower().rstrip(".")
    origin = f"{parts.scheme}://{parts.netloc}"
    redirect_handler = SameHostRedirect(host)
    opener = build_opener(redirect_handler)
    robots = robots_for(opener, origin)
    redirect_handler.robots = robots
    delay = max(delay, float(robots.crawl_delay(USER_AGENT) or 0))
    queue = deque([(seed, 0)])
    seen: set[str] = set()
    pages: list[dict] = []
    errors: list[dict] = []
    last_request = time.monotonic()
    attempts = 0
    while queue and len(pages) < max_pages and attempts < max_pages * 3:
        url, level = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        attempts += 1
        try:
            validate_url(url, host)
            if not robots.can_fetch(USER_AGENT, url):
                raise ValueError("Blocked by robots.txt")
            wait = delay - (time.monotonic() - last_request)
            if wait > 0:
                time.sleep(wait)
            last_request = time.monotonic()
            with opener.open(Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"}), timeout=15) as response:
                final_url = validate_url(response.geturl(), host)
                content_type = response.headers.get_content_type()
                if content_type not in {"text/html", "application/xhtml+xml"}:
                    raise ValueError(f"Unsupported content type: {content_type}")
                charset = response.headers.get_content_charset() or "utf-8"
                raw = read_limited(response)
            parser = PageParser(final_url)
            parser.feed(raw.decode(charset, errors="replace"))
            title, text, links, images = parser.result()
            if not text:
                raise ValueError("No readable HTML text")
            pages.append({"url": final_url, "title": title or final_url, "fetched_at": datetime.now(timezone.utc).isoformat(), "text": text, "images": images})
            if level < depth:
                for link in links:
                    try:
                        link = validate_url(link, host)
                        if link not in seen:
                            queue.append((link, level + 1))
                    except ValueError:
                        continue
        except (ValueError, HTTPError, URLError, TimeoutError, UnicodeError) as exc:
            errors.append({"url": url, "error": str(exc)})
    return {"seed": seed, "pages": pages, "errors": errors}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("url")
    ap.add_argument("--max-pages", type=int, default=8)
    ap.add_argument("--depth", type=int, default=1)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--output")
    args = ap.parse_args()
    if not 1 <= args.max_pages <= 20 or not 0 <= args.depth <= 2 or not 0.5 <= args.delay <= 10:
        ap.error("Allowed ranges: 1-20 pages, depth 0-2, delay 0.5-10 seconds")
    result = crawl(args.url, args.max_pages, args.depth, args.delay)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output + "\n")
    else:
        print(output)


if __name__ == "__main__":
    main()
