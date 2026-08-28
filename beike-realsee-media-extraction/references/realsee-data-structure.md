# realsee VR 页内嵌数据结构（实录 2026-08）

贝壳小程序「复制链接」给出的 `open.realsee.com/ke/<workCode>/<token>/` 页面，把完整数据以 JSON 塞在 HTML 注释里，服务端渲染，**免验证码**（贝壳/链家详情页 `hip.ke.com/captcha` 有验证码）。

## 提取方式

```python
import re, json
t = open('page.html', encoding='utf-8').read()
idx = t.find('"firstscreen"')
start = t.rfind('<!--', 0, idx)
end = t.find('-->', idx)
data = json.loads(t[start+4:end].strip())
# 顶层键: firstscreen / configure / viewports
```

## 关键字段

### firstscreen.houseInfo
- `title` 房源标题（如「XX小区 4室2厅」）
- `houseCode`（12位数字）、`cityId`（6位数字）、`area`、`coordinates`
- `detail.data[]`：`{title, content, is_price, ...}` — 售价/单价/户型/面积/挂牌/朝向/楼型/城市/楼层
- `multimedia[]`：`{type: 'video'|'image', title, list: [{url, coverURL, title}]}`
  - type=video 且 title=`小区楼栋`/`停车管理` → **小区视频**（非室内），url 是 `http://video.ljcdn.com/resblock-video/*.mp4`
  - type=image → `https://ke-image.ljcdn.com/hdic-resblock/*.jpg`（小区图片）
- `params`：workCode / platform / relationId 等

### firstscreen.defaultWork（VR 全景核心）
- `panorama`：`{base_url, count, list[], work_code}`
  - `list[i]` 键：`front` `back` `left` `right` `up` `down`（六面立方体贴图 URL）+ `index` + `size_list`
  - URL 形如 `https://vr-public.realsee-cdn.cn/release/auto3dhd/<hash>/images/cube_2048/<i>/<facehash>/<i>_<f>.avif`
- `observers[]`：`{index, position[x,y,z], quaternion{w,x,y,z}, floor_index, visible_nodes[], accessible_nodes[]}` — 观察点空间图（`visible_nodes` 是相邻点，可做 BFS 漫游路径）
- `initial`：`{pano_index, heading, latitude, longitude, fov, offset{x,y,z}}` — 初始视角
- `model.file_url`：`.at3d` 3D 模型；`hierarchy_floor_plan[]`/`outline_floor_plan[]`：户型图；`picture_url`/`title_picture_url`：封面
- `house_layout`：`{bedroom_amount, parlor_amount, cookroom_amount, toilet_amount}`

### firstscreen.resblockInfo
`detail.data[]`（小区信息）+ `multimedia[]`（与 houseInfo.multimedia 相同的 6 面/图片，即小区媒体）

## avif → jpg/png（服务端转码）

realsee 图片在腾讯云 COS 上，支持 `imageMogr2` 处理参数：
- `https://.../0_f.avif?imageMogr2/format/jpg` → 直接返回 2048×2048 jpg（~270KB）
- `?imageMogr2/format/png` → 2048×2048 png（~1.8MB）
- 换 `.jpg` 后缀 → **404**，必须用 `imageMogr2` 参数

## 6面立方体 → 360° 全景图（ffmpeg v360）

v360 的 cubemap `c6x1`（6面横排）面顺序默认 `in_forder=rludfb` = **right, left, up, down, front, back**。

realsee 键名是 `front/back/left/right/up/down`，需重排为 v360 顺序：
```
right, left, up, down, front, back
```

```bash
ffmpeg -hide_banner -y \
  -i right.jpg -i left.jpg -i up.jpg -i down.jpg -i front.jpg -i back.jpg \
  -filter_complex "[0][1][2][3][4][5]hstack=6[c];[c]v360=c6x1:e" \
  -frames:v 1 equi.png   # 输出 8192x4096 equirectangular
```

提取普通透视视角（单帧/视频片段）：
```bash
ffmpeg -y -i equi.png -vf "v360=e:flat:yaw=0:pitch=0:h_fov=100:v_fov=59:w=1920:h=1080" view.png
```

## 方向校准（实测验证过的正确参数）

用 `right,left,up,down,front,back` 顺序 + `v360=c6x1:e`，输出全景图提取的正面透视**方向正确**（文字正向、墙竖直、地面水平、无镜像）。验证法：`v360=e:flat:yaw=0:pitch=0` 提取一张，用 vision 看时钟/文字是否正向。若发现镜像/颠倒，改 `in_frot`（每面旋转码，如 `000000` → 对应面转 90° 的 0-3）。

## 视频/图片下载

- 视频：`curl -s -o x.mp4 "<mp4_url>" -A "<UA>" -H "Referer: https://open.realsee.com/"`，返回 `video/mp4` 或 `application/octet-stream`，几 MB~十几 MB。
- 图片：`curl -s -o x.jpg "<jpg_url>" -A "<UA>"`。
