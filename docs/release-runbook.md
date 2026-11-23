# 发布流程（双镜像 + 文档同步）

本仓库每次发布产出**同一提交的两个镜像**（同一组标签，linux/amd64）：
- Docker Hub：`kid941005/xiaozhi-esp32-server:<ver>` / `:latest`（public）
- GHCR：`ghcr.io/kid941005/xiaozhi-esp32-server:<ver>` / `:latest`（public）

## 一键流程

```bash
# 0) 发布前自检（三个子项目全部测试；需要 3306/6379 时按 CI services 起容器）
bash scripts/run_tests.sh all

# 1) 打 tag 并推送 —— 触发 .github/workflows/dockerhub-image.yml，一次构建同时推 GHCR + Docker Hub
git tag -a v0.9.10 -m "v0.9.10"
git push origin main --tags

# 2) 等流水线跑完（GHCR 用内置 GITHUB_TOKEN；Docker Hub 用 secrets.DOCKERHUB_USERNAME/TOKEN）
gh run list --workflow=dockerhub-image.yml --limit 1
gh run watch $(gh run list --workflow=dockerhub-image.yml --limit 1 --json databaseId -q ".[0].databaseId")

# 3) 同步 README 镜像表与 digest（自动读取两个仓库的 index digest）
bash scripts/release/update_image_docs.sh v0.9.10 --notes docs/release-notes-v0.9.10.md

# 4) 提交文档并创建 Release
git add README.md docs && git commit -m "docs: v0.9.10 镜像表与 digest" && git push origin main
gh release create v0.9.10 --target main --latest --title "v0.9.10" --notes-file docs/release-notes-v0.9.10.md
```

## 校验清单

```bash
# 两个仓库都能匿名拉取（public 包）
docker logout ghcr.io >/dev/null 2>&1 || true
docker manifest inspect ghcr.io/kid941005/xiaozhi-esp32-server:v0.9.10 >/dev/null && echo GHCR_OK
docker manifest inspect kid941005/xiaozhi-esp32-server:v0.9.10 >/dev/null && echo DH_OK

# Docker Hub 是否 public
curl -s https://hub.docker.com/v2/repositories/kid941005/xiaozhi-esp32-server/ | grep -o "\"is_private\":[a-z]*"
```

## 已知限制 / 注意

1. **GHCR 包首次创建默认 private**，且用户级包没有 REST 接口可改可见性（PAT 也改不了，只有组织级 `PATCH /orgs/{org}/packages/...`）。首次发布新包名时需在网页手动改：包页面 → Package settings → Danger Zone → Change visibility → Public。详见 `.learnings/LEARNINGS.md` 的 `LRN-20261123-011`。
2. 缺失 `DOCKERHUB_*` secrets 时流水线只推 GHCR，不会失败；补上 secrets 后重跑即补推 Docker Hub。
3. 不要用旧镜像 tar 或旧仓库快照覆盖工作目录；镜像以容器仓库里的 digest 为准。
4. `docs/release-notes-v<ver>.md` 需含一个 `## 镜像` 小节，`update_image_docs.sh --notes` 会替换该小节内容。
