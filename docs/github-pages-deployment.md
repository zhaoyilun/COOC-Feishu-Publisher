# GitHub Pages 发布与迁移

## 当前公开入口

- 仓库：`zhaoyilun/COOC-Feishu-Publisher`（公开）
- 站点：<https://zhaoyilun.github.io/COOC-Feishu-Publisher/>
- 发布：`.github/workflows/sync-feishu.yml` 的 `deploy` 作业将 `site/` 作为 Pages 制品发布。

## 内容与凭证边界

学习者只访问 GitHub Pages。`site/data/courses.json` 只指向仓库内的 `site/courses/<course>/` 静态页面；课程正文、图片和附件均随 `site/` 发布，禁止嵌入或链接回 `*.feishu.cn`。

`FEISHU_APP_ID`、`FEISHU_APP_SECRET` 与 `FEISHU_WIKI_PUBLIC_ROOT_TOKEN` 只能保存在 GitHub Actions Secrets；不得写入仓库、页面或日志。初始迁移工作流复用这些凭证，且必须填写确认口令才会创建飞书课程文档。

## 同步后部署

飞书同步通过 `GITHUB_TOKEN` 写入生成的公开站点；这类提交不会触发另一个推送工作流。因此 `sync-feishu.yml` 在生成和测试成功后检出最新 `main` 并直接部署 `site/` 到 Pages。不要改为依赖推送触发。

## 回滚与迁移

- 暂停公开站点：GitHub 仓库 **Settings → Pages** 停用站点；仓库和提交不会删除。
- 回滚公开内容：将 `site/` 恢复到最近确认可用的 Git 提交，再手动运行同步工作流。
- 回滚飞书课程：将误导入文档移出 `公开课程`，再运行同步工作流；静态页和本地媒体会被撤下。
- 回滚一次性全文导入：在飞书文档版本历史恢复导入前版本，再运行同步工作流；不要通过再次运行初始化工作流覆盖编辑者后续改动。
- 迁移至 `cooc-china`：转移仓库后重新运行完整课程发布工作流。公开 URL 随新所有者变化，只需更新外部入口，不需要迁移飞书课程文档。
