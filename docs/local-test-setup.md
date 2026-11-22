# 本地跑单元测试（含 libopus 准备）

本文说明如何在**本机**（非 Docker）跑三个子项目的测试。
Docker 镜像里 libopus 由 `Dockerfile-server-base` 的 `apt-get install libopus0` 提供，无需本文步骤。

## 三个子项目的统一入口

仓库根目录的 `scripts/run_tests.sh` 是三个子项目共用的入口，CI 调的就是它，本地跑法完全一致：

```bash
bash scripts/run_tests.sh            # 依次跑 python / java / web
bash scripts/run_tests.sh python     # 只跑 xiaozhi-server（pytest）
bash scripts/run_tests.sh java       # 只跑 manager-api（mvn test + 集成测试守卫）
bash scripts/run_tests.sh web        # 只跑 manager-web（契约测试 + 单元测试 + 构建）
bash scripts/run_tests.sh python -k wakeup -v   # 额外参数透传给对应子项目脚本
```

| 目标 | 实际脚本 | 需要的前置条件 |
| --- | --- | --- |
| `python` | `main/xiaozhi-server/scripts/run_tests.sh` | 无（脚本自己准备 libopus 与 `data/.config.yaml`，见下文） |
| `java` | `main/manager-api/scripts/run_tests.sh` | 全量跑需要 MySQL + Redis（CI 由 job 的 services 提供）；本地只跑单元测试用 `-Dtest=SomeTest`，但结尾的集成测试守卫会因为缺少那几个集成测试而失败，属预期 |
| `web` | `main/manager-web/scripts/run_tests.sh` | `node_modules`（缺失时脚本自动 `npm ci`）；`SKIP_BUILD=1` 可跳过生产构建 |

`main/manager-api/scripts/run_tests.sh --dry-run` 只打印将执行的命令，不真跑；本机 `mvn` 不在 PATH 时用 `MVN=/path/to/mvn`（Windows 上用 `mvn.cmd`，同时设置 `MAVEN_HOME`、`JAVA_HOME`）。

## 一键方式

```bash
cd main/xiaozhi-server
bash scripts/run_tests.sh              # 准备 libopus + data/.config.yaml，然后跑全量
bash scripts/run_tests.sh -k wakeup -v # 额外参数原样透传给 pytest
```

预期结果（本机实测，2026-11）：

```
143 passed, 5 skipped
```

## 与 CI 的一致性

`.github/workflows/test.yml` 的 `python` job 直接调用同一个脚本，本地与流水线是同一入口：

```yaml
- name: Run tests
  working-directory: main/xiaozhi-server
  run: bash scripts/run_tests.sh -k "not test_tts_text_to_speak_writes_file"
```

- 那个 `-k` 是 CI 专属：Edge TTS 用例要连微软公网，GitHub runner 的出口 IP 会被风控挡掉（根治办法是给它打 live 标记，属另一条改动）。
- CI 上 `requirements.txt` 里的 `cnlunar` / `markitdown` 都会装好，所以脚本的自动 ignore 不生效；本地缺依赖时才会跳过对应文件。
- libopus 由 job 里显式的 `apt-get install -y libopus0` 提供，脚本检测到已可用会直接跳过安装。
- `java` / `web` 两个 job 同样走统一入口：`bash scripts/run_tests.sh java`（含集成测试守卫）、`bash scripts/run_tests.sh web`（契约测试 + 单元测试 + 生产构建）。

本地复刻 CI 那条命令：

```bash
cd main/xiaozhi-server
bash scripts/run_tests.sh -k "not test_tts_text_to_speak_writes_file"
# 期望：142 passed, 5 skipped, 1 deselected
```

## 为什么需要额外准备 libopus

`requirements.txt` 里的 `opuslib_next` 是 **纯 Python 的 ctypes 绑定**，pip 装完仍要靠系统里的 libopus 动态库：

