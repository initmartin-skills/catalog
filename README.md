# Martin’s Skills Library

按用途保存，按验证版本使用。

[打开可搜索目录](https://initmartin-skills.github.io/catalog/) · [维护说明](MAINTAINING.md) · [组织主页](https://github.com/initmartin-skills)

自动扫描组织和个人账号的公开 Fork。新条目进入 inbox（待分类）/ saved；catalog.json 中的手工记录优先，采用版本不会被自动更新。

[手动立即扫描](https://github.com/initmartin-skills/catalog/actions/workflows/sync-catalog.yml) · [扫描来源配置](sources.json)

| Skill | 用途 | 分类 | 状态 | 采用提交 | 来源 |
| --- | --- | --- | --- | --- | --- |
| [oil-ui](https://github.com/initmartin-skills/oil-ui/blob/a3343469e422078a1433d38eb9a5915df256ddc2/SKILL.md) | 为界面设计探索方向、细化方案和评审真实截图。 | design | saved | a3343469e4 | oil-oil/oil-ui |
| [stickman-video-director](https://github.com/initmartin-alt/stickman-video-director/blob/eda39dc083c32df0066611a9dc8e84067989044d/SKILL.md) | 火柴人视频导演 Skill for Muse — stickman story video production skill (scene generation, voiceover, BGM, editing) | inbox | saved | eda39dc083 | CryptoYuyyy02/stickman-video-director |

最近检查（北京时间）：2026-11-23 · 来源仓库：4 · 异常：0

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
