# Hermes Skills

由 [Hermes Agent](https://hermes-agent.nousresearch.com/docs) 生成、可复用的技能集合。

## 技能列表

| 技能 | 说明 |
|---|---|
| [`android-cli-maintenance`](android-cli-maintenance/) | 维护/排错 Google 的 Android CLI（`android` 命令）自身：launcher 与 runtime 两层结构、`android info` 两个版本号的关系、如何单独更新 launcher、`android init` 往各 agent 目录撒 skill 的副作用与 Apache-2.0 许可提醒。 |
| [`pdf-image-stitch`](pdf-image-stitch/) | 从 PDF 里取出内嵌原始图（不渲染页面，避免 72dpi 降质），按比例或像素裁剪任意部分并上下拼成一张：裁剪零损失、合并只做一次 JPEG 编码，质量/色度采样对齐源图；附扫描件内容边界自动裁切（`--trim`）与隐私红线提醒。 |
| [`realsee-vr-extract`](realsee-vr-extract/) | 从贝壳/如视(realsee)房源提取 360° VR 全景（立方体面图→等距柱状投影）、户型图、三维模型、视频/图片，并生成可拖拽观看的本地全景查看器（three.js）。 |
| [`wechat-miniprogram-media`](wechat-miniprogram-media/) | 从小程序取没有下载入口的视频：借 Mac 微信 WebView 缓存还原页面调用的接口，按实体 ID 认领内容后下载原片；附贝壳「实勘视频」端到端流程与抓取脚本。 |
| [`wechat-mp-to-markdown`](wechat-mp-to-markdown/) | 把微信公众号文章存成 Markdown：抓取正文并保留原创标识/作者/公众号/发布时间，按行还原代码块、清理 NBSP，图片本地化到 `images/NN.ext` 并改写为相对链接。 |

## 目录结构

每个技能目录包含：

- `SKILL.md` — 技能主文档（触发条件、流程、坑、验证方法）
- `references/` — 详细参考（JSON 路径、URL 规则、命令）
- `scripts/` — 可执行脚本
- `templates/` — 模板文件

## 许可

MIT — 见 [LICENSE](LICENSE)
