"""Convert a public WeChat MP article (mp.weixin.qq.com/s/...) to Markdown.

Usage:
  uv run --quiet --with beautifulsoup4 --with lxml --with markdownify \
    python wx_mp_to_md.py <url> [outdir] [--no-images]

Writes <outdir>/<title>.md and <outdir>/images/NN.<ext>, with relative image links.
"""
import datetime
import html as htmllib
import json
import os
import re
import subprocess
import sys

from bs4 import BeautifulSoup
from markdownify import MarkdownConverter

NB = "\u00a0"
UA_PC = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
UA_WX = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
         "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1 MicroMessenger/8.0.49")


def http_get(url: str, ua: str = UA_PC, referer: str | None = None) -> str:
    cmd = ["curl", "-sSL", "--max-time", "60", "-A", ua]
    if referer:
        cmd += ["-e", referer]
    r = subprocess.run(cmd + [url], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def get_text(soup, sel, attr=None):
    el = soup.select_one(sel)
    if not el:
        return ""
    return (el.get(attr) or "").strip() if attr else el.get_text(" ", strip=True)


def slug(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]+', "-", s).strip()
    return re.sub(r"\s+", "-", s)[:80] or "article"


def extract_meta(page: str, soup, url: str) -> dict:
    meta = {
        "title": get_text(soup, "#activity-name"),
        "account": get_text(soup, "#js_name"),
        "author": get_text(soup, "#js_author_name"),
        "original": bool(soup.select_one("#copyright_logo")),
        "datetime": "",
        "url": "",
        "account_url": "",
    }
    # #publish_time is JS-filled and empty in the HTML; var ct is the real timestamp
    m = re.search(r'var ct = "(\d+)"', page)
    if m:
        meta["datetime"] = datetime.datetime.fromtimestamp(
            int(m.group(1))).strftime("%Y-%m-%d %H:%M")
    m = re.search(r'property="og:url"[^>]+content="([^"]+)"', page)
    meta["url"] = re.sub(r"\?.*$", "", htmllib.unescape(m.group(1))) if m else url
    # a#js_name carries no href; the account profile link is built from var biz
    m = re.search(r'var biz\s*=\s*"([^"]+)"', page)
    if m:
        meta["account_url"] = ("https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz="
                               f"{m.group(1)}&scene=124#wechat_redirect")
    return meta


def main() -> None:
    args = sys.argv[1:]
    flags = {a for a in args if a.startswith("--")}
    pos = [a for a in args if not a.startswith("--")]
    if not pos:
        sys.exit(__doc__)
    url = pos[0]

    page = http_get(url, UA_WX)
    if len(page) < 5000:
        sys.exit(f"fetch failed: {len(page)} bytes")
    soup = BeautifulSoup(page, "lxml")
    meta = extract_meta(page, soup, url)

    outdir = pos[1] if len(pos) > 1 else slug(meta["title"])
    imgdir = os.path.join(outdir, "images")
    os.makedirs(imgdir, exist_ok=True)

    content = soup.select_one("#js_content")
    if content is None:
        sys.exit("no #js_content: deleted, gated, or login-required article")
    for sel in ["script", "style", ".js_img_loading", "#js_pc_qr_code", ".reward_area"]:
        for el in content.select(sel):
            el.decompose()

    # --- images: download, rewrite to relative path ---
    images = []
    if "--no-images" not in flags:
        for i, img in enumerate(content.find_all("img"), 1):
            src = img.get("data-src") or img.get("src") or ""
            if not src:
                img.decompose()
                continue
            mm = re.search(r"wx_fmt=(\w+)", src)
            fname = f"{i:02d}.{mm.group(1) if mm else 'png'}"
            dest = os.path.join(imgdir, fname)
            subprocess.run(["curl", "-sSL", "--max-time", "60", "-A", UA_PC,
                            "-e", "https://mp.weixin.qq.com/", "-o", dest, src],
                           capture_output=True)
            images.append({"file": f"images/{fname}",
                           "ok": os.path.exists(dest) and os.path.getsize(dest) > 1000})
            img["src"] = f"images/{fname}"
            for a in ["data-src", "data-croporisrc", "data-backh", "data-backw",
                      "data-ratio", "data-w", "data-type"]:
                img.attrs.pop(a, None)

    # --- code blocks: one <code> child of <pre> == one line ---
    code_blocks = []
    for pre in list(content.select("pre")):
        wrapper = pre.find_parent("section", class_="code-snippet__fix") or pre
        lines = [c.get_text().replace(NB, " ").replace("\r", "").rstrip()
                 for c in (pre.find_all("code", recursive=False) or pre.find_all("code"))]
        if not lines:
            continue
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        idx = len(code_blocks)
        code_blocks.append("\n".join(lines))  # pre[data-lang] values are unreliable
        ph = soup.new_tag("p")
        ph.string = f"@@CODEBLOCK{idx}@@"
        wrapper.replace_with(ph)

    class Md(MarkdownConverter):
        def convert_img(self, el, text, parent_tags):
            return f"![]({el.get('src', '')})" if el.get("src") else ""

        def convert_figcaption(self, el, text, parent_tags):
            return f"\n\n> {text.strip()}\n\n" if text.strip() else ""

    body = Md(heading_style="ATX", bullets="-", strong_em_symbol="*").convert_soup(content)
    body = body.replace(NB, " ")
    for i, code in enumerate(code_blocks):
        fence = f"```\n{code}\n```"
        body = re.sub(r"@@CODEBLOCK%d@@" % i, lambda _m, f=fence: f, body)
    body = re.sub(r"\n{3,}(\S)", r"\n\n\1", body)
    body = re.sub(r"[ \t]+\n", "\n", body).strip()

    # --- header: 原创 / 作者 / 公众号(+link) / 时间 / 原文链接 ---
    head = []
    if meta["original"]:
        head.append("`原创`")
    if meta["author"]:
        head.append(f"作者：**{meta['author']}**")
    if meta["account"]:
        head.append(f"公众号：[{meta['account']}]({meta['account_url']})"
                    if meta["account_url"] else f"公众号：{meta['account']}")
    if meta["datetime"]:
        head.append(meta["datetime"])

    md = f"# {meta['title']}\n\n"
    md += (" · ".join(head) + "\n\n") if head else ""
    md += f"原文：[{meta['url']}]({meta['url']})\n\n{body}\n"
    out = os.path.join(outdir, f"{slug(meta['title'])}.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(md)

    print(json.dumps({"md": out, "title": meta["title"], "original": meta["original"],
                      "author": meta["author"], "account": meta["account"],
                      "datetime": meta["datetime"], "url": meta["url"],
                      "account_url": meta["account_url"], "chars": len(md),
                      "nb_left": md.count(NB), "tokens_left": md.count("@@CODEBLOCK"),
                      "code_blocks": len(code_blocks), "images": len(images),
                      "bad_images": [i for i in images if not i["ok"]]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
