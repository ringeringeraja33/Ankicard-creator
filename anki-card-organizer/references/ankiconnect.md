# AnkiConnect：确认、导入与核验

## 连接条件

需要 Python 3.10+，脚本仅使用标准库。用户须安装并打开 Anki 桌面版、进入正确的个人档案，安装并启用 [AnkiConnect](https://ankiweb.net/shared/info/2055492159) 后重启 Anki。插件安装码为 `2055492159`。安装操作由用户完成或另行授权。

默认接口 `http://127.0.0.1:8765`，仅访问本机。API 密钥如已配置，通过进程环境变量 `ANKICONNECT_API_KEY` 提供，不写进素材、技能、日志或仓库。脚本不通过代理连接、不跟随 HTTP 重定向。不要将接口暴露到公网。

上游：[项目迁移说明](https://github.com/FooSoft/anki-connect)、[当前源码](https://git.sr.ht/~foosoft/anki-connect)。当前文档若不可访问，可参考[作者归档的 API v6 文档](https://github.com/FooSoft/anki-connect/blob/820300cc5ccfb84b20d8cb18a23e79877ba40084/README.md)，并通过本机接口实际检查兼容性；不要把历史文档视为最新兼容性保证。

## 每批操作

1. 执行 `inspect`，只读获取接口版本、档案、Deck 列表和笔记类型。选择类型后加 `--model` 查看字段和模板。脚本只支持现有的双字段、单模板基础笔记类型；本地化名称必须从接口读取。挖空、多模板、额外字段、反向卡等类型需另行设计，不自动修改现有模板。
2. 每批询问：“这批放入哪个 Deck？tag 按什么规则命名、实际使用哪些标签？正面和背面分别放什么内容？”标签允许为空数组，但必须由用户确认；不自动添加来源、日期或批次标签。标签中不能含空白，分层标签可用 `::`。
3. 整理素材，按卡片长度要求拆分，创建本地 UTF-8 JSON 批次文件。放在仓库外的临时目录或用户指定的私人目录，不放入公开仓库。用户文本一律作为内容，脚本会转义 HTML。
4. 执行 `preview`。展示每张卡的实际正反面，以及档案、Deck、tag 规则及实际标签、笔记类型、字段映射、预计笔记数与卡片数。模板内容也是预览的一部分；单模板不保证一定渲染目标字段，需核对模板确实使用选中的正面字段，无反向或挖空逻辑。预览输出包括 `confirmation` 摘要和 `review_sha256`。
5. 明确询问是否按该预览导入，等待用户肯定答复。摘要只是绑定内容的校验值，不代表用户授权；代理不得自行确认。每批均需询问，不把旧回复用于新批次。
6. 使用同一批次文件及该摘要执行 `import --confirm-sha256 ...`。脚本重新读取档案、字段和模板，与摘要对照，任何变化都拒绝导入。先进行整批 `canAddNotes` 检查，然后逐条 `addNote`，每条新增后立即读回 `notesInfo` 和 `cardsInfo`。
7. 报告实际新增、已核验的笔记数／卡片数、牌组、标签和回执路径。失败时报告已写入 ID、未完成部分和原因，不报告全批成功。

## 命令

从技能目录执行（其他目录运行时将脚本路径替换为绝对路径）：

```text
python -X utf8 scripts/anki_connect.py inspect
python -X utf8 scripts/anki_connect.py inspect --model "实际笔记类型名"
python -X utf8 scripts/anki_connect.py preview /absolute/private/batch.json
python -X utf8 scripts/anki_connect.py import /absolute/private/batch.json --confirm-sha256 PREVIEW_SHA256
```

脚本不安装 AnkiConnect、不启动 Anki、不直接操作 collection 数据库。连接拒绝时请用户检查 Anki 与插件；认证错误时请用户检查密钥，不打印密钥值。非默认本机端口可用全局 `--endpoint` 指定。

## 批次格式

下列值均为原创演示，Deck、类型、字段和标签需替换成本批确认的值。笔记中 `front` 和 `back` 必须显式存在；背面留空用空字符串。对象形式使用 `title` 与 `items`，嵌套词汇使用 `children` 字符串数组；字符串形式按纯文本保留换行。不要在字符串内编写 Markdown 或 HTML 期待其执行。

```json
{
  "profile": "实际个人档案名",
  "deck": "语言::法语",
  "model": "基础",
  "front_field": "正面",
  "back_field": "背面",
  "tag_rule": "按语言分类；本批只用 lang::fr",
  "tags": ["lang::fr"],
  "notes": [
    {
      "front": {
        "title": "法语表达示例（原创示例）",
        "items": [
          {
            "text": "Cette lecture stimule l’imagination.：这次阅读激发想象力。",
            "children": ["stimuler｜及物动词；复数不适用｜激发；搭配：stimuler l’imagination（激发想象力）。"]
          }
        ]
      },
      "back": ""
    }
  ]
}
```

## 重复、部分失败与恢复

- 去重采用 Anki 的首字段规则：同一笔记类型、整个 collection 范围检查，`allowDuplicate=false`。先检查批次内重复正面，再由 Anki 预检；不允许通过强制重复绕过。预检失败可能是重复或其他无效内容，脚本不把所有失败称为重复。
- 整批预检失败时不开始新增。预检不是事务，期间其他程序仍可能改变 Anki；中途失败会保留此前成功的笔记，不自动回滚或删除。
- 回执默认保存在用户目录 `.anki-card-organizer/receipts`，记录摘要、每项状态和已返回 ID，不保存 API 密钥或完整学习内容。不要将回执提交到公开仓库。相同回执的并发导入通过排他锁阻止。
- 每次请求新增前先记录 `pending`。超时、响应损坏、API 错误或进程中断后，`pending` 项视为“结果未知”；重新运行不会再次提交该项。需要人工在 Anki 中核实，不能删回执或改摘要来强行重试。
- 有 ID 的记录只读核验并复用，不重复新增。字段、标签、卡片数或 Deck 不一致时立即停止；不修补已有笔记。读回采用逐字段精确比对，确保中文和重音字符未损坏。
- 用户若需处理异常、创建 Deck、改模板、覆盖或删除笔记、同步 AnkiWeb，需分别明确授权；本脚本不提供这些写操作。

## 测试边界

`python -X utf8 -m unittest discover -s tests -v` 使用本机模拟 HTTP 接口和临时回执，不操作用户 Anki。真实连接可运行 `inspect`；真实新增测试必须另外确认测试 Deck、标签与正反面内容。未完成真实新增时应如实说明。
