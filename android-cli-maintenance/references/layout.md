# Android CLI 磁盘布局（macOS 实测样本）

2026-09-16 在 macOS arm64（Apple Silicon）上实测，launcher `1.0.15433482` + runtime `1.0.16261425`。

## launcher

```
~/.local/bin/android                    3,652,512 B  Mach-O 64-bit arm64  (mode -rwx--x--x)
```

对应官方最新（同日下载）：`3,672,080 B`，内置版本 `1.0.16261425`。体积随版本略变，量级 ~3.5–3.7 MB 可用来区分它和 runtime。

## runtime（`ANDROID_USER_HOME=~/.android`）

```
~/.android/bin/android-cli                                  83,918,832 B  (mode -rwxr--r--)
~/.android/cli/bundles/<sha>/main.jar                       53,130,290 B
~/.android/cli/bundles/<sha>/jre/                           (bundled JRE)
~/.android/cli/last_update_check                            10 B, Unix 秒
~/.android/cli/tos_displayed                                1 B
~/.android/cli/analytics/{metrics/spool,crash_reports}/
~/.android/cli/docs/
~/.android/cli/skills/                                      ~27 个条目，含 .claude-plugin/ .codex-plugin/ 的 marketplace/plugin 清单
~/.android/cli/studio/
```

`bundles/<sha>/` 的哈希由内容决定，升级后目录名会变，不要在脚本里硬编码。

## 下载 URL → 本地文件映射（用 content-length 判定）

| URL | 大小 | 落到本地 |
|---|---|---|
| `.../cli/latest/<platform>/android` | 3,672,080 | launcher → `~/.local/bin/android` |
| `.../cli/latest/<platform>/android-cli` | 83,918,832 | runtime → `~/.android/bin/android-cli` |
| `.../cli/latest/<platform>/install.sh` | — | 安装脚本（HTTP 200；`/cli/install.sh` 是 404） |

runtime 下载 URL 的字节数与本地 `~/.android/bin/android-cli` **完全一致**，这是确认「哪个 URL 是 runtime」最直接的办法。

用 `curl -sIL <url> | awk 'BEGIN{IGNORECASE=1}/^content-length:/{v=$2}END{gsub(/\r/,"",v);print v}'` 取字节数（macOS 没有 `numfmt`）。

## `android init` 的副作用：往各 agent 目录撒 `skills/android-cli`

`android init` 会检出机器上的各个 agent，把官方 `android-cli` skill 装进它们的 skills 目录。实测命中 **15 处**（以下即 `android init` 的原始输出，未包含全部 agent）：

`~/.gemini/config/skills/`、`~/.gemini/antigravity-cli/skills/`、`~/.gemini/antigravity/skills/`、`~/.gemini/skills/`、`~/.claude/skills/`、`~/.codex/skills/`、`~/.agents/skills/`、`~/.codebuddy/skills/`、`~/.lingma/skills/`、`~/.qwen/skills/`、`~/.qoder/skills/`、`~/.qoder-cn/skills/`、`~/.config/opencode/skills/`、`~/.codeium/windsurf/skills/`、**`~/.hermes/skills/`**。

排错陷阱：用 `find ~ -name 'android-cli'` 统计时会把 `~/.android/bin/android-cli` 算进来，那是 **runtime 二进制**不是 skill，真数会偏大。

两个必须注意的点：

1. **命名**：Google 官方这个 skill 就叫 `android-cli`，且落在 `~/.hermes/skills/` 的**扁平根层**（其余 skill 都在分类子目录下）。所以本 skill 命名成 `android-cli-maintenance` 避重名。两者职责互补：官方那个讲「怎么用 `android`」，本 skill 讲「怎么维护这个工具自身」。
2. **许可**：官方 skills 是 **Apache-2.0**（全文在 `~/.android/cli/skills/LICENSE.txt`，201 行），但**装进 agent 目录的副本只有 `SKILL.md` + `references/`，不带任何许可声明**。因此**不要**把 `~/.hermes/skills/android-cli/` 同步/提交到自己的 MIT 仓库——既缺归属声明又错标许可。它还会被 `android skills update` 覆盖，进 git 只会产生噪音。同步脚本里排除掉。

`~/.android/cli/skills/` 里**没有**记录「装到了哪些路径」的清单（grep `.hermes` 无命中），所以 `skills remove/update` 是重新扫描各 agent 目录，而不是读路径表。

`android skills add --agent=<key>` 可限定单个 agent；有效 key 是 `claude-code`（不是 `claude`）、`gemini`、`codex`、`cursor`、`opencode`、`windsurf`、`github-copilot`、`antigravity`、`universal`。`android skills add --all` 会装到所有检出的 agent。清理时记得这些目录散布在多个 agent 下。

装好后的文件构成（实测）：`SKILL.md` 21,118 B + `references/interact.md` 4,756 B + `references/journeys.md` 4,754 B。`skill_view('android-cli')` 可正常加载，Hermes 认扁平根层的 skill 目录。
