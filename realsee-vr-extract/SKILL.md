---
name: realsee-vr-extract
description: Extract Beike/realsee VR house photos, panoramas, videos.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [realsee, beike, 贝壳, panorama, 360, vr, real-estate, cubemap, equirectangular, ffmpeg]
    category: media
---

# Realsee VR Extract Skill

Downloads 360° VR panoramas, photos, and videos from Beike/贝壳 (realsee.com/ke) house-listing
VR pages. Converts the per-observation-point cube-face images into single equirectangular
360° photos, and can generate a local drag-to-view web viewer. Also covers the general
cubemap→equirectangular technique and macOS 360° viewing quirks.

## When to Use

- User shares a `https://open.realsee.com/ke/...` or `realsee.com/ke/...` link and wants the
  house's photos / panorama / video saved.
- User shares a Beike mini-program link (`#小程序://贝壳找房...`). That code is NOT decodable
  client-side (see Pitfalls) — ask for a web link instead (the app's 复制链接 gives the realsee URL).
- Any 6-face cubemap source needs converting to an equirectangular 360° image.

## Prerequisites

- `ffmpeg` with the `v360` filter (`ffmpeg -filters | grep v360`). No avif decoder needed.
- `terminal` + `curl`/`python3`. No API keys.

## How to Run

```bash
python3 scripts/realsee_download.py "https://open.realsee.com/ke/<workCode>/<token>/" ~/Downloads/<小区名>
```

Or follow the manual procedure below. Read `references/realsee-page-structure.md` for the exact
JSON paths, URL patterns, and the verified ffmpeg commands.

## Quick Reference

| Step | Action |
|------|--------|
| Fetch page | `curl -s -A "Mozilla/5.0" <url>` → HTML |
| Extract data | JSON is inside an HTML comment, key `firstscreen` |
| House fields | `firstscreen.houseInfo` → title / houseCode / area / price / multimedia |
| Videos | `houseInfo.multimedia[type=video].list[].url` → direct `.mp4` on `video.ljcdn.com` |
| Faces | `defaultWork.panorama.list[i].{front,back,left,right,up,down}` → `.avif` URLs |
| Convert avif | append `?imageMogr2/format/jpg` (Tencent COS) — ffmpeg cannot decode avif |
| Synthesize | `ffmpeg -i right -i left -i up -i down -i front -i back -filter_complex "[0..5]hstack=6[c];[c]v360=c6x1:e" out.jpg` |
| Verify | compare against `defaultWork.picture_url` (official cover) |
| Floor plans | `defaultWork.hierarchy_floor_plan[].url` (jpeg) + `outline_floor_plan[].url` (png) — 2 floors |
| Room labels | vision-OCR the floor-plan jpegs → official room names (卧室A/B/C/D, 卫生间A/B/C/D, 厨房, 餐厅, 客厅, 衣帽间, 过道) — authoritative, far better than guessing rooms from photos |
| 3D model | `defaultWork.model.file_url` (`.at3d`) + `material_base_url` + `material_textures[]` |

## Procedure

1. **Fetch the page** with a browser UA string. The whole dataset is server-rendered into an
   HTML comment — no JS execution needed.
2. **Extract the JSON**: find the substring `"firstscreen"`, then the nearest enclosing
   `<!--` (search backward) and `-->` (search forward), `json.loads` the slice.
3. **Read the media** you need (see reference for full paths):
   - house video/images → `houseInfo.multimedia[]`
   - N observation points (N = `panorama.count`) → `defaultWork.panorama.list[]` (6 cube faces each) and
     `defaultWork.observers[]` (position / floor_index / visible_nodes).
4. **Download faces** with `?imageMogr2/format/jpg` appended (jpg ≈ 270 KB/face vs 1.8 MB png).
5. **Synthesize equirectangular** per point with the v360 command above. **Face order is
   critical** — see Pitfalls.
6. **Verify orientation** against the official cover (`defaultWork.picture_url`) before batch
   processing — it is the ground-truth "correct" perspective.
7. **Optional viewer**: a three.js sphere viewer (`templates/viewer.html`) served via
   `python3 -m http.server 8090 --bind 127.0.0.1`, opened with `open_preview` or a one-click
   `.command` script. Drop `three.min.js` (r128, from
   `cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js`) into the same folder as the
   viewer and the panoramas.

## Pitfalls

- **Face order is `right,left,up,down,front,back` — do NOT swap left/right.** v360 `c6x1` default
  `in_forder=rludfb` = `right,left,up,down,front,back`, and realsee's `left`/`right` faces match
  this convention directly (NO swap). hstack order `right,left,up,down,front,back` gives
  yaw=0→front, yaw=90→right, yaw=-90→left, yaw=180→back, all correct (verified via pixel
  correlation against the source face images). Swapping to `left,right,...` produces a
  left-right *swapped* panorama — the user reports "左边中间和右边中间对调". Also up/down faces
  need NO rotation: v360 places up above front and down below front (confirmed by the
  `vf_v360.c` ASCII diagram and edge-pixel correlation). A "mirror" report is usually a
  drag-direction bug in the viewer, NOT an image-orientation bug — verify with pixels before
  touching face order.
- **`#小程序://` links are not plain base64** (tried std/urlsafe + rotated alphabets; payload is
  compressed/encrypted client-side). Do not burn time decoding — ask the user for the web link.
- **ke.com / lianjia.com listing pages redirect to a captcha** (`hip.ke.com/captcha`). The
  realsee VR page already embeds everything you need — use it, don't fight the captcha.
- **ffmpeg has no avif decoder** (`ffmpeg -decoders | grep avif` → 0). Convert server-side with
  `?imageMogr2/format=jpg|png` (Tencent Cloud COS supports it).
- **v360 `yaw`/`pitch`/`roll` do NOT support per-frame `t` expressions** (only `h_fov`/`v_fov`
  do). For animated pan, wrap the equirectangular: `[0]hstack=2[ee];[ee]crop=W:H:x='t*speed':y=0[rot];[rot]v360=e:flat:yaw=0:...`. `yaw` range is `[-180,180]` — normalize any out-of-range value into this range.
- **`model.file_url` is a proprietary `.at3d` binary** (magic `01 00 00 00`, size u32 follows) — NOT glTF/zip/OBJ/PLY. No open parser exists, so it cannot be converted to `.glb`/`.obj`. Save it verbatim (plus the `material_textures[]` jpgs) and tell the user it only opens in Beike's app 「三维模型」 mode. Don't sink time into reverse-engineering the mesh.
- **Room labels come from the floor-plan images, not the `.at3d`.** OCR `hierarchy_floor_plan[].url` with `vision_analyze` (vision IS reliable for reading room-name text, just not for orientation). The floor plan gives the official per-room names + areas (㎡); map the observation points (count varies per listing) onto those names using `observers[].position` + the OCR'd layout. This beats guessing rooms from panorama thumbnails.
- **Generated equirectangular jpgs lack GPano XMP metadata** → macOS Preview/Quick Look shows
  them as a stretched strip, NOT an interactive 360. Only a real panorama viewer (phone album,
  FSPViewer, or a three.js viewer) pans them.
- **`file://` WebGL viewers fail (white screen)** — browser CORS blocks local textures. Serve via
  `python3 -m http.server` and open `http://127.0.0.1:PORT/viewer.html`; ship a `.command`
  one-click launcher.
- **Drag direction:** `lon += dx` (not `-=`) gives the "grab the scene" feel (drag right → look
  left) that matches phone-album 360 convention.
- **Do NOT trust `vision_analyze` for mirror/rotation judgment.** This session it reported
  "文字正向、无镜像" for a WRONG (`left,right`) face order, and reported "旋转错位" for the
  up/down pole region that was actually just `pitch≈±85` perspective distortion (up/down faces
  needed no rotation). Vision is fine for *labeling* rooms but unreliable for orientation —
  always confirm orientation with the pixel-correlation method in Verification.
- **Field shapes vary across listings.** `observers[].position` is a list `[x,y,z]` on some
  houses and a dict `{x,y,z}` on others — read both (e.g. `p[0]` vs `p['x']`). `houseInfo.detail.data[]`
  uses `title`/`content` keys, NOT `label`/`value` — the wrong keys silently empty the 详情 block.
  `house_layout` may be a dict or a JSON string. Single-storey houses have all
  `observers[].floor_index == 0` and only ONE floor plan (`hierarchy_0`, no `_1`).
- **Floor-plan filename collision:** naming from `url.split('_')[0]` maps both `hierarchy_0` and
  `hierarchy_1` to "hierarchy", so the second overwrites the first (you get 2 files instead of 4).
  Extract the floor digit with `re.search(r'hierarchy_(\d)', url)` → 0=一层 / 1=二层.
- **`vision_analyze` is intermittently down** ("This model does not support image") and this user
  prefers NOT relying on it. For room labels when vision is unavailable, map observation points
  onto floor-plan rooms using `observers[].position` coordinates + the OCR'd layout +
  `house_layout` counts (data-driven). When reusing a viewer template for another house, remember
  to rewrite ROOM_NAMES AND the scene loop (count + floor-index boundary) — copying the HTML
  alone leaves the previous house's labels.
- **Output-folder convention (this user):** name each house `贝壳-<小区名>-<houseCode>` and always
  write a `房源信息.json` (title / houseCode / 户型结构 / 详情 from `detail.data[].{title,content}`).
  Single-storey: drop the "第N层" suffix in the viewer label — only multi-storey keeps it.

## Verification

- `file` each downloaded face → valid JPEG.
- **Objective orientation check (pixel correlation — the authoritative method).** Extract a flat
  view and correlate it against the source face image; correct orientation gives 正序 ≈ +0.99,
  mirrored ≈ +0.08:
  ```bash
  ffmpeg -y -i out.jpg -vf "v360=e:flat:yaw=0:pitch=0:h_fov=90:v_fov=90:w=2048:h=2048" v0.png
  ffmpeg -y -i v0.png -f rawvideo -pix_fmt gray v0.raw
  ffmpeg -y -i front.jpg -vf scale=2048:2048 -f rawvideo -pix_fmt gray front.raw
  # python3: correlate v0.raw vs front.raw (正序) and vs horizontally-mirrored front.raw;
  # yaw=0 should be front (正序≈+0.99), yaw=90→right, yaw=-90→left, yaw=180→back.
  ```
  Seam-continuity check: adjacent rows/columns at the up/front and front/down boundaries should
  correlate >0.9. This catches both face-order swaps and (indirectly) face-rotation errors
  without any vision model.
- Serve the viewer over HTTP and confirm `viewer.html`, the JS, and one panorama all return 200.

## References

- `references/realsee-page-structure.md` — exact JSON paths, URL patterns, verified ffmpeg commands.
- `scripts/realsee_download.py` — fetch + download faces + synthesize all panoramas in one run.
- `templates/viewer.html` — three.js 360° viewer (drag to rotate, wheel zoom, scene switcher).
