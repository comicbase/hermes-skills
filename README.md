# Hermes Skills

由 [Hermes Agent](https://hermes-agent.nousresearch.com/docs) 生成、可复用的技能集合。

## 技能列表

| 技能 | 说明 |
|---|---|
| [`realsee-vr-extract`](realsee-vr-extract/) | 从贝壳/如视(realsee)房源提取 360° VR 全景（立方体面图→等距柱状投影）、户型图、三维模型，并生成可拖拽观看的本地全景查看器（three.js）。 |
| [`beike-realsee-media-extraction`](beike-realsee-media-extraction/) | 贝壳/链家/如视房源媒体提取的通用流程：定位房源、抓取如视 VR 页内嵌数据、下载视频/图片/全景图。 |

## 目录结构

每个技能目录包含：

- `SKILL.md` — 技能主文档（触发条件、流程、坑、验证方法）
- `references/` — 详细参考（JSON 路径、URL 规则、命令）
- `scripts/` — 可执行脚本
- `templates/` — 模板文件

## 许可

MIT — 见 [LICENSE](LICENSE)
