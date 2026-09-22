# handoff-kit

让 `/clear` 不再丢上下文。

长会话贵的不是模型单价，是**每一轮都要重读整个上下文**。Opus 5 缓存读取 $0.50/MTok，400k 上下文每轮就是 $0.20；压到 120k 是 $0.06。同样的活，差三倍多。

但 `/clear` 之所以让人不敢按，是因为它真的会丢东西。这个插件把连续性从对话搬到磁盘，让 `/clear` 变成免费操作。

## 两层模型

寿命不同的东西必须分开存，这是全部设计的核心：

| 文件 | 内容 | 寿命 | 写法 |
|---|---|---|---|
| `DECISIONS.md` | 目标、约束、决策+理由、**被否决的方案+原因** | 整个项目 | **只追加，永不重写** |
| `STATE.md` | 进度、下一步、卡点、关键命令 | 到下次 `/clear` | 整个覆盖，≤150 行 |

混在一个文件里，决策层会被状态层的反复重写churn掉——你会发现自己在手动做 `HANDOFF_HISTORY_20260920.md` 这种归档。

## 用法

```
/handoff        # 写入两个文件 + 只提交这两个文件
/clear          # 手动，见下
```

新会话**什么都不用做**——`SessionStart` hook 自动注入。

### 为什么 `/clear` 保持手动

技术上可以自动化，但这是整个流程里唯一一个你能在上下文消失前亲眼检查 handoff 的点。写漏了，手动模式下还能说「补上 X」；自动模式下能补救的那个会话已经没了。

（真清错了也不是绝路：transcript 还在磁盘上，`claude --resume` 能捞回来。）

### 注入预算

`STATE.md` 全量注入（有 150 行上限），`DECISIONS.md` **只注入标题 + 路径**，需要细节时模型自己 Read。

这条很关键：决策日志是只追加的，几个月后会到几十 KB。全量注入等于用新方式重建上下文膨胀，那整套就白做了。开局成本压在 1–2k tokens。

### 过期警告

如果 `STATE.md` 比最新改动的源文件早 6 小时以上，注入内容顶部会加警告。

主要防 `cp -r` 复制实验目录——`STATE.md` 跟着复制过来，描述的却是父实验的状态。这比没有 handoff 更危险：没有时模型会去看代码，有假的时它不会。

**复制实验目录后第一件事：删掉 `STATE.md`。** `DECISIONS.md` 可以继承，状态不行。

## 安装

```
/plugin marketplace add <your-gh-user>/handoff-kit
/plugin install handoff-kit@handoff-kit
```

依赖：`python3`（系统自带即可）、`git`（可选，没有就跳过提交）。

## 配套的 token 配置

插件管不了这些，但和它是同一件事。`~/.claude/settings.json`：

```json
{
  "model": "opus",
  "env": {
    "CLAUDE_CODE_SUBAGENT_MODEL": "sonnet"
  }
}
```

- **`opus` 而非 `opus[1m]`** — auto-compact 窗口是跟着模型上下文大小走的。用 1M 变体，会话永远不触发压缩，一路涨到 300–500k。需要长上下文时临时 `/model opus[1m]` 切一次。
- **`CLAUDE_CODE_SUBAGENT_MODEL`** — 内置 agent（general-purpose / Explore / Plan）默认继承主模型。不设这个，你在 agent 文件里配的 haiku/sonnet 路由会被它们绕过。自定义 agent 的 `model:` 字段优先级更高，不受影响。

可选：`CLAUDE_CODE_AUTO_COMPACT_WINDOW` 可以强制更小的压缩窗口，但官方默认的 `auto` 是按模型调过的，压太勤会反复重读文件，可能不省反亏。先别动。
