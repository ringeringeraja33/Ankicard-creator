# Anki Card Organizer

将语言素材整理成短篇幅 Anki 语言积累卡，并通过本机 AnkiConnect 在逐批确认后导入。

## 功能

- 来源标题、原文列点、中文释义与必要讲解；B2–C1 重点词汇在下一行缩进，附词性、复数与常见搭配。
- 每卡约 4–6 个原文要点，按词汇密度调整；长素材拆卡。
- 每批询问 Deck、标签规则和正反面内容，展示全部预览后等待用户确认。
- 连接档案、笔记类型、字段及模板检查；确认摘要绑定本批内容与设置。
- Anki 首字段去重预检、逐条新增、字段／标签／牌组／卡片数量读回验证。
- 本地回执记录部分成功与未知结果，禁止自动重试未知写入；不会覆盖笔记或自动同步 AnkiWeb。

## 安装为 Agent Skill

将仓库中的 `anki-card-organizer` 文件夹复制到代理支持的技能目录，例如工作区 `.agents/skills/` 或个人 `~/.codex/skills/`。保留目录结构，从 [SKILL.md](anki-card-organizer/SKILL.md) 进入。

仅整理文字无需 Anki。直接导入需要 Python 3.10+、已打开的 Anki 桌面版和启用的 [AnkiConnect](https://ankiweb.net/shared/info/2055492159)。默认访问 `http://127.0.0.1:8765`，脚本仅依赖 Python 标准库。它使用 AnkiConnect 的 API，不捆绑插件本体。

详细连接、批次 JSON 格式、确认命令及恢复规则见 [AnkiConnect 操作流程](anki-card-organizer/references/ankiconnect.md)。

## 使用

对代理说：“把这些素材整理为语言积累卡，并加入 Anki；先询问 Deck、tag 规则和正反面内容。”

从仓库根目录执行只读连接检查或测试：

```text
python -X utf8 anki-card-organizer/scripts/anki_connect.py inspect
python -X utf8 -m unittest discover -s anki-card-organizer/tests -v
```

脚本中的确认摘要用于防止预览后内容变更；用户授权由代理在对话中取得，摘要本身不代表授权。

## 范围与隐私

当前导入器支持现有的双字段、单模板基础笔记类型，支持本地化字段名和背面留空。挖空、反向卡、多模板、额外字段、媒体下载、建牌组、改模板、删除、覆盖及 AnkiWeb 同步不在当前自动导入范围内。

私人素材与批次 JSON 保存在仓库外。回执默认在用户目录 `.anki-card-organizer/receipts/`。密钥只通过 `ANKICONNECT_API_KEY` 环境变量传入，不提交密钥、回执或学习内容。测试使用原创示例及隔离的模拟 HTTP 服务，不接触真实 Anki。

归档 API 文档与实际安装版本可能不同；`inspect` 或后续只读调用遇到不支持的方法时停止，不降级为直接数据库写入。导入期间不要切换 Anki 档案或编辑相关模板。
