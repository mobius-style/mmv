"""Render-faithful extraction for Kiwix MediaWiki HTML (candidate v2).

Fixes measured on 2026-09-14 against the current extractor:
  1. per-article ZIM footer boilerplate ("This article is issued from Wikipedia…")
     present in 96.1% of published ja chunks / 89.9% of zh chunks;
  2. <head>/<h1> title text duplicated into the body;
  3. inline tags replaced by a space, splitting words ("<b>Ar</b>gentino" -> "Ar gentino");
  4. HTML entities never unescaped (&nbsp;, &amp; survive as text);
  5. injected spaces inside CJK sentences.
Block elements become newlines so the chunker can treat them as segment boundaries.
"""
import re
from html import unescape

_CONTENT   = re.compile(r'<div[^>]+id="mw-content-text"', re.I)
_HTDIG     = re.compile(r'<!--\s*htdig_noindex\s*-->.*?<!--\s*/htdig_noindex\s*-->', re.S | re.I)
_ZIMFOOT   = re.compile(r'<div[^>]*class="[^"]*zim-footer[^"]*".*?</div>', re.S | re.I)
_SCRIPT    = re.compile(r'<(script|style)\b[^>]*>.*?</\1>', re.I | re.S)
_COMMENT   = re.compile(r'<!--.*?-->', re.S)
_BLOCK     = re.compile(r'</?(?:p|div|section|h[1-6]|li|ul|ol|dl|dd|dt|tr|table|tbody|thead|br|hr|blockquote|figure|figcaption|caption|aside|nav|header|footer|main)\b[^>]*>', re.I)
_CELL      = re.compile(r'</(?:td|th)\s*>', re.I)
_TAG       = re.compile(r'<[^>]+>')
_CSSCMT    = re.compile(r'/\*.*?\*/', re.S)
_CSSRULE   = re.compile(r'[.#@][-\w][^{}<>]{0,200}\{[^{}]*\}')
_FOOTTXT   = re.compile(r'This article is issued from Wikipedia[^\n]*', re.I)
_EDITLINKS = re.compile(r'\[\s*(?:edit|編集|编辑|編輯)\s*\]', re.I)
_NAVLINE   = re.compile(r'^(?:[■□▪\s]*(?:Template|テンプレート|ノート|解説|Project|プロジェクト|カテゴリ|表示|編集|v\s*[·・.]?\s*t\s*[·・.]?\s*e|查|论|編|编|論|閱|读)\b[^\n]{0,40})$', re.I)
_SYMBOLONLY= re.compile(r'^[\W_]{1,12}$')
_CJK       = r'　-〿぀-ヿ㐀-䶿一-鿿豈-﫿＀-￯'
_CJKSPACE  = re.compile(r'(?<=[' + _CJK + r'])[ \t]+(?=[' + _CJK + r'])')
_SPACES    = re.compile(r'[ \t ]+')
_NEWLINES  = re.compile(r'\s*\n\s*')

def extract_text(html: str) -> str:
    m = _CONTENT.search(html)
    if m:
        html = html[m.start():]
    else:                                   # fall back to <body>
        b = html.lower().find('<body')
        if b >= 0: html = html[b:]
    html = _HTDIG.sub('\n', html)
    html = _ZIMFOOT.sub('\n', html)
    html = _SCRIPT.sub(' ', html)
    html = _COMMENT.sub(' ', html)
    html = _CELL.sub(' 　| ', html)     # keep table cell boundaries visible
    html = _BLOCK.sub('\n', html)
    html = _TAG.sub('', html)               # inline tags: no space injected
    text = unescape(html)
    text = _CSSCMT.sub(' ', text)
    text = _CSSRULE.sub(' ', text)
    text = _FOOTTXT.sub(' ', text)
    text = _EDITLINKS.sub(' ', text)
    text = text.replace('　| \n', '\n').replace('　|', ' |')
    text = _SPACES.sub(' ', text)
    text = _NEWLINES.sub('\n', text)
    text = _CJKSPACE.sub('', text)
    lines, seen_first = [], None
    for ln in (l.strip(' |') for l in text.split('\n')):
        if not ln: continue
        if _NAVLINE.match(ln) or _SYMBOLONLY.match(ln): continue
        if seen_first is None: seen_first = ln
        elif ln == seen_first: continue     # drop repeated title lines
        lines.append(ln)
    return '\n'.join(lines).strip()
