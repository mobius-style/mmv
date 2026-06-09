#!/usr/bin/env python3
"""
kiwix_adapter.py — MOBIUS MMV v2: Kiwix local Wikipedia adapter (Box W complement)
src/adapters/kiwix_adapter.py

Role:
  When Box W (WikiAdapter / FAISS) is insufficient,
  fetches full-text Wikipedia articles via kiwix-serve as a local complement.
  Does not add a new Box; functions as an internal complement within Stage 1 (local_rag).

Design principles:
  - source_type = "local_rag"  (Frozen v1.0 / 08_api_types.docx section 9 maintained)
  - No network required, no API key required, fully local operation
  - Principle G: embedding uses device='cpu' only (this adapter does not use embedding)
  - If kiwix-serve is not running, is_available() returns False and is skipped
  - Assumes wikipedia_en_all_mini series ZIM files

Dependencies:
  - kiwix-tools (kiwix-serve command) — apt install kiwix-tools
  - requests
  - beautifulsoup4 (optional — enables higher quality text extraction)

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
Spec   : mobius_v3_3_integrated.docx §4.2, §4.3, §4.6
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# -- Type definitions (shared with retrieval_selector.py) ----------------------
@dataclass
class Source:
    source_type:     str
    label:           str
    uri:             str
    chunk_index:     Optional[int]   = None
    retrieved_at:    str             = ""
    relevance_score: Optional[float] = None

    def __post_init__(self):
        if not self.retrieved_at:
            self.retrieved_at = datetime.now(timezone.utc).isoformat()


@dataclass
class RetrievalResult:
    sources:   List[Source]
    outcome:   str    # "success" | "partial" | "failed"
    synthesis: str


# -- KiwixAdapter -------------------------------------------------------------
class KiwixAdapter:
    """
    Box W complement adapter that retrieves local Wikipedia articles via kiwix-serve.

    Usage:
        adapter = KiwixAdapter()
        adapter.start_server()
        if adapter.is_available():
            result = adapter.retrieve("Photosynthesis", top_k=3)
        adapter.stop_server()

    Environment variables:
        KIWIX_ZIM_PATH   : ZIM file path (overrides constructor argument)
        KIWIX_PORT       : kiwix-serve port number (default: 8888)
        KIWIX_AUTO_START : If "1", auto-start on is_available() call
    """

    DEFAULT_PORT          = 8888
    SUFFICIENCY_THRESHOLD = 0.0    # Sufficient if text is retrieved
    SEARCH_TIMEOUT        = 8      # seconds
    MAX_SNIPPET_CHARS     = 1500   # Max characters to retrieve from article text

    def __init__(
        self,
        zim_path:   Optional[str] = None,
        port:       int           = DEFAULT_PORT,
        auto_start: bool          = False,
    ):
        self._zim_path = (
            zim_path
            or os.environ.get("KIWIX_ZIM_PATH", "")
            or self._find_zim_default()
        )
        self._port       = int(os.environ.get("KIWIX_PORT", port))
        self._auto_start = auto_start or os.environ.get("KIWIX_AUTO_START", "") == "1"
        self._proc: Optional[subprocess.Popen] = None
        self._base_url = f"http://localhost:{self._port}"

    # -- ZIM auto-discovery ----------------------------------------------------
    @staticmethod
    def _find_zim_default() -> str:
        """Search common locations and return the ZIM path. Returns empty string if not found."""
        home = Path.home()
        candidates = [
            home / "デスクトップ" / "mobius_ai" / "kiwix",
            home / "kiwix",
            Path("/opt/kiwix"),
        ]
        for d in candidates:
            if d.exists():
                zims = list(d.glob("wikipedia_en_all_mini*.zim"))
                if zims:
                    return str(sorted(zims)[-1])
        return ""

    # -- Server management -----------------------------------------------------
    def start_server(self, wait: float = 3.0) -> bool:
        """Start kiwix-serve in the background."""
        if not self._zim_path or not Path(self._zim_path).exists():
            logger.warning(f"[Kiwix] ZIM not found: {self._zim_path!r}")
            return False

        if self._proc and self._proc.poll() is None:
            logger.debug("[Kiwix] Server already running.")
            return True

        try:
            self._proc = subprocess.Popen(
                ["kiwix-serve", "--port", str(self._port), self._zim_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(wait)
            if self._proc.poll() is not None:
                logger.error("[Kiwix] Server exited immediately.")
                return False
            logger.info(f"[Kiwix] Server started: port={self._port} zim={self._zim_path}")
            return True
        except FileNotFoundError:
            logger.error("[Kiwix] kiwix-serve not found. Run: sudo apt install kiwix-tools")
            return False
        except Exception as e:
            logger.error(f"[Kiwix] Failed to start: {e}")
            return False

    def stop_server(self):
        """Stop kiwix-serve."""
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            logger.info("[Kiwix] Server stopped.")
        self._proc = None

    def is_available(self) -> bool:
        """Check whether kiwix-serve is responding."""
        import requests
        if self._auto_start and (not self._proc or self._proc.poll() is not None):
            self.start_server()
        try:
            resp = requests.get(
                f"{self._base_url}/search",
                params={"pattern": "test", "count": "1"},
                timeout=3,
            )
            return resp.status_code < 500
        except Exception:
            return False

    # -- Search and retrieval --------------------------------------------------
    def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
        """
        Retrieve articles related to the query via kiwix-serve search API.
        source_type = "local_rag" (Frozen v1.0 maintained)
        """
        import requests

        now     = datetime.now(timezone.utc).isoformat()
        sources = []
        texts   = []

        try:
            search_resp = requests.get(
                f"{self._base_url}/search",
                params={"pattern": query, "count": str(top_k), "start": "0"},
                timeout=self.SEARCH_TIMEOUT,
            )
            search_resp.raise_for_status()
            article_urls = self._parse_opensearch(search_resp.text, top_k)

            if not article_urls:
                logger.debug(f"[Kiwix] No results for: {query!r}")
                return RetrievalResult(sources=[], outcome="failed", synthesis="")

            for url in article_urls:
                try:
                    art_resp = requests.get(url, timeout=self.SEARCH_TIMEOUT)
                    art_resp.raise_for_status()
                    text, title = self._extract_text(art_resp.text, url)
                    if not text:
                        continue
                    sources.append(Source(
                        source_type     = "local_rag",   # Frozen v1.0 maintained
                        label           = title,
                        uri             = url,
                        retrieved_at    = now,
                        relevance_score = 1.0,
                    ))
                    texts.append(f"[{title}]\n{text[:self.MAX_SNIPPET_CHARS]}")
                except Exception as e:
                    logger.debug(f"[Kiwix] Article fetch failed: {url} — {e}")
                    continue

        except Exception as e:
            logger.warning(f"[Kiwix] Search failed: {e}")
            return RetrievalResult(sources=[], outcome="failed", synthesis="")

        if not sources:
            return RetrievalResult(sources=[], outcome="failed", synthesis="")

        outcome = "success" if len(sources) >= top_k else "partial"
        return RetrievalResult(
            sources   = sources,
            outcome   = outcome,
            synthesis = "\n\n".join(texts),
        )

    def get_sufficiency_score(self, result: RetrievalResult) -> float:
        return 1.0 if result.sources else 0.0

    # -- Internal parsers ------------------------------------------------------
    def _parse_opensearch(self, html_text: str, top_k: int) -> list:
        import re
        # kiwix-serve returns search results in HTML format
        # Extract href="/content/wikipedia_en_all_mini_YYYY-MM/Article_Name"
        pattern = re.compile(r'href="(/content/[^"]+)"')
        urls = []
        seen = set()
        for m in pattern.finditer(html_text):
            path = m.group(1).strip()
            if path in seen:
                continue
            seen.add(path)
            urls.append(f"{self._base_url}{path}")
            if len(urls) >= top_k:
                break
        return urls

    def _extract_text(self, html: str, url: str) -> tuple:
        title = url.split("/")[-1].replace("_", " ")
        try:
            from bs4 import BeautifulSoup
            soup  = BeautifulSoup(html, "html.parser")
            h1    = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)
            paras = soup.find_all("p")
            text  = "\n".join(p.get_text(strip=True) for p in paras if p.get_text(strip=True))
            return text, title
        except ImportError:
            import re
            m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
            if m:
                title = m.group(1).strip()
            paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
            text  = "\n".join(re.sub(r'<[^>]+>', '', p).strip() for p in paras)
            return text, title
