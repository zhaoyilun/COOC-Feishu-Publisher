# GitHub Pages 发布与迁移

## 当前公开入口

- 仓库：`zhaoyilun/COOC-Feishu-Publisher`（公开）
- 站点：<https://zhaoyilun.github.io/COOC-Feishu-Publisher/>
- 部署方式：[`.github/workflows/deploy-pages.yml`](../.github/workflows/deploy-pages.yml) 与飞书同步工作流中的部署作业

两类工作流都将 `site/` 作为 Pages 制品发布。`actions/configure-pages@v5` 使用 `enablement: true`，使新仓库的第一次部署可以自动配置 Pages。

## 内容与凭证边界

读者只访问 GitHub Pages。`site/data/courses.json` 指向仓库内的 `site/courses/<course>/` 静态页面；课程正文、图片和附件均随 `site/` 发布，禁止写入任何 `*.feishu.cn` 课程链接。

飞书同步所需的 `FEISHU_APP_ID`、`FEISHU_APP_SECRET` 与 `FEISHU_WIKI_PUBLIC_ROOT_TOKEN` 只能保存为 GitHub Actions Secrets；不得写入仓库、网页或日志。

## 同步后部署

飞书同步使用 GitHub Actions 的 `GITHUB_TOKEN` 写入生成的公开站点；这类提交不会触发另一个 `push` 工作流。因此 [`.github/workflows/sync-feishu.yml`](../.github/workflows/sync-feishu.yml) 在生成和测试成功后，会检出最新 `main` 并直接部署 `site/` 到 Pages。不要移除此部署作业或改为依赖推送触发。

## 回滚与迁移

- 暂停公开站点：GitHub 仓库 **Settings → Pages** 停用站点；仓库和提交不会因此删除。
- 恢复：在 **Settings → Pages** 选择 **GitHub Actions**，再手动运行 `Deploy COOC catalogue to GitHub Pages`。
- 回滚内容：将 `site/` 恢复至最近确认可用的 Git 提交，并手动运行 Pages 部署。
- 迁移至 `cooc-china`：转移仓库后重新运行完整课程发布工作流。公开 URL 会随新所有者变更；只需更新外部入口，不需要修改飞书编辑文档。
