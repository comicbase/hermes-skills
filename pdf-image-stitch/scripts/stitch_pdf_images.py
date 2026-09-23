#!/usr/bin/env python3
"""PDF 内嵌图裁剪拼接：probe / extract / stitch 三个子命令。

设计要点（详见 SKILL.md）：
  * 直接抽内嵌原始流，不渲染页面（渲染会按 72dpi 降质）
  * 裁剪在解码后的像素域做 —— 无损；损失只来自最后那一次编码
  * 输出默认 JPEG，质量/色度采样默认对齐源图，只编码一次

依赖：pymupdf（取图）+ pillow（裁剪/拼接/编码）
  uv run --with pymupdf --with pillow python stitch_pdf_images.py ...
"""
from __future__ import annotations

import argparse
import io
import math
import os
import sys
from fractions import Fraction


# ---------------------------------------------------------------------------
# JPEG 头解析：判定色度采样，避免不必要地升采样（体积翻倍、肉眼无差）
# ---------------------------------------------------------------------------
_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def jpeg_sampling(data: bytes):
    """返回 '444' / '422' / '420' / '440'，或 None（非 JPEG / 解析失败）。"""
    i, n = 2, len(data)
    while i + 1 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        m = data[i + 1]
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        if m == 0xDA or i + 4 > n:  # 熵编码开始，SOF 必在前面
            return None
        seglen = int.from_bytes(data[i + 2:i + 4], "big")
        if m in _SOF and i + 10 <= n:
            ncomp = data[i + 9]
            comps = [(data[i + 11 + 3 * k] >> 4, data[i + 11 + 3 * k] & 0x0F) for k in range(ncomp)]
            if not comps:
                return None
            h, v = comps[0]
            return {(1, 1): "444", (2, 1): "422", (2, 2): "420", (1, 2): "440"}.get((h, v), f"{h}x{v}")
        i += 2 + seglen
    return None


SAMPLING_CODE = {"444": 0, "422": 1, "420": 2}


