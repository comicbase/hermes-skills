# Hermes Skills

由 [Hermes Agent](https://hermes-agent.nousresearch.com/docs) 生成、可复用的技能集合。

## 技能列表

| 技能 | 说明 |
|---|---|
| [`android-cli-maintenance`](android-cli-maintenance/) | 维护/排错 Google 的 Android CLI（`android` 命令）自身：launcher 与 runtime 两层结构、`android info` 两个版本号的关系、如何单独更新 launcher、`android init` 往各 agent 目录撒 skill 的副作用与 Apache-2.0 许可提醒。 |
| [`realsee-vr-extract`](realsee-vr-extract/) | 从贝壳/如视(realsee)房源提取 360° VR 全景（立方体面图→等距柱状投影）、户型图、三维模型、视频/图片，并生成可拖拽观看的本地全景查看器（three.js）。 |
| [`wechat-mp-to-markdown`](wechat-mp-to-markdown/) | 把微信公众号文章存成 Markdown：抓取正文并保留原创标识/作者/公众号/发布时间，按行还原代码块、清理 NBSP，图片本地化到 `images/NN.ext` 并改写为相对链接。 |

## 目录结构

每个技能目录包含：

- `SKILL.md` — 技能主文档（触发条件、流程、坑、验证方法）
- `references/` — 详细参考（JSON 路径、URL 规则、命令）
- `scripts/` — 可执行脚本
- `templates/` — 模板文件

## 许可

MIT — 见 [LICENSE](LICENSE)
