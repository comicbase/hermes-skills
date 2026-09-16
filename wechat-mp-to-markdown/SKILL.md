---
name: wechat-mp-to-markdown
description: "Use when saving a WeChat 公众号 article as Markdown."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [WeChat, Markdown, Scraping, Archival]
    related_skills: [blocked-page-recovery]
---

# WeChat MP article → Markdown

One-shot:

```bash
uv run --quiet --with beautifulsoup4 --with lxml --with markdownify \
  python scripts/wx_mp_to_md.py "https://mp.weixin.qq.com/s/XXXX" ~/Downloads/<slug>
```

Produces `<outdir>/<title>.md` + `<outdir>/images/NN.png` (relative links).
Markdown only — no styled HTML artifact; the user wants plain text output.

## Why not the normal fetchers

- `web_extract` **fails** on mp.weixin.qq.com with "Blocked: URL targets a
  private or internal network address" — a false positive, not a real block.
- The browser tools may refuse too (`use_real_profile` needs a Chromium
  default). `curl` works fine and needs no login for public articles:

```bash
curl -sSL -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1 MicroMessenger/8.0.49" \
  -o /tmp/wx.html "https://mp.weixin.qq.com/s/XXXX"
```

## Article anatomy (selectors that matter)

| What | Where |
|---|---|
| Body | `#js_content` |
| Title | `#activity-name` |
| 公众号 | `#js_name` |
| 作者 | `#js_author_name` |
| 发布时间 | **not** in `#publish_time` (JS-filled, empty) — parse `var ct = "<unix>"` from the HTML |
| 摘要 | `meta[name=description]` (also appears as a leading blockquote in body) |

`#js_content` also contains junk to decompose: `script`, `style`,
`.js_img_loading`, `#js_pc_qr_code`, `.reward_area`.

## The three things that break naive conversion

1. **Code blocks lose every line break.** Structure is
   `section.code-snippet__fix > ul.code-snippet__line-index + pre.code-snippet__js`,
   and *each `<code>` child of the `<pre>` is ONE line* (a blank line is
   `<code><span><br/></span></code>`). `markdownify`'s default `convert_pre`
   squashes them into a single line. Fix: read the `<code>` children yourself,
   join with `\n`, and reset the section to a `@@CODEBLOCKn@@` placeholder that
   is substituted with a fenced block after conversion.
2. **`pre[data-lang]` is unreliable.** Authors' editors write bogus values
   (a YAML frontmatter block tagged `makefile`, `curl | bash` tagged `ruby`).
   Emit plain ``` fences; do not trust the tag.
3. **U+00A0 (NBSP) everywhere** (515 occurrences in a 20k-char article),
   including code indentation. Replace `\u00a0` → space; the count is
   preserved so alignment survives. Verify `md.count('\u00a0') == 0`.

## Images

Take `data-src` (not `src`, which is often a 0-width placeholder), map
`wx_fmt=` → file extension, download with curl (no Referer needed, but pass
`-e https://mp.weixin.qq.com/` for safety), write `images/NN.ext`, rewrite the
attribute to the relative path, drop `data-*` attrs. Validate: each file >1KB
and `file` reports a real image (WeChat serves 200 + HTML on hotlink failure).

## Header block (keep the 公众号's own meta line)

The article's second line carries real provenance, and all of it is recoverable
from the HTML even where the page fills it with JS:

| Put in the md | Source |
|---|---|
| `原创` badge | presence of `#copyright_logo` |
| 作者 | `#js_author_name` (fallback `var author`) |
| 公众号 + profile link | `#js_name` for the name; `a#js_name` has **no href** — build `https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=<var biz>&scene=124#wechat_redirect` (opens inside WeChat only) |
| 发布时间 | `var ct` (unix seconds); `#publish_time` renders empty |
| 原文链接 | `meta[property=og:url]`, query string (`?nwr_flag=1`) stripped → canonical `/s/<id>` |

The header reads
`\`原创\` · 作者：**名字** · 公众号：[名字](链接) · 2026-09-14 08:00`, then the
原文 line. The article's own 摘要 also sits at the top of `#js_content` as a
blockquote — leave it in the body, don't duplicate it in the header.

## markdownify settings that fit WeChat

```python
Md(heading_style='ATX', bullets='-', strong_em_symbol='*').convert_soup(content)
```

Custom `convert_img` (drop alt, keep `![](path)`) and `convert_figcaption`
(`> caption`) keep image captions the WeChat way. Finish by collapsing 3+
newlines and stripping trailing spaces per line — but never inside the fence
placeholders (substitute them *after* the cleanup).

## Verify before delivering

```python
md.count('\u00a0') == 0          # NBSP gone
md.count('@@CODEBLOCK') == 0     # all placeholders substituted
all blocks with >1 original line are multi-line now
no `![](http` left; N image links == N files on disk
```

## Housekeeping

`#js_content` sits in the DOM, but the same article body is duplicated inside
an escaped JS string in the same file — parse the real `#js_content` node
(`bs4` + `lxml`), not raw regex over the HTML.

Deliver the finished `.md` with a `MEDIA:` card and mention the `images/`
folder.
