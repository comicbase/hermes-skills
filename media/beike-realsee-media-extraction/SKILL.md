---
name: beike-realsee-media-extraction
description: Use when saving media from 贝壳/链家/如视(realsee) listings.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [web-scraping, real-estate, 贝壳, 链家, realsee, vr, media-download, ffmpeg]
    category: media
    related_skills: [blocked-page-recovery, youtube-content]
---

# 贝壳/链家/如视房源媒体提取 Skill

从贝壳找房/链家/如视(realsee)房源里，把**图片、视频、360°VR全景照片**下载到本地。覆盖：贝壳小程序分享链接 → 定位房源 → 抓取如视VR页内嵌数据 → 下载媒体。不做：录屏VR漫游视频（那是另一类任务）。

## When to Use

- 用户发来贝壳/链家/如视房源链接（小程序 `#小程序://` 链接、`open.realsee.com` 链接、或房源详情页链接），要「保存视频/图片/全景」。
- 需要从贝壳房源页提取可下载的媒体文件（mp4 / jpg / 全景图）。

## Prerequisites

- `curl` + `ffmpeg`（`ffmpeg -filters | grep v360` 应命中 `v360`，用于立方体贴图→全景图合成）。
- 终端有外网访问能力（`curl -sI https://ke.com` 返回 200/302 即正常）。
- **无需** avif 解码器（用 CDN 的 imageMogr2 服务端转码，见下）。

## How to Run

```bash
# 通用脚本：给定 realsee 链接，下载视频/图片/6面原始图 + 合成360°全景照(每观察点1张，N=panorama.count)
python3 scripts/download_realsee_media.py "https://open.realsee.com/ke/<workCode>/<token>/"
```

## Quick Reference

| 需求 | 做法 |
|---|---|
| 微信小程序链接解码 | **不可解**（客户端私有编码，非普通 base64），直接向用户要网页链接 |
| 贝壳/链家详情页 | 有验证码（302 → `hip.ke.com/captcha`），别硬爬 |
| 免验证码入口 | **如视VR链接** `open.realsee.com/ke/<workCode>/<token>/`，贝壳小程序「复制链接」给的就是它 |
| 内嵌数据 | 页面 HTML 注释 `<!-- {"firstscreen":{...},"configure":{...},"viewports":{...}} -->` |
| 视频 URL | `firstscreen.houseInfo.multimedia[].list[].url` → `http://video.ljcdn.com/resblock-video/*.mp4` |
| 图片 URL | `ke-image.ljcdn.com/hdic-resblock/*.jpg` |
| 全景图 URL | `defaultWork.panorama.list[].{front,back,left,right,up,down}` → `.../cube_2048/{i}/{hash}/{i}_{face}.avif` |
| avif→jpg/png | URL 追加 `?imageMogr2/format/jpg`（腾讯云 COS 服务端转码） |
| 6面→360°全景 | ffmpeg `v360=c6x1:e`，面顺序 `rludfb` |
| 全景→普通透视 | ffmpeg `v360=c6x1:flat:yaw=0:pitch=0:h_fov=100:v_fov=59` |

## Procedure

1. **拿到链接**。用户给 `#小程序://贝壳找房…/xxx` 时：这是微信私有编码（base64 解码得到二进制，不是可读路径），别浪费时间暴力破解——直接请用户改用「贝壳App/网页版→分享→复制链接」，或贴 `open.realsee.com/ke/...` 链接。

2. **抓取如视VR页**（免验证码）。`curl -s "<realsee_url>" -A "<UA>" -H "Accept-Language: zh-CN,zh;q=0.9" -o page.html`。贝壳/链家详情页(`xm.ke.com`/`xm.lianjia.com`)会 302 到 `hip.ke.com/captcha`，**不要**去碰，直接走 realsee 链接。

