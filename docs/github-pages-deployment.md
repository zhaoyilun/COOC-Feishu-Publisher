# GitHub Pages 发布与迁移

## 当前公开入口

- 仓库：`zhaoyilun/COOC-Feishu-Publisher`（公开）
- 站点：<https://zhaoyilun.github.io/COOC-Feishu-Publisher/>
- 部署方式：GitHub Actions 工作流 [`.github/workflows/deploy-pages.yml`](../.github/workflows/deploy-pages.yml)

工作流将 `site/` 作为 Pages 制品发布。`actions/configure-pages@v5` 使用 `enablement: true`，使新仓库的第一次部署可以自动配置 Pages。

## 内容与凭证边界

公开站点只读取已生成的 `site/data/courses.json`。飞书同步需要的 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_BITABLE_APP_TOKEN` 与 `FEISHU_BITABLE_TABLE_ID` 只能保存为 GitHub Actions Secrets；不得写入仓库、网页或日志。

## 首次验收（2026-08-04）

- Actions 运行 `30922861371` 的 Pages 部署成功。
- 未登录 HTTP 请求返回站点首页 `200`。
- 未登录读取 `data/courses.json` 时，仅有 1 条公开课程 `COOC 协同创建课程导论`；`内部资料草案` 不在公开数据中。

## 回滚与迁移

- 暂停公开站点：GitHub 仓库 **Settings → Pages** 停用站点；也可删除 Pages 站点配置。仓库和提交不会因此删除。
- 恢复：在 **Settings → Pages** 选择 **GitHub Actions**，再手动运行 `Deploy COOC catalogue to GitHub Pages`。
- 迁移至 `cooc-china`：转移仓库后重新运行部署。公开 URL 会随新所有者变更，必须更新飞书中引用旧站点的链接并重新执行未登录访问验收。
