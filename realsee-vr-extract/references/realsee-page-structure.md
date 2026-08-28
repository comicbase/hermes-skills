# Realsee VR page — data structure & verified commands

Source: a Beike/贝壳 house VR page at `https://open.realsee.com/ke/<workCode>/<token>/`.
All data is server-rendered into an HTML comment. No JS/API needed.

## JSON extraction (python)

```python
import json
html = open('page.html', encoding='utf-8').read()
idx = html.find('"firstscreen"')
start = html.rfind('<!--', 0, idx)
end = html.find('-->', idx)
data = json.loads(html[start + 4:end].strip())
```

Top-level keys: `firstscreen`, `configure`, `viewports`.

## Key paths

| Path | Meaning |
|------|---------|
| `firstscreen.houseInfo.title` | e.g. `<小区名> 4室2厅` |
| `firstscreen.houseInfo.houseCode` | 12-digit Beike house code |
| `firstscreen.houseInfo.area` / `detail.data[]` | area / price / layout / city |
| `firstscreen.houseInfo.multimedia[i]` | `{type: video\|image, title, list: [{url, coverURL, title}]}` |
| `firstscreen.defaultWork.panorama` | `{base_url, count, list[]}` — N scenes (count varies per listing) |
| `firstscreen.defaultWork.panorama.list[i]` | `{front, back, left, right, up, down, index, size_list}` |
| `firstscreen.defaultWork.observers[i]` | `{index, floor_index, position, quaternion, visible_nodes}` |
| `firstscreen.defaultWork.initial` | `{longitude, latitude, fov, pano_index}` (radians) |
| `firstscreen.defaultWork.picture_url` | **official cover = ground-truth orientation for verification** |

`firstscreen.resblockInfo` = the community (小区) info: `detail.data[]` + `multimedia[]` (same media
as `houseInfo.multimedia`). `firstscreen.houseInfo.params` carries `workCode` / `platform` / `relationId`.

`multimedia[type=video]` entries are community (小区) videos, not house-interior — e.g.
`http://video.ljcdn.com/resblock-video/<ts>_<hash>_ke.mp4`. Download directly with a Referer header.

## URL patterns

- Face image (avif, 2048×2048):
  `https://vr-public.realsee-cdn.cn/release/auto3dhd/<hash>/images/cube_2048/<i>/<facehash>/<i>_<face>.avif`
  where `<face>` ∈ `b,d,f,l,r,u`.
- **avif → jpg/png (server-side, Tencent COS)**: append `?imageMogr2/format/jpg` (≈270 KB) or
  `?imageMogr2/format/png` (≈1.8 MB). ffmpeg has NO avif decoder.
- Official cover: `firstscreen.defaultWork.picture_url` (and `title_picture_url`).

## Cubemap → equirectangular (verified)

**Correct face order — right,left,up,down,front,back (NO swap):**

```bash
ffmpeg -y \
  -i right.jpg -i left.jpg -i up.jpg -i down.jpg -i front.jpg -i back.jpg \
  -filter_complex "[0][1][2][3][4][5]hstack=6[c];[c]v360=c6x1:e" \
  -frames:v 1 panorama_360.jpg
```

- v360 `c6x1` default `in_forder=rludfb` = right,left,up,down,front,back. Realsee's left/right
  match this directly (NO swap). Verified via pixel correlation.
- Output is 8192×4096 for 2048 cube faces.

## Orientation verification

Official cover (`picture_url`) is the correct perspective for
`initial.longitude` (radians). Convert to degrees and normalize into `[-180,180]`, then extract
the same perspective from your synthesized panorama and compare left/right layout:

```bash
ffmpeg -y -i panorama_360.jpg \
  -vf "v360=e:flat:yaw=<yaw>:pitch=<pitch>:h_fov=99:v_fov=59:w=1200:h=900" verify.png
```

(Convert `initial.longitude` radians → degrees, normalize into `[-180,180]`; `initial.latitude` → `pitch`.)

## Animated pan (v360 yaw is NOT per-frame)

`yaw`/`pitch`/`roll` reject `t` expressions ("Undefined constant ... in 't/5'"). For a rotating
scan, wrap the equirectangular then feed `v360=e:flat:yaw=0`:

```bash
ffmpeg -y -i panorama_360.jpg \
  -filter_complex "[0]hstack=2[ee];[ee]crop=8192:4096:x='t*546':y=0[rot];[rot]v360=e:flat:yaw=0:pitch=0:h_fov=100:v_fov=59:w=1920:h=1080[v]" \
  -map "[v]" -t 5 -r 30 -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p scan.mp4
```

`speed = 8192 × (degrees/360) / seconds`.
