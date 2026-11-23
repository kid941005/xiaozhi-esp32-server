# v0.9.10

基于上游 [xinnan-tech/xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server) `main`（已合并至 `3219a28`，含 39 个上游提交），叠加本地安全与稳定性修复：上游 issue #3526 / #3000 / #3437 / #3365 / #3448 / #3456，A 组 #3472 / #3478 / #3483 / #3490 / #3496 / #3505，以及架构评审中的 10 项高危问题（H1–H10）。

## 镜像

（发布流水线完成后自动填充）

## 安全加固（P0）

### 设备鉴权与 OTA 签发（#3448、#3456）
- **WebSocket 白名单不再免 token**：白名单设备仍需携带有效 Bearer token，白名单只放宽有效期（新配置 `auth.allowed_devices_expire_seconds`，默认 315360000 秒）。消除「伪造 Device-Id 即可零凭证接入」的绕过。
- **OTA 签发收紧**：新增配置 `auth.strict_ota`（**默认 true**），按「白名单 / 已有有效凭证 / 进程内首次自举」三选一放行，否则返回 403；MQTT 分支同样受约束。
- **OTA 输入校验**：强制校验 Device-Id 的 MAC 格式与 Device-Model 字符集，阻断 MQTT subscribe topic 注入。
- **固件下载鉴权**：新增配置 `auth.protect_firmware_download`（默认 false，开启后下载需有效凭证）。
- **智控台**：`checkDeviceActive` 仅在设备已登记时签发 WebSocket token，未登记设备不再凭空发放。
- **配置合并**：智控台模式下 `server.auth` 不再被整段覆盖，只以智控台下发的 `enabled` 为准，本地白名单/有效期/strict_ota 等加固项保留。

### 匿名面与凭证加固（H1 / H2 / H3 / H6）
- `/druid/**`、`/v3/api-docs/**`、`/doc.html` 不再匿名，需登录；`/otaMag/download/**` 保留匿名（设备升级通道，避免砖机）。
- 配置快照 `server:config` 增加 300 秒 TTL，配置修改后不再长期读到旧快照。
- 设备绑定验证码改用 `SecureRandom` 生成固定六位数字（原 `Math.random` 可预测，且科学计数法时越界抛异常），碰撞最多重试 10 次。
- 匿名聊天记录下载凭证增加 600 秒 TTL，避免链接永久有效。

### CORS 与空指针（H5 + 独立缺陷）
- CORS 改为按 `server.cors.allowed_origins` 白名单回显请求 Origin；不再同时下发 `Allow-Origin: *` 与 `Allow-Credentials: true`；请求带 Origin 时统一返回 `Vary: Origin`。
- 知识库不存在时按无权限拒绝（`RenException(NO_PERMISSION)`），不再 NPE 变 500。

## 稳定性与正确性（P1）

- **WebSocket 会话收敛**：同设备多会话收敛、ASR 空识别反馈、断开清理加固与轮次判废（#3526 #3000 #3437）。
- **本地 ASR 性能**：本地 ASR 实例进程内复用，避免每连接约 3 GB 内存占用（#3365）。
- **事务边界**：`DeviceServiceImpl` 的 `deviceActivation` / `unbindDevice` / `manualAddDevice` 补 `@Transactional(rollbackFor = Exception.class)`。
- **异步非阻塞**：12 个 TTS/ASR provider 的 async 方法内同步 `requests` / `time.sleep` 改为 `asyncio.to_thread` / `asyncio.sleep`，不再阻塞事件循环。
- **fastgpt**：`response_with_functions` 不再返回 `None`（降级为普通生成，避免调用方 TypeError）；`<think>` 段改为按状态剥离，不再整块丢弃正文。
- **provider 加载**：`core/utils` 下 7 个工厂的存在性判断改为基于 `__file__` 锚定，不再依赖启动时工作目录。

## 功能与兼容（P2）

- **天气插件**：移除失效的共享凭据、未配置时给出明确提示、失败缓存按凭据指纹区分、请求加 12 秒总预算并增强网页降级解析（#3472 #3478 #3483）；网页降级失败仍按 `Action.RESPONSE` 回复用户。
- **模型配置**：视觉模型段移除星火 Lite 条目，避免纯文本模型被当作视觉通道（#3490）。
- **数字人**：唤醒词启动失败时回滚已启动插件，音频采集流不再泄漏（#3496）。
- **文档**：多语言 README 校徽 alt 写法统一（#3505）。

## 测试与 CI

- Python：`bash scripts/run_tests.sh python -k "not test_tts_text_to_speak_writes_file"` → **292 passed, 5 skipped**（基线 273）。
- Java：`bash scripts/run_tests.sh java` → **Tests run: 211, Failures: 0, Errors: 0**，集成测试守卫（DeviceTest / ModelConfigPersistenceTest / loginControllerTest）通过。
- Web：contract + 70 个单测 + 构建通过。
- 新增回归测试：设备绑定码、事务注解、知识库权限、OTA 严格模式、CORS 头、鉴权有效期、配置合并、TTS 异步非阻塞、provider 路径锚定、fastgpt think 剥离等。

## 升级注意

1. `auth.strict_ota` 默认 **true**：老固件若既不带 `Authorization`、又不在白名单，OTA 会被拒绝（403）。应急可临时设 `strict_ota: false`，升级固件后改回。
2. `/doc.html`、`/v3/api-docs`、`/druid` 需要登录后再访问。
3. `auth.allowed_devices` 默认改为空列表（原示例 MAC 已删除）；白名单现在的含义是「延长 token 有效期」，不再是免 token。
4. 智控台模式下 `server.auth` 的本地加固键不再被覆盖，请确认部署机 `config.yaml` 中的取值符合预期。

## 包含的主要提交

- `9c669046` fix(reliability): 事务边界、异步非阻塞与 provider 解析加固（H4/H8/H9/H10）
- `56783668` fix(security): 配置快照 TTL、匿名路由收口、验证码与下载凭证加固（H1/H2/H3/H5/H6/H7）
- `aab421df` docs(security): 补充设备鉴权与 CORS 加固说明
- `d12e8216` fix(security): 收紧设备鉴权、OTA 签发与 CORS 策略（#3448、#3456）
- `721cbb49` test(ci): 统一入口禁用 anyio 插件，环境无法收集的用例自动跳过
- `1ace992b` fix(weather): 网页降级失败仍按 Action.RESPONSE 回用户（承接 #3472）
- `fefa392a` fix(asr): 本地 ASR 实例进程内复用，避免每连接 3GB（#3365）
- `28463250` fix(ws): 同设备会话收敛、空识别反馈、清理加固与轮次判废（#3526 #3000 #3437）
- `91cf337c` docs(readme): 统一多语言校徽 alt 写法（#3505）
- `4f3e36e8` fix(digital-human): 唤醒词启动失败回滚，采集流不再泄漏（#3496）
- `82a0bd29` fix(config): 视觉模型段移除星火 Lite 条目（#3490）
- `781cf5a4` fix(weather): 去掉失效共享凭据，未配置给提示，失败缓存按凭据区分（#3472 #3478 #3483）
- `5942118e` merge: 合并上游 2dfaf44..3219a28（39 个提交），保留本地加固与工具链