# ---------------------------------------------------------------------------
# PDF 取图
# ---------------------------------------------------------------------------
def _safe(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception as exc:  # 个别图没有可用 bbox
        return f"<{type(exc).__name__}>"


def open_doc(path):
    import pymupdf

    return pymupdf.open(path)


def page_images(doc, pno):
    """该页所有内嵌图，按像素数降序。"""
    page = doc[pno]
    out = []
    for info in page.get_images(full=True):
        got = doc.extract_image(info[0])
        out.append({
            "xref": info[0],
            "ext": got["ext"],
            "data": got["image"],
            "width": got["width"],
            "height": got["height"],
            "colorspace": got.get("colorspace"),
            "bpc": got.get("bpc"),
            "bbox": _safe(page.get_image_bbox, info),
        })
    out.sort(key=lambda d: d["width"] * d["height"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# 内容行区间 / 边界框（纯 PIL，无需 numpy）
# ---------------------------------------------------------------------------
def _binary(im, thresh=245):
    return im.convert("L").point(lambda p: 255 if p < thresh else 0)


def row_profile(im, thresh=245):
    """每行「暗像素占比」0..255 的列表。"""
    from PIL import Image

    g = _binary(im, thresh)
    col = g.resize((1, g.height), Image.BOX)
    return [col.getpixel((0, y)) for y in range(col.height)]


def col_profile(im, thresh=245):
    from PIL import Image

    g = _binary(im, thresh)
    row = g.resize((g.width, 1), Image.BOX)
    return [row.getpixel((x, 0)) for x in range(row.width)]


def span(profile, floor=1.5, margin=0):
    """内容区间。两道抗干扰措施：
    * floor —— 绝对阈值（0-255 的占比刻度）。噪点行/列的值在 0.5 以下，
      真实内容（哪怕只有几行文字的稀疏列）也在 1-3 以上，分界很干净。
      用「最大值的百分比」当阈值反而会用密集区域把稀疏的真内容滤掉。
    * margin —— 两端排除若干行/列。扫描件四周的边框线/装订阴影是满行满列的黑，
      任何占比阈值都推不掉，只能靠排除边缘。
    """
    n = len(profile)
    lo, hi = margin, max(margin, n - margin)
    sub = profile[lo:hi]
    if not sub or max(sub) <= floor:
        return None
    rows = [i + lo for i, v in enumerate(sub) if v > floor]
    return (rows[0], rows[-1]) if rows else None


def content_box(im, thresh=245, floor=1.5, edge=0.015):
    """内容边界框 (x0,y0,x1,y1)，行/列各取内容区间，并排除四周 edge 比例的边缘。"""
    ry = span(row_profile(im, thresh), floor, margin=int(im.height * edge))
    cx = span(col_profile(im, thresh), floor, margin=int(im.width * edge))
    if not ry or not cx:
        return None
    return (cx[0], ry[0], cx[1] + 1, ry[1] + 1)


# ---------------------------------------------------------------------------
# 位置解析：比例用 Fraction 精确换算，也支持像素行号
# ---------------------------------------------------------------------------
def parse_pos(tok, total):
    tok = str(tok).strip().lower()
    if tok in ("top", "start"):
        return 0
    if tok in ("bottom", "end"):
        return total
    if tok.endswith("px"):
        return int(tok[:-2])
    if tok.endswith("%"):
        return int(Fraction(tok[:-1]) / 100 * total + Fraction(1, 2))
    return int(Fraction(tok) * total + Fraction(1, 2))


def parse_part(spec, doc):
    bits = str(spec).split(":")
    if len(bits) != 3:
        raise SystemExit(f"--part 写法应为 页号:起点:终点，收到 {spec!r}")
    pno = int(bits[0])
    if not 0 <= pno < doc.page_count:
        raise SystemExit(f"页号 {pno} 超出范围（共 {doc.page_count} 页）")
    return pno, bits[1], bits[2]


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------
def cmd_probe(args):
    from PIL import Image

    doc = open_doc(args.pdf)
    print(f"{args.pdf}: {doc.page_count} 页")
    for pno in range(doc.page_count):
        page = doc[pno]
        print(f"\n第 {pno} 页  页面框 {page.rect.width:.0f}x{page.rect.height:.0f}pt（渲染尺寸，非原图尺寸）")
        imgs = page_images(doc, pno)
        if not imgs:
            print("  （无内嵌图 —— 文字型页面，别用本技能）")
            continue
        for k, meta in enumerate(imgs):
            line = (f"  [{k}] xref={meta['xref']} {meta['width']}x{meta['height']} {meta['ext']}"
                    f" {meta['colorspace']}/{meta['bpc']}bit {len(meta['data'])/1024:.0f}KB")
            sampling = jpeg_sampling(meta["data"]) if meta["ext"] == "jpeg" else None
            if sampling:
                line += f" 采样={sampling}"
            print(line)
            if meta["bbox"] is not None and not isinstance(meta["bbox"], str):
                print(f"      页内位置 {meta['bbox']}")
            pil = Image.open(io.BytesIO(meta["data"])).convert("RGB")
            H, W = pil.height, pil.width
            scale = min(1.0, 1024 / W)
            small = pil.resize((max(1, int(W * scale)), max(1, int(H * scale))))
            prof = row_profile(small)
            srow = span(prof, margin=int(small.height * 0.015))
            sbox = content_box(small)
            kx, ky = W / small.width, H / small.height
            if srow:
                a, b = srow[0] / small.height, (srow[1] + 1) / small.height
                print(f"      内容行区间 {srow[0]}–{srow[1]}/{small.height} 即 {a:.1%}–{b:.1%}"
                      f" → 像素行 {int(a*H)}–{int(b*H)}")
            if sbox:
                x0, y0, x1, y1 = [int(round(v)) for v in
                                  (sbox[0] * kx, sbox[1] * ky, sbox[2] * kx, sbox[3] * ky)]
                print(f"      内容框 x {x0}–{x1} y {y0}–{y1}（宽 {x1-x0} 高 {y1-y0}）→ "
                      f"占全图 {x0/W:.0%}–{x1/W:.0%} / {y0/H:.0%}–{y1/H:.0%}")
            band = max(1, small.height // 20)
            occ = [sum(prof[i:i + band]) for i in range(0, small.height, band)]
            print("      每 5% 高度内容量: " + " ".join(str(int(v)) for v in occ))
    return 0


def cmd_extract(args):
    doc = open_doc(args.pdf)
    os.makedirs(args.outdir, exist_ok=True)
    n = 0
    for pno in range(doc.page_count):
        for k, meta in enumerate(page_images(doc, pno)):
            if k and not args.all:
                continue
            fn = os.path.join(args.outdir, f"p{pno}_{k}.{meta['ext']}")
            with open(fn, "wb") as fh:
                fh.write(meta["data"])
            print(f"{fn}  {meta['width']}x{meta['height']}  {len(meta['data'])/1024:.0f}KB（原字节，无重编码）")
            n += 1
    print(f"共 {n} 个文件")
    return 0


def cmd_stitch(args):
    from PIL import Image

    doc = open_doc(args.pdf)
    pieces, notes, src_sampling = [], [], None

    for spec in args.part:
        pno, s_tok, e_tok = parse_part(spec, doc)
        imgs = page_images(doc, pno)
        if not imgs:
            raise SystemExit(f"第 {pno} 页没有内嵌图")
        if args.index >= len(imgs):
            raise SystemExit(f"第 {pno} 页只有 {len(imgs)} 张内嵌图，--index {args.index} 不存在")
        meta = imgs[args.index]
        pil = Image.open(io.BytesIO(meta["data"])).convert("RGB")
        H = pil.height
        y0, y1 = parse_pos(s_tok, H), parse_pos(e_tok, H)
        y0, y1 = max(0, min(H, y0)), max(0, min(H, y1))
        if y1 <= y0:
            raise SystemExit(f"{spec}: 起点 {y0} 不小于终点 {y1}")
        piece = pil.crop((0, y0, pil.width, y1))
        note = ""
        if args.trim:
            sw = min(1000, piece.width)
            small = piece.resize((sw, max(1, int(piece.height * sw / piece.width))))
            bb = content_box(small)
            if bb:
                k = piece.width / small.width
                box = tuple(int(round(v * k)) for v in bb)
                piece = piece.crop(box)
                note = f"  trim={box}"
        if args.gap_pad:
            piece = _pad(piece, args.gap_pad)
        pieces.append(piece)
        notes.append(f"第{pno}页 行 {y0}-{y1} → {piece.width}x{piece.height}{note}")
        if src_sampling is None and meta["ext"] == "jpeg":
            src_sampling = jpeg_sampling(meta["data"])

    width = max(p.width for p in pieces)
    height = sum(p.height for p in pieces) + args.gap * max(0, len(pieces) - 1)
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    y = 0
    for p in pieces:
        canvas.paste(p, (_align(args.align_x, width, p.width), y))
        y += p.height + args.gap

    print("拼接组成（自上而下）：")
    for n in notes:
        print("  " + n)
    if any(p.width != width for p in pieces):
        print("  注意：各部分宽度不一致，已补白对齐")

    out = args.out
    if args.png or out.lower().endswith(".png"):
        if not out.lower().endswith(".png"):
            out = os.path.splitext(out)[0] + ".png"
        canvas.save(out, optimize=True)
        enc = "PNG（无损容器，体积大）"
    else:
        if not os.path.splitext(out)[1]:
            out += ".jpg"
        sampling_name = args.sampling if args.sampling != "auto" else (src_sampling or "444")
        canvas.save(out, "JPEG", quality=args.quality,
                    subsampling=SAMPLING_CODE.get(sampling_name, 0),
                    optimize=True, progressive=True)
        enc = f"JPEG q{args.quality} 采样={sampling_name}（源图 {src_sampling or '非 JPEG'}）"

    print(f"输出 {out}\n  {canvas.width}x{canvas.height}  {os.path.getsize(out)/1024:.1f}KB  {enc}")

    if args.verify:
        buf = io.BytesIO()
        canvas.save(buf, "PNG")
        ref = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
        got = Image.open(out).convert("RGB")
        from PIL import ImageChops, ImageStat

        diff = ImageChops.difference(ref, got)
        rms = ImageStat.Stat(diff).rms
        mse = sum(v * v for v in rms) / len(rms)
        psnr = 20 * math.log10(255 / math.sqrt(mse)) if mse > 0 else 99.0
        mx = max(ImageStat.Stat(diff).extrema[c][1] for c in range(3))
        print(f"  校验 PSNR {psnr:.2f} dB  最大单像素偏差 {mx}"
              f"（实测参考：白底扫描件 53dB/31，密排文字 38dB/42，都肉眼无差；"
              f"异常信号是 max>80 或 PSNR<30）")
    return 0


def _pad(im, pad):
    from PIL import Image

    out = Image.new("RGB", (im.width + 2 * pad, im.height + 2 * pad), (255, 255, 255))
    out.paste(im, (pad, pad))
    return out


def _align(kind, width, w):
    if kind == "left":
        return 0
    if kind == "right":
        return width - w
    return (width - w) // 2


def main(argv=None):
    ap = argparse.ArgumentParser(description="PDF 内嵌图裁剪拼接（裁剪无损，只编码一次）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="列出每页内嵌图与内容行区间")
    p.add_argument("pdf")
    p.set_defaults(func=cmd_probe)

    e = sub.add_parser("extract", help="按原字节导出内嵌图（零重编码）")
    e.add_argument("pdf")
    e.add_argument("-o", "--outdir", required=True)
    e.add_argument("--all", action="store_true", help="导出每页所有内嵌图（默认只导最大的那张）")
    e.set_defaults(func=cmd_extract)

    s = sub.add_parser("stitch", help="裁剪并堆叠成一张图")
    s.add_argument("pdf")
    s.add_argument("-p", "--part", action="append", required=True,
                   help="页号:起点:终点，可重复；自上而下堆叠")
    s.add_argument("-o", "--out", required=True)
    s.add_argument("--quality", type=int, default=90)
    s.add_argument("--sampling", default="auto", choices=["auto", "444", "422", "420"],
                   help="色度采样，默认沿用源图")
    s.add_argument("--png", action="store_true", help="输出无损 PNG（体积大，仅按需）")
    s.add_argument("--trim", action="store_true", help="每部分先裁到内容边界框")
    s.add_argument("--gap", type=int, default=0, help="部分之间的白边行数")
    s.add_argument("--gap-pad", type=int, default=0, help="每部分四周补白像素")
    s.add_argument("--index", type=int, default=0, help="每页用第几张内嵌图（默认最大那张）")
    s.add_argument("--align-x", choices=["center", "left", "right"], default="center")
    s.add_argument("--verify", action="store_true", help="与无损参考比对，打印 PSNR")
    s.set_defaults(func=cmd_stitch)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
