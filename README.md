# Martin’s Skills Library

按用途保存，按验证版本使用。

[打开可搜索目录](https://initmartin-skills.github.io/catalog/) · [维护说明](MAINTAINING.md) · [组织主页](https://github.com/initmartin-skills)

此文件由 scripts/build_catalog.py 根据 catalog.json 生成。元数据校验不代表技能已通过内容、安全或效果审阅。

| Skill | 用途 | 分类 | 状态 | 采用提交 | 来源 |
| --- | --- | --- | --- | --- | --- |
| [oil-ui](https://github.com/initmartin-skills/oil-ui/blob/a3343469e422078a1433d38eb9a5915df256ddc2/SKILL.md) | 为界面设计探索方向、细化方案和评审真实截图。 | design | saved | a3343469e4 | oil-oil/oil-ui |

## 常用包

- **design**：尚未选定已验证条目
- **apple-development**：尚未选定已验证条目
- **content**：尚未选定已验证条目

## 状态

saved → trial → approved；暂停使用标记 paused，停止采用标记 retired。收藏不等于安装。

## 更新目录

```sh
python3 scripts/build_catalog.py
python3 scripts/build_catalog.py --check
```

安装由现有客户端或 Skills CLI 完成；本生成器不会联网、运行技能、改名或修改 GitHub 设置。
