---
name: wechat-miniprogram-media
description: Extract video from WeChat mini programs (no save button).
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [wechat, 微信, miniprogram, 小程序, video, media, cache, beike, 贝壳]
    category: media
---

# WeChat Mini Program Media Extraction

Mini programs often render video in a player with no save/download entry, and the
`#小程序://name/code` share link is an opaque server-side code. The working path: recover the
API the page actually called from WeChat Mac's webview cache, then call that API yourself.

## When to Use

- User sends a `#小程序://<name>/<code>` link and asks to save a video/photo.
- A mini program page shows media but has no save button and no long-press menu item.
- Not for 公众号 articles (use `wechat-mp-to-markdown`) or realsee VR pages (`realsee-vr-extract`).

## Prerequisites

- macOS with WeChat Mac logged in, and the mini program opened **on the Mac** (phone-only
  playback leaves nothing to inspect).
- Full Disk Access for the agent app: 系统设置 → 隐私与安全性 → 完全磁盘访问权限 → add Hermes →
  **quit and reopen the app**. Without it every read under
  `~/Library/Containers/com.tencent.xinWeChat/` fails with `Operation not permitted`.

## Procedure

1. Ask the user to open the page on the Mac and play the media to the end. Playback does **not**
   write a video file to disk — what you need is the page's API request in the cache.
2. Identify which applet ran (most recently modified package dir wins):
   ```bash
   ls -lt ~/Library/Containers/com.tencent.xinWeChat/Data/Documents/app_data/radium/users/*/applet/packages/ | head
   ```
3. Confirm the page name from the mini program log (proves the user opened it):
   ```bash
   grep -a "onLoad" <container>/Documents/app_data/radium/users/<userhash>/applet/local/<appid>/usr/miniprogramLog/log*
   ```
   New-style data lives under `Documents/app_data/radium/`; the older `.wxapplet/` tree is stale.
4. Harvest request URLs from the webview cache (bodies are encrypted, URLs are not):
   ```bash
   cd ~/Library/Containers/com.tencent.xinWeChat/Data/Documents/app_data/radium/web/profiles/webview_*/Cache/Cache_Data
   grep -aohE "https?://[!-~]+" * | sort -u > /tmp/wx_urls.txt
   grep -iE "player|video|content|media" /tmp/wx_urls.txt
   ```
5. Replay the endpoint posing as the mini program:
   - UA: a `MicroMessenger/8.x` iPhone UA
   - Referer: `https://servicewechat.com/<appid>/<version>/page-frame.html`
   - Paths under `gw-mp.api.ke.com` often answer **without** `sign`; `wxapp.api.ke.com` returns
     HTTP 418 until signed, so prefer whatever proxy host the page used.
6. Verify the payload belongs to the requested entity **before** downloading.
7. Download the best asset (`resource.origin` first, then `url`) with UA + Referer, then ffprobe.

## 实勘视频(贝壳)— 端到端实操

目标:拿到某套二手房在贝壳小程序「视频看房」里的实勘视频原片。全程不需要签名。

1. **让小程序在 Mac 上跑一遍**:微信 Mac 打开 `#小程序://贝壳找房…` 链接 → 进入房源 → 点视频.
   日志会留下 `page subpackages/mercy/pages/videoLanding/index onLoad` 行,可作为证据:
   ```bash
   grep -a "videoLanding" ~/Library/Containers/com.tencent.xinWeChat/Data/Documents/app_data/radium/users/*/applet/local/wxcfd8224218167d98/usr/miniprogramLog/log*
   ```
2. **从 webview 缓存捞 player/list URL**(响应体是加密的,URL 是明文):
   ```bash
   cd ~/Library/Containers/com.tencent.xinWeChat/Data/Documents/app_data/radium/web/profiles/webview_*/Cache/Cache_Data
   grep -aohE "https?://[!-~]+" * | sort -u | grep "content/xcx/player/list" | head
   ```
   这条 URL 里带着 `contentIds`、`contentList`、`openId`、`risk_data_id`——**照抄**即可.
