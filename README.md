# COOC Feishu Publisher

无服务器的静态课程发布器：编辑者只维护飞书知识库 `COOC 课程内容管理`，学习者只访问 GitHub Pages。GitHub Actions 读取 `公开课程` 目录，生成完整静态课程页并将图片、附件下载到站点内；读者不需要飞书账号。

## 内容流

```text
Feishu Wiki（公开课程下的直接 docx 子文档）
        ↓ GitHub Actions
site/courses/<stable-course-id>/index.html + assets/
site/data/courses.json
        ↓
GitHub Pages（唯一学习入口）
```

生成页不包含任何 `*.feishu.cn` 链接、文档 token 或需要登录的资源。将课程移出 `公开课程` 后，下次同步会删除对应静态页和媒体。

## 团队维护与发布

- 管理员负责知识库成员、目录和发布边界；建议始终保留两名以上管理员。
- 课程负责人加入“可编辑的成员”，审核人员加入“可阅读的成员”，不要共享个人账号或应用密钥。
- `公开课程` 下的直接 `docx` 子文档会自动公开；草稿、内部资料和未获授权内容必须放在该目录之外。
- 修改飞书文档并确认“已保存到云端”后，可手动运行 **Publish complete COOC courses from Feishu Wiki**，或等待每天北京时间 10:17 自动同步。

完整操作步骤见 [飞书课程维护与 GitHub Pages 发布 HOW-TO](docs/feishu-course-maintenance-how-to.md)。

## COOC-China 初始迁移

仓库提供受保护的手动工作流 **Import 20 COOC-China courses into Feishu**。它从 `COOC-China/cooc-china.github.io` 的公开 `_posts/` 读取 20 门课程，创建尚不存在的同名飞书文档，写入正文、分类、原始发布日期、外部学习链接和课程封面。

运行时在 `confirm` 输入框填写 `IMPORT_COOC_CHINA_20`。再次运行会跳过同名课程，不会重复创建。成功后立即运行 **Publish complete COOC courses from Feishu Wiki**，将飞书内容同步到 Pages。

初始迁移后，课程编辑只在 `COOC 课程内容管理` 知识库完成：修改标题、正文、图片或附件，然后运行同步工作流或等待每日计划任务。`课程分类：` 与 `原始发布日期：` 是文档内的可见元数据，用于首页分类、发布时间和排序；不显示在公开课程正文中。

## 授权图书全文试点

**Import authorized COOC embedded systems book into Feishu** 是 `COOC-China/Embedded-System-Development-Book` 的一次性全文初始化工具。它依据 `SUMMARY.md` 导入仓库中全部非重复的 Markdown 正文和本地图片到现有的 `嵌入式系统底层开发` 飞书课程文档，并把旧的“学习课程”外部链接替换为本页维护说明。原始在线演示脚本不会嵌入公开页；请由编辑者在飞书中补充本地课件或附件。

运行时在 `confirm` 填写 `IMPORT_COOC_EMBEDDED_SYSTEM_BOOK`。导入标记已存在时任务会安全退出，不会覆盖教师后续在飞书中的修改。全文迁移完成后，日常更新只编辑飞书并运行常规发布工作流；不要重复运行此初始化任务。若需撤回初始化，请在飞书版本历史中恢复到导入前版本，再运行发布工作流。

## 本地验证

```sh
# 用非敏感样例生成完整静态站点
python3 scripts/sync_feishu_wiki.py --input samples/feishu-wiki-nodes.json

# 对已提取的官方 20 门课程执行不写入飞书的演练
python3 scripts/import_cooc_china.py --source-directory /path/to/posts --dry-run

# 对已检出的授权图书全文执行不写入飞书的演练
python3 scripts/import_embedded_system_book.py --source-directory /path/to/Embedded-System-Development-Book --dry-run

# 运行全部测试
python3 -m unittest discover -s tests -v

# 本地预览
python3 -m http.server 4173 -d site
```

## 生产配置与边界

GitHub Secrets 仅保存：

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_WIKI_PUBLIC_ROOT_TOKEN` — `公开课程` Wiki 节点 token

飞书自建应用需要在目标知识库具有编辑权限，并开通 `wiki:wiki`、`docx:document`、`docs:document.media:upload` 和媒体下载能力。凭证、私有链接和 token 不得写入仓库、静态页或工作流日志。

`公开课程` 的每一个直接 `docx` 子文档都会公开复制到 GitHub 仓库和 Pages。因此不要放置机密、仅内部授权的内容或凭证；草稿与内部资料应放在其他知识库位置。
