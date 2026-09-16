---
name: android-cli-maintenance
description: Use when updating or troubleshooting the Android CLI.
---

# Android CLI（Google 的 `android` 命令）自身的分层与维护

本 skill 讲的是**维护 / 排错 `android` 这个工具自身**（更新、版本对不上、更新没生效），不是教你怎么用它跑 Android 项目。工具本身就叫 Android CLI，所以这里的名字带 `-maintenance` 以便区分。

Google 的 Android CLI（agent-first 的那套，非 Android Studio 自带工具）是**两层结构**，两个版本号来源不同，是排查「版本对不上 / 更新没生效」时最容易踩的点。

## 它是两层的，别把两个版本号搞混

| 组件 | 磁盘位置 | 体积 | 谁负责更新 |
|---|---|---|---|
| **launcher** | `~/.local/bin/android`（或 `/usr/local/bin/android`） | ~3.5–3.7 MB，Rust 写的 `launcher.rs` | **只有官方安装脚本 / 重新下载** |
| **runtime** | `$ANDROID_USER_HOME/bin/android-cli` + `$ANDROID_USER_HOME/cli/bundles/<sha>/main.jar` + `cli/bundles/<sha>/jre/` | ~84 MB | `android update` + 自动更新检查 |

`ANDROID_USER_HOME` 默认 `~/.android`。launcher 启动时设置并透传 `ANDROID_CLI_LAUNCHER_VERSION` / `ANDROID_CLI_LAUNCHER_PATH` / `ANDROID_CLI_LAUNCHER_PID` / `ANDROID_CLI_FRESH_INSTALL` / `ANDROID_CLI_DOWNLOAD_URL`，runtime 据此知道自己的宿主是谁。

`android info` 的对应关系：
- `version:` → **runtime** 版本（报 bug、判断「我在用哪个版本」看这个）
- `launcher_version:` → **launcher** 版本

**launcher 落后于 runtime 是正常现象，不影响日常使用**。launcher 只是引导层：读 METADATA、确保 runtime 存在、然后 exec 它。由于 runtime 会自更新而 launcher 不会，两者长期不一致很常见。

## `android update` 只更新 runtime，不动 launcher

`android update` 的 help 是「Update the Android CLI to the latest version」，它替换的是 `$ANDROID_USER_HOME/` 里那份 runtime。下载逻辑（`ANDROID_CLI_DOWNLOAD_URL`、"Downloading Android CLI..."、"Failed to move temporary file to final destination"）写在 **launcher 二进制里**，所以运行中的 runtime 替换不掉自己的 launcher。

诊断：launcher 文件 mtime 远早于 runtime 文件 mtime（`stat -f "%Sm" -t "%Y-%m-%d" <file>`）→ 就是这种情况，正常的。

## 只更新 launcher

平台标签：`darwin_arm64` / `darwin_x86_64` / `linux_x86_64` / `windows_x86_64`（macOS Intel 用 `darwin_x86_64`，Windows 是 `install.cmd`）。

**方法 A：精准替换（推荐，不用 sudo，不碰 runtime）**
```bash
curl -fsSL https://dl.google.com/android/cli/latest/darwin_arm64/android -o /tmp/android.new
chmod +x /tmp/android.new
cp ~/.local/bin/android ~/.local/bin/android.bak   # 保底：旧版本没有历史 URL 可再下
mv /tmp/android.new ~/.local/bin/android
android info        # launcher_version 应变成新版本
```

**方法 B：官方安装脚本**
```bash
curl -fsSL https://dl.google.com/android/cli/latest/darwin_arm64/install.sh | bash
```

⚠️ 坑：`install.sh` 默认写到 `/usr/local/bin/android`（要 sudo），若你原本装在 `~/.local/bin/android`，就会**存在两份**。`~/.local/bin` 通常在 PATH 里排在 `/usr/local/bin` 前面，脚本装的那份被遮蔽 —— 表现为「明明装了却没生效 / `which android` 指向没变」。要用这个脚本，装完把多余那份删掉；否则直接用方法 A。

## 不执行就读出内置版本（排错 / 免 sudo 验证）

launcher 二进制里带一个固定格式的字符串，可直接提取，无需运行：
```bash
strings -a ~/.local/bin/android | grep -oE "Failed to exec android binary: version=[0-9.]+"
```
注意用 `[0-9.]+` 全量匹配；写成 `[0-9]+\.[0-9]+` 只会匹配到 `1.0` 就截断。

判断某个下载 URL 是 launcher 还是 runtime：比 content-length 与本地文件大小 —— `.../<platform>/android` 约 3.67 MB（launcher），`.../<platform>/android-cli` 约 84 MB（runtime）。下载后 `shasum -a 256` 比对可确认是否为新构建。

## 其他有用位置

- `$ANDROID_USER_HOME/cli/last_update_check`：runtime 自动更新检查的时间戳（Unix 秒，`date -r <n>` 换算）。注意目录是短名 `cli`，不是 `android-cli`。
- `android update --url=PARAM`：指定更新来源（镜像 / 内网用）。
- `~/.androidrc`（macOS/Linux）：每次调用自动附加的默认 flag。
- `android -v`：verbose，排错用。

## 官方资料

- 概述与安装：https://developer.android.com/tools/agents/android-cli
- agent skill（含各平台安装一行命令）：https://developer.android.com/agents/skills/devtools/android-cli/skill
- skills 仓库：https://github.com/android/skills

命令清单（`android help` 实测）：`create` `describe` `docs` `emulator` `info` `init` `install` `layout` `run` `screen` `sdk` `skills` `studio` `update` `completion`。

**版本号现场查，别记静态值**：`android info` / `android --version` / 上面的 strings 一行命令都比记住的数字可靠，这两个组件几个月就会各自前进好几次。
