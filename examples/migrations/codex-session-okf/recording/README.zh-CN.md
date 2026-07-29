# 录制包使用说明

## 今天：只做安全彩排

```bash
cd /workspace/memanto-migration
examples/migrations/codex-session-okf/recording/preflight.sh
MEMANTO_DEMO_AUTO=1 \
  examples/migrations/codex-session-okf/recording/record_demo.sh
```

默认彩排不会写入云端，只执行转换、测试、黄金验证和 Memanto dry-run。

## 明天：正式录制

1. 打开录屏软件，选择“仅录制终端窗口”。
2. 将终端最大化，字号调整到 20–24 px。
3. 运行 `preflight.sh`；全部显示 `OK` 后清屏。
4. 开始录屏。
5. 运行：

```bash
MEMANTO_RECORD_LIVE=1 \
  examples/migrations/codex-session-okf/recording/record_demo.sh
```

6. 每一幕结束后，脚本会等待 Enter。按照镜头表控制节奏。
7. Freedom Loop 总结出现后停止录屏。
8. 将视频文件交给 Codex 做敏感信息检查，再决定是否发布。

正式脚本会用时间戳创建全新的隔离 Agent，避免与之前的测试数据混合。

## 文件说明

- `preflight.sh`：认证、权限、样本安全和仓库状态检查。
- `record_demo.sh`：逐幕演示脚本。
- `SHOT_LIST.zh-CN.md`：镜头和时间安排。
- `NARRATION.en.md`：英文旁白全文。
- `SUBTITLES.srt`：可直接导入剪辑软件的英文字幕。
- `PUBLISHING_COPY.md`：YouTube、X、LinkedIn 发布草稿。
