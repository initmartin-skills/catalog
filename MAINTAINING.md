# 维护这份目录

本目录是 [initmartin-skills/catalog](https://github.com/initmartin-skills/catalog) 的根目录，是技能目录的唯一维护来源。浏览入口：https://initmartin-skills.github.io/catalog/

只编辑 `catalog.json`。新增条目时按已有记录填写：稳定 id、name、用途、分类、标签、upstream、fork（可空）、相对 path、40位 commit、license、status、reviewed_at、customized、used_in 和 notes。

当前唯一条目来自实际的 oil-ui Fork，状态 saved。没有已验证常用包，没有执行安装。

## 三个命令

在本目录打开终端：

```sh
python3 scripts/build_catalog.py
python3 scripts/build_catalog.py --check
python3 -m unittest discover -s tests -v
```

第一个命令生成 README.md 和 index.html；另两个检查一致性和规则。没有网络调用，不会执行第三方技能。

## 什么时候升级状态

saved 表示收录，trial 表示试用，approved 表示已经记录审阅日期和实际任务结果。常用包只能放 approved 条目。
元数据通过校验不等于内容或效果已经验证。许可证字段要照来源填写；采用前自行确认具体授权。

## 更新来源

已采用版本固定到完整 commit。更新 Fork 不会自动更新 adopted commit；通过一个代表任务后再改目录。
Fork 放在 `initmartin-skills` 组织中，默认保留上游仓库名。一个仓库可登记多个技能，分别记录 SKILL.md 所在目录和稳定 ID。新增收藏先使用 saved 状态；不必马上验证整个仓库中的所有技能。

`organization` 当前为 `initmartin-skills`。迁移或改名时同时更新 fork 字段和相关 notes。自己的修改放独立分支，保留原作者和许可证；不要强推覆盖自定义提交。

## 工作流

`.github/workflows/catalog-check.yml` 检查元数据、生成文件与测试。
它只在提交、PR、手动运行时检查；没有定时触发、写权限或 Secrets。网页由 main 分支根目录的 GitHub Pages 发布。
第三方技能 Fork 的工作流与本目录不同，需要单独审阅。

