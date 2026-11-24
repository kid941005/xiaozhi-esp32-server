#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同步 README（以及可选 Release 说明）中的镜像表与 digest。

用法：
    bash scripts/release/update_image_docs.sh v0.9.10
    bash scripts/release/update_image_docs.sh v0.9.10 --notes docs/release-notes-v0.9.10.md
    # digest 也可直接传入，跳过 docker 查询：
    bash scripts/release/update_image_docs.sh v0.9.10 --dh-digest sha256:... --ghcr-digest sha256:...
"""
import argparse
import io
import os
import re
import subprocess
import sys

BEGIN = "<!-- IMAGES:BEGIN -->"
END = "<!-- IMAGES:END -->"
OWNER = os.environ.get("IMG_OWNER", "kid941005")


def fetch_digest(image):
    proc = subprocess.run(["docker", "buildx", "imagetools", "inspect", image],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit("无法读取 %s 的 digest：%s" % (image, (proc.stderr or proc.stdout).strip()))
    m = re.search(r"^Digest:\s+(sha256:[0-9a-f]{64})", proc.stdout, re.M)
    if not m:
        sys.exit("未在 imagetools 输出中找到 Digest：%s" % image)
    return m.group(1)


def image_rows(ver):
    dh = "%s/xiaozhi-esp32-server" % OWNER
    gh = "ghcr.io/%s/xiaozhi-esp32-server" % OWNER
    wv = ver[1:] if ver.startswith("v") else ver
    return [
        "| 镜像地址 | 说明 |",
        "|---|---|",
        "| `%s:%s` | Docker Hub（public，无需登录），服务端固定版本，建议用于生产部署与回滚 |" % (dh, ver),
        "| `%s:latest` | Docker Hub（public），服务端跟随最近一次发布，当前等同 `%s` |" % (dh, ver),
        "| `%s:web_%s` | Docker Hub（public），智控台（前端 + manager-api）固定版本 |" % (dh, wv),
        "| `%s:web_latest` | Docker Hub（public），智控台跟随最近一次发布 |" % dh,
        "| `%s:%s` | GHCR（public，无需登录），服务端固定版本 |" % (gh, ver),
        "| `%s:latest` | GHCR（public，无需登录），服务端跟随最近一次发布，当前等同 `%s` |" % (gh, ver),
        "| `%s:web_%s` | GHCR（public），智控台固定版本（多架构 amd64 + arm64） |" % (gh, wv),
        "| `%s:web_latest` | GHCR（public），智控台跟随最近一次发布（多架构） |" % gh,
    ]


def digest_lines(dhd, ghc, dhw=None, ghw=None):
    lines = [
        "镜像 digest（同一提交、不同构建环境，内容等价）：",
        "- Docker Hub 服务端：`%s`（linux/amd64，压缩约 3.5 GB / 解压 10.8 GB）" % dhd,
        "- GHCR 服务端：`%s`（linux/amd64，10.8 GB）" % ghc,
    ]
    if dhw:
        lines.append("- Docker Hub 智控台：`%s`（linux/amd64）" % dhw)
    if ghw:
        lines.append("- GHCR 智控台：`%s`（多架构 index，amd64 + arm64）" % ghw)
    return lines


def pull_lines(ver):
    dh = "%s/xiaozhi-esp32-server" % OWNER
    gh = "ghcr.io/%s/xiaozhi-esp32-server" % OWNER
    return [
        "拉取与使用：",
        "",
        "```bash",
        "# Docker Hub（public，可直接拉取）",
        "docker pull %s:%s" % (dh, ver),
        "",
        "# GHCR（public，可直接拉取）",
        "docker pull %s:%s" % (gh, ver),
        "```",
        "",
        "在 `docker-compose.yml` 中把 server 服务的 `image` 换成上述地址即可，例如：",
        "",
        "```yaml",
        "services:",
        "  xiaozhi-esp32-server:",
        "    image: %s:%s            # Docker Hub" % (dh, ver),
        "    # image: %s:%s  # GHCR 备用" % (gh, ver),
        "```",
        "",
        "> Docker Hub 与 GHCR 上的镜像均为 **public**，可直接拉取、无需登录。若 GHCR 仍报 `unauthorized` / `denied`，多半是本地缓存了旧的私有凭据：先 `docker logout ghcr.io` 再重试。",
        "",
        "> 镜像由 GitHub Actions 流水线 [`.github/workflows/dockerhub-image.yml`](.github/workflows/dockerhub-image.yml) 构建：推送 `v*.*.*` 标签或手动触发时，一次构建同时发布到 GHCR 与 Docker Hub（同一组标签）。",
    ]


def readme_block(ver, dhd, ghc, dhw=None, ghw=None):
    lines = ["本 fork 提供已构建好的服务端与智控台镜像（含安全加固、上下文源并发化、工具调用治理与测试工程化，详见 [%s Release](https://github.com/%s/xiaozhi-esp32-server/releases/tag/%s)）：" % (ver, OWNER, ver), ""]
    lines += image_rows(ver)
    lines += [""] + digest_lines(dhd, ghc, dhw, ghw)
    lines += [""] + pull_lines(ver)
    return "\n".join([BEGIN, ""] + lines + ["", END])


def notes_block(ver, dhd, ghc, dhw=None, ghw=None):
    lines = image_rows(ver)
    lines += [""] + digest_lines(dhd, ghc, dhw, ghw)
    lines += [""] + pull_lines(ver)
    return "\n".join(lines)


def update_readme(path, ver, dhd, ghc, dhw=None, ghw=None):
    text = io.open(path, encoding="utf-8").read()
    if BEGIN not in text or END not in text:
        sys.exit("README 缺少 %s / %s 标记，请先手工加上" % (BEGIN, END))
    new = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _: readme_block(ver, dhd, ghc, dhw, ghw), text, count=1, flags=re.S)
    if new != text:
        io.open(path, "w", encoding="utf-8", newline="\n").write(new)
        print("README 已更新：%s" % path)
    else:
        print("README 无需变更：%s" % path)


def update_notes(path, ver, dhd, ghc, dhw=None, ghw=None):
    text = io.open(path, encoding="utf-8").read()
    m = re.search(r"^## 镜像[^\n]*\n", text, re.M)
    if not m:
        sys.exit("%s 中没有 “## 镜像” 小节" % path)
    start = m.end()
    nxt = re.search(r"^## ", text[start:], re.M)
    end = start + nxt.start() if nxt else len(text)
    new = text[:start] + "\n" + notes_block(ver, dhd, ghc, dhw, ghw) + "\n\n" + text[end:]
    io.open(path, "w", encoding="utf-8", newline="\n").write(new)
    print("Release 说明已更新：%s" % path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("version", help="版本标签，例如 v0.9.10")
    ap.add_argument("--readme", default="README.md")
    ap.add_argument("--notes", default=None, help="Release 说明文件（含 ## 镜像 小节）")
    ap.add_argument("--dh-digest", default=None)
    ap.add_argument("--ghcr-digest", default=None)
    ap.add_argument("--dh-web-digest", default=None, help="Docker Hub 智控台镜像 digest")
    ap.add_argument("--ghcr-web-digest", default=None, help="GHCR 智控台（多架构）index digest")
    a = ap.parse_args()
    ver = a.version
    dh_img = "%s/xiaozhi-esp32-server:%s" % (OWNER, ver)
    gh_img = "ghcr.io/%s/xiaozhi-esp32-server:%s" % (OWNER, ver)
    wv = ver[1:] if ver.startswith("v") else ver
    dh_web_img = "%s/xiaozhi-esp32-server:web_%s" % (OWNER, wv)
    gh_web_img = "ghcr.io/%s/xiaozhi-esp32-server:web_%s" % (OWNER, wv)
    dhd = a.dh_digest or fetch_digest(dh_img)
    ghc = a.ghcr_digest or fetch_digest(gh_img)
    dhw = a.dh_web_digest or fetch_digest(dh_web_img)
    ghw = a.ghcr_web_digest or fetch_digest(gh_web_img)
    print("version=%s" % ver)
    print("dockerhub=%s digest=%s" % (dh_img, dhd))
    print("ghcr=%s digest=%s" % (gh_img, ghc))
    print("dockerhub-web=%s digest=%s" % (dh_web_img, dhw))
    print("ghcr-web=%s digest=%s" % (gh_web_img, ghw))
    update_readme(a.readme, ver, dhd, ghc, dhw, ghw)
    if a.notes:
        update_notes(a.notes, ver, dhd, ghc, dhw, ghw)


if __name__ == "__main__":
    main()