3. **解析内嵌 JSON**。HTML 里 `<!-- {...} -->` 注释含完整数据，用正则定位 `"firstscreen"` 再取外层 `<!--`…`-->`，`json.loads`。关键字段：
   - `firstscreen.houseInfo`：`title`、`houseCode`、`cityId`、`area`、`detail.data[]`(售价/户型/面积/朝向…)、`multimedia[]`(视频/图片)。
   - `firstscreen.defaultWork`：`panorama.list[]`(每个观察点6面图)、`observers[]`(position/quaternion/floor_index/visible_nodes)、`initial`、`model`(3D文件)、`hierarchy_floor_plan`(户型图)。
   - 详见 `references/realsee-data-structure.md`。

4. **下载媒体**。视频/图片直接 `curl`（视频要带 `Referer`）；全景 6 面 avif 用 `?imageMogr2/format/jpg` 转码后下载。

5. **合成 360° 全景图**（可选，一张看全房间）。ffmpeg v360，**面顺序必须是 `rludfb`**（right,left,up,down,front,back），即把 realsee 的 `front/back/left/right/up/down` 重排为 `right,left,up,down,front,back`：
   ```bash
   ffmpeg -y -i right.jpg -i left.jpg -i up.jpg -i down.jpg -i front.jpg -i back.jpg \
     -filter_complex "[0][1][2][3][4][5]hstack=6[c];[c]v360=c6x1:e" -q:v 3 out.jpg
   ```

6. **验证方向**（务必做）。从全景图提取一张正面透视看是否正常（文字正向、墙竖直、地面水平、无镜像）：
   ```bash
   ffmpeg -y -i out.jpg -vf "v360=e:flat:yaw=0:pitch=0:h_fov=100:v_fov=80:w=1200:h=900" check.png
   ```
   用 `vision_analyze` 看 `check.png`；文字反向/墙歪/镜像 → 调面顺序或 `in_frot`。

## Pitfalls

- **`v360` 的 `yaw/pitch/roll` 不支持每帧 `t` 表达式**（报 `Undefined constant or missing '(' in 't/5.0'`）——只有 `h_fov/v_fov/d_fov` 支持 `t`。要做旋转动画，用 `hstack=2` 复制全景图 + 动态 `crop=x='t*speed'` 做 wrap-around 平移，再 `v360=e:flat:yaw=0` 提取。
- **本机 ffmpeg 可能没有 avif 解码器**（`ffmpeg -decoders | grep avif` 为空）。别本地转码，用 CDN `?imageMogr2/format/jpg|png` 服务端转。
- **ffmpeg 可能没编 `drawtext`**（`No such filter`）。调试别依赖它打时间戳。
- **视频 URL 是 `http://` 不是 `https://`**，且需带 `Referer: https://open.realsee.com/` 才 200。
- **realsee 页面里的视频是「小区视频」**（楼体外观/楼梯间/门禁/电梯间/停车场，标题在 `multimedia[].list[].title`），不是房源室内实拍。室内视频（如有）在验证码保护的详情页里。先向用户澄清要哪种，别默认。
- **全景图是 equirectangular 投影**（宽:高=2:1 长条图），电脑普通看图软件显示为拉长图是正常现象；手机相册/微信能识别成 360° 拖动观看。
- 合成全景图本质是「拼接」；若用户明确说「不用拼接、只要原始照片」，就只下 6 面原始图（每个观察点 front/back/left/right/up/down 六张），不要自作主张合成。

## Verification

- 下载完成：用 `search_files target='files'` 核对文件数（N 个观察点 = N 张全景 + N×6 张面图，N=panorama.count）与大小。
- 全景图方向：**优先用像素相关度客观验证，别只信 vision**（vision 会把错误的 left,right 面顺序判成"文字正向无镜像"，也会把 `pitch≈±85` 的极点透视畸变误判成"旋转错位"）。提取 `v360=e:flat:yaw=0:pitch=0:h_fov=90:v_fov=90:w=2048:h=2048` 透视图转灰度 raw，与原始面图 front/right/left/back 做正序/镜像相关度：正确方向正序≈+0.99、镜像≈+0.08；yaw=0→front、yaw=90→right、yaw=-90→left、yaw=180→back。接缝连续性（up/front、front/down 交界相邻行列相关度>0.9）也可辅助判断面旋转。
- 视频可用性：`file *.mp4` 应显示 `ISO Media, MP4 Base Media`；`curl -o /dev/null -w "%{http_code}"` 应 200。
