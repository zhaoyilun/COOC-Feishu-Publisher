# COOC Feishu Publisher

无服务器的静态课程发布器：编辑者只维护飞书知识库，学习者只访问 GitHub Pages。GitHub Actions 读取公开课程 Wiki，生成完整静态课程页并将图片、附件下载到站点内；读者不需要飞书账号。

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

## COOC-China 初始迁移

仓库提供受保护的手动工作流 **Import 20 COOC-China courses into Feishu**。它从 `COOC-China/cooc-china.github.io` 的公开 `_posts/` 读取 20 门课程，创建尚不存在的同名飞书文档，写入正文、分类、原始发布日期、外部学习链接和课程封面。

运行时在 `confirm` 输入框填写 `IMPORT_COOC_CHINA_20`。再次运行会跳过同名课程，不会重复创建。成功后立即运行 **Publish complete COOC courses from Feishu Wiki**，将飞书内容同步到 Pages。

初始迁移后，课程编辑只在飞书完成：修改标题、正文、图片或附件，然后运行同步工作流或等待每日计划任务。`课程分类：` 与 `原始发布日期：` 是文档内的可见元数据，用于首页分类、发布时间和排序；不显示在公开课程正文中。

## 本地验证

```sh
# 用非敏感样例生成完整静态站点
python3 scripts/sync_feishu_wiki.py --input samples/feishu-wiki-nodes.json

# 对已提取的官方 20 门课程执行不写入飞书的演练
python3 scripts/import_cooc_china.py --source-directory /path/to/posts --dry-run

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