3. **重放接口**(`sign` 被缓存截断没关系,`gw-mp` 代理不校验):
   ```bash
   python3 scripts/beike_shikan_video.py --url '<粘贴 player/list URL>' --house-code <houseCode>
   ```
4. **按 `placeCard.entityId` 认领房源**:`entityId` 必须等于 houseCode;`resblockName` 应是该小区.
   同一房源可能有多条实勘视频(时长/户型故事不同),先列清单让用户挑,再下载原片.
5. **下载原片**:优先 `video.resource.origin`(可能是 `.mov`,20+ Mbps,几百 MB),配 `Referer: https://m.ke.com/`:
   ```bash
   python3 scripts/beike_shikan_video.py --url '<...>' --house-code <houseCode> \
       --download 1 --out "~/HermesProjects/贝壳-<小区名>-<houseCode>/房源视频"
   ```
6. **校验**:`ffprobe` 的 duration/分辨率要等于接口返回的 `duration`/`width`×`height`;写一份
   `视频信息.json`(contentId、时长、分辨率、作者、origin 地址).

一次抓多条时先 `--download` 逐条执行,或改脚本循环;每条原片都可能 600 MB 级.

## Beike / 贝壳找房 specifics

- 小程序 appid: `wxcfd8224218167d98` (“贝壳找房丨二手房新房租房装修”).
- House video feed on the mercy proxy:
  ```
  https://gw-mp.api.ke.com/mercy_api/proxyApi/i.content.api.ke.com/content/xcx/player/list
    ?contentIds=<id1,id2>&contentList=<...>&friendShare=2&source=ershoudetail
    &openId=<openid>&agentId=&shareUcid=&preLook=false&pageNo=1&queryId=[]
    &env=weapp&risk_business_type=scene-risk-video-flow
  ```
  `contentIds` / `contentList` / `openId` are copied straight out of the cached URL.
- Response shape: `data.list[].video.{url, resource.origin, duration, width, height, videoType}`,
  `data.list[].placeCard.{entityId, resblockName, description}`, `data.list[].author.name`.
  `placeCard.entityId` equals the listing houseCode — use it to prove ownership.
- One listing can carry several 实勘视频; iterate every item and check each `placeCard`. List
  them (summary / duration / size) and let the user pick **before** downloading originals — a single
  1080p60 `.mov` can be 600 MB+.
- The vod CDN (`kelive*.ke.com`) serves with a plain UA + `Referer: https://m.ke.com/`.
- Keep the downloaded file's **original name** (the CDN basename, e.g. `YryjchylNxkA.mov`). This user
explicitly does not want media renamed into descriptive titles — record the descriptive metadata in
`视频信息.json` instead of in the filename.
- 原片 may be `.mov` at 20+ Mbps (hundreds of MB). Save it as-is; only offer a transcode if the user asks.

## Pitfalls

- `#小程序://name/code` is not base64 or URL-encoded data — the mapping is server-side in WeChat.
  Don't spend time decoding it; go through the cache.
- No video file is cached on disk. Scanning for `*.mp4` / `ftyp` finds nothing; the artifact to find
  is the request URL.
- Cached response bodies are encrypted (not gzip/deflate/brotli/zstd). Don't brute-force
  decompressors — take the URL and re-request.
- WeChat Mac `*.wxapkg` uses the V1MM encrypted container; unpacking needs a key you don't have.
  Skip code extraction when the cache already yields a URL.
- Cached URLs appear with `sign=` stripped; never assume that is the exact signed URL — rebuild the
  request without the signature.
- A video in the feed is not automatically this listing's: always cross-check the entity id.

## Verification

- `ffprobe` duration / resolution / codec must match the API's `duration` / `width` / `height`.
- `placeCard.entityId` must equal the requested houseCode.
- Write a small `<media>信息.json` (id, duration, resolution, author, source URL) beside the files.
