# 设备鉴权与 CORS 加固说明

对应上游 issue #3448、#3456。本仓库在 `config.yaml` 的 `server` 段新增了若干开关，
默认值保持与旧版本兼容（不改变现有部署行为），需要更严格的安全姿态时按需开启。

## 1. `server.auth` 相关配置

```yaml
server:
  auth:
    # 是否校验设备 token（保持原语义）
    enabled: false
    # 白名单设备：不再"免 token"，只是放宽 token 有效期
    allowed_devices: []
    # 白名单设备的 token 有效期（秒），默认 10 年
    allowed_devices_expire_seconds: 315360000
    # 严格 OTA：为设备签发 token 前要求已有有效凭证（首次连接允许自举一次）
    strict_ota: false
    # 固件下载是否要求 Bearer token
    protect_firmware_download: false
```

### 行为说明

| 配置 | 默认 | 开启后的影响 |
| --- | --- | --- |
| `auth.enabled` | `false` | 与旧版本一致：WebSocket 连接校验 Bearer token |
| `auth.allowed_devices` | `[]` | 列表内设备**仍必须携带 token**，只是有效期改用 `allowed_devices_expire_seconds`。旧版本是"白名单内直接放行、不校验 token"，可被伪造 `Device-Id` 头绕过（#3448），因此已取消该豁免 |
| `auth.strict_ota` | `false` | `/xiaozhi/ota/` 只为"白名单设备 / 已有有效凭证 / 进程内首次自举"的设备签发 token，其余返回 403。升级前请先确认固件会在 OTA 请求里带 `Authorization`，否则可能无法获取 token |
| `auth.protect_firmware_download` | `false` | `/xiaozhi/ota/download/{filename}` 要求有效 Bearer token，否则 401 |

> 当 `auth.enabled: true` 而 `strict_ota` / `protect_firmware_download` 仍为 `false` 时，
> 服务启动日志会各打一条 warning 提示当前仍有未收敛的入口。

### Device-Id / Device-Model 校验

OTA 接口现在始终校验：

- `Device-Id` 必须形如 `AA:BB:CC:DD:EE:FF`（也接受 `-` 分隔），否则返回 403；
- `Device-Model` 限制为 `[A-Za-z0-9._-]{1,64}`，非法时回退为 `default`。

这两项用于阻断把任意字符串拼进 MQTT topic / client-id 的注入路径。

## 2. `server.cors.allowed_origins`

```yaml
server:
  cors:
    # 允许跨域访问 OTA / 视觉识别接口的来源白名单；留空表示不返回 CORS 头
    allowed_origins: []
```

- 列表包含 `*`：回显请求的 `Origin`，但**不再下发** `Access-Control-Allow-Credentials`（同时打 warning）；
- 命中具体来源：回显该来源并允许携带凭证；
- 未命中或列表为空：不下发 `Access-Control-Allow-Origin`，日志 debug 记录被拒绝的来源；
- 任何带 `Origin` 的请求都会返回 `Vary: Origin`。

旧实现同时下发 `Access-Control-Allow-Origin: *` 与 `Access-Control-Allow-Credentials: true`，
该组合在浏览器中无效，且任意网页都能读取 OTA 凭证（#3456 独立缺陷 2），故改为白名单模式。

## 3. 智控台侧（manager-api）

`DeviceServiceImpl.checkDeviceActive` 现在只对已在数据库中登记的设备签发 WebSocket token；
未登记设备返回空 token 并记录 warning，避免任何人自报 `Device-Id` 即可换取合法凭证。

## 4. 智控台下发的配置与本地配置合并

全模块部署时，智控台只会覆盖 `server.auth.enabled`，其余 `server.auth.*` 与
`server.cors.*` 键以本地 `config.yaml` 为准（此前智控台模式下整个 `server.auth` 段会被覆盖成
只剩 `enabled`）。
