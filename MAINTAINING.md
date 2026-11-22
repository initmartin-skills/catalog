# 维护这份目录

[打开技能目录](https://initmartin-skills.github.io/catalog/) · [立即扫描 / 查看运行记录](https://github.com/initmartin-skills/catalog/actions/workflows/sync-catalog.yml)

## 以后怎样收藏

在 GitHub 上点击技能项目的 **Fork**，Owner 推荐选择 **initmartin-skills**。Fork 到个人账号 **initmartin-alt** 的公开项目也会收录，无需再手动添加目录条目。

扫描计划为每小时第 17 分钟，由 GitHub Actions 运行。GitHub 调度可能延迟；大量项目首次扫描遇到接口限额时，可能需要后续轮次补全。Mac 关机不影响运行。想立即更新，打开上面的运行记录链接，点击 **Run workflow → Run workflow**；通常无需勾选 `refresh`。

只扫描这两个账号下的**公开 Fork**，读取默认分支里根目录和子目录中名称精确为 `SKILL.md` 的常规文件。一个仓库里的多个技能分别收录；没有该文件的项目不会产生技能条目。私有仓库与原创仓库不在自动扫描范围。

新技能显示为 **inbox（待分类） / saved**。名称、用途、来源与许可证会尽量从文件和仓库元数据提取；许可证仍需在采用时核对具体技能。收录不会安装或执行技能，也不会同步上游、迁移仓库或自动批准使用。

## 哪些文件可以编辑

| 文件 | 用途 |
| --- | --- |
| `catalog.json` | 手工分类、说明、审阅状态、采用版本和常用包；优先于扫描结果 |
| `sources.json` | 扫描账号和排除名单；`exclude_repositories` 填 `owner/repository` |
| `discovered.json` | 自动发现记录和缓存，由工作流维护，不手工编辑 |
| `README.md` / `index.html` | 自动生成的仓库目录和网页，不直接编辑 |

要给自动条目分类或补充说明，从 `discovered.json` 的对应仓库 `skills` 数组复制该条目到 `catalog.json` 的 `skills` 数组，保留 `id`、`repository_id` 和 `path`，再修改 `category`、`summary` 等字段。可以删除复制记录中的 `blob_sha`、`extracted` 和 `metadata_error`；它们仅供扫描缓存使用。新分类先添加到 `categories`。

提交到 main 后会自动重建并发布。手工条目与自动条目按仓库 ID 和路径合并，不重复显示；仓库改名或转移到另一扫描账号后，地址会随扫描更新。排除名单只移除自动条目，已经手工登记的条目仍保留。

## 状态与版本

`saved` 表示收录，`trial` 表示试用，`approved` 表示已填写审阅日期与实际任务结果；常用包只能放 `approved` 条目。元数据校验不代表内容或效果已经验证。

尚未手工登记的自动条目随 Fork 默认分支更新。进入 `catalog.json` 的手工条目会固定到完整的 40 位 `commit`：自动扫描保留你的分类、说明、状态、采用提交与常用包，来源有更新时只显示提示。试用新版本后再手工修改采用提交。

## 扫描、缓存与异常

未变化的仓库使用缓存；变化的仓库重新查目录，只读取有变化的技能文件。每次运行的摘要记录扫描量和异常数，`discovered.json` 保存最近检查日期（北京时间），每天第一次成功检查会更新日期记录。同一天无变化时不产生额外提交。

单个来源或文件读取失败时保留已有记录和成功读取的进度，下轮重试；页面会标记扫描不完整。来源移出公开 Fork 列表时保留历史并标记暂不可用。账号列表请求失败时整个扫描失败，保留原快照。查看 Actions 日志可以区分接口限额、权限或来源问题。`refresh` 强制重新检查仓库目录，仍复用内容未变化的文件缓存。

当前单仓库最多检查 200,000 个树条目；超过 256 KiB 的技能文件只记录路径和仓库信息，不提取正文元数据。可在 `sources.json` 调整限制。

## 本地维护与工作流

本地生成与检查（不访问网络、不执行技能）：

```sh
python3 scripts/build_catalog.py
python3 scripts/build_catalog.py --check
python3 -m unittest discover -s tests -v
```

`scripts/discover_skills.py` 单独负责联网扫描，可通过环境变量 `GH_TOKEN` 或 `GITHUB_TOKEN` 使用已有认证；不要把令牌写入仓库。

`.github/workflows/catalog-check.yml` 在提交、PR 和手动运行时校验目录并运行测试，只有读取权限。

`.github/workflows/sync-catalog.yml` 在定时、手动触发和相关文件推送到 main 时扫描、生成、提交结果并部署 GitHub Pages。它使用 GitHub 自动提供的 `GITHUB_TOKEN`，不需要额外 PAT 或 Secrets。扫描作业有目录仓库写权限，部署作业有 Pages 与 OIDC 权限。并发任务串行执行；提交使用普通 push，不强推覆盖他人的修改。

Pages 的发布来源是 **GitHub Actions**。扫描机器人提交与网站部署在同一次工作流中完成，确保自动收录后网页也更新。第三方 Fork 自己的工作流与本目录的扫描无关。