- `opuslib_next/api/__init__.py:9` 用 `ctypes.util.find_library("opus")` 找库；
- Windows 上这一步等价于「PATH 里有没有 `opus.dll`」；
- 找不到时 `tests/conftest.py:48-78` 会把 `Encoder`/`Decoder` 换成抛错的桩，于是 `tests/core/handle/test_wakeup_response.py` 的 5 个用例失败，报错为：

```
RuntimeError: libopus 没装，Opus 编解码跑不了。装法：apt-get install libopus0（正式镜像 Dockerfile-server-base 里也是这么装的）
```

## 分步方式

### 1. 准备 libopus

```bash
bash scripts/setup_libopus.sh          # 幂等：已可用直接跳过
bash scripts/setup_libopus.sh --force  # 强制重装 opuslib_next
```

脚本按平台自动处理：

| 平台 | 做法 |
| --- | --- |
| Linux | `apt-get install -y libopus0` / `dnf install -y opus` / `pacman -S opus`（按可用包管理器） |
| macOS | `brew install opus` |
| Windows（MSYS/Git Bash） | `pip install av`，从 `site-packages/av.libs/libopus-*.dll` 复制为 `~/.cache/xiaozhi-opus/opus.dll`，并提示加入 PATH |

Windows 上首次运行会打印一行，需要在新终端里执行一次（或写进 `~/.bashrc`）：

```bash
export PATH="C:\Users\<你>\.cache\xiaozhi-opus;$PATH"
```

> ⚠️ 必须是 **Windows 原生路径**（`C:\...`）。在 MSYS/Git Bash 里写 `/c/Users/...` 或 `/d/...` 传不到原生 Python 进程，
> `find_library("opus")` 仍然返回 `None`。脚本内部用 `cygpath -w` 做了转换，手工设置时要自己注意。

dll 存放目录可用 `XIAOZHI_OPUS_DIR` 覆盖，pip 参数可用 `PIP_BREAK_SYSTEM_PACKAGES` 覆盖（默认 `--break-system-packages`，适配 PEP 668 环境）。

### 2. 准备测试配置

`config/logger.py` 的 `setup_logging()` 在 import 阶段就会读 `data/.config.yaml`，缺文件直接抛错。
`run_tests.sh` 会自动创建一份 `{}`；手工方式：

```bash
printf '{}\n' > data/.config.yaml
```

### 3. 跑测试

```bash
python -m pytest tests/ -q \
  --ignore=tests/core/utils/test_current_time.py \
  --ignore=tests/plugins_func/test_weather_news_plugins.py
```

两个 `--ignore` 是**可选依赖**缺失时的兜底：`test_current_time.py` 需要 `cnlunar`，`test_weather_news_plugins.py` 需要 `markitdown`，缺了会在 collection 阶段直接报错。
装上依赖后可去掉对应 `--ignore`。`run_tests.sh` 会自动探测并只跳过缺依赖的那个文件。

## 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| `Exception: Could not find Opus library. Make sure it is installed.`（import opuslib_next 时） | 只有绑定没有库。跑 `scripts/setup_libopus.sh` |
| 5 个 `test_wakeup_response` 用例失败，报 `RuntimeError: libopus 没装` | 同上；conftest 走了桩分支 |
| Windows 已放 dll 但仍找不到 | PATH 用了 MSYS 路径，或没在**新终端**里 export |
| `test_current_time` / `test_weather_news_plugins` collection error | 缺 `cnlunar` / `markitdown`，装依赖或加 `--ignore` |
| 5 个 skipped | 正常：3 个 `test_llm.py` 占位符 api_key（需 `RUN_LIVE_API_TESTS=1` 且填真 key），2 个 import 期需要 `data/.config.yaml` 的副作用测试 |
| `ModuleNotFoundError: No module named 'core...'` | 必须在 `main/xiaozhi-server` 目录下运行（conftest 会注入 sys.path） |
| 看不到最后的 `143 passed, 5 skipped in Xs` 汇总行 | 传了两次 `-q`（脚本默认一次 + 自己再传一次）= `-qq`，pytest 的 `-q` 是累加的，`-qq` 会连汇总行一起吞掉。脚本现在只在调用方没传 `-q`/`-v` 时才加默认 `-q` |
