# 两分钟录屏镜头表

建议成片 2:15–3:00，纯屏幕即可，不需要真人出镜。录制区域只包含演示终端，
不要录制整个桌面、飞书通知栏或共享浏览器的其他标签页。

## 录制设置

- 画面：1920×1080，30 FPS。
- 终端字号：20–24 px；深色背景；窗口最大化。
- 关闭桌面通知、终端历史联想和密码管理器弹窗。
- 不打开 `~/.memanto/.env`、Moorcheh API Keys 页面或 `memanto status`。
- 可不录声音，后期使用 `SUBTITLES.srt`。

## 镜头顺序

| 时间 | 屏幕内容 | 重点 |
| --- | --- | --- |
| 0:00–0:12 | 标题卡或 Scene 1 标题 | Codex memory, freed with OKF |
| 0:12–0:32 | 4 条公开 Codex 消息摘要 | 真实来源；私密内部记录不进入公开样本 |
| 0:32–0:55 | 转换命令和 OKF Markdown | 普通 Markdown，可读、可迁移 |
| 0:55–1:15 | 隐私测试和 3/3 parity | 工具调用、推理、凭据被排除 |
| 1:15–1:35 | `--dry-run` 映射 | 4 nodes → 4 context memories |
| 1:35–1:55 | 云端真实导入 | 4 imported、0 failed |
| 1:55–2:25 | 三个问题，每题只显示 Top 1 | 日期、memanto、bounty-radar |
| 2:25–2:45 | 重新导出 OKF | 4 memories exported |
| 2:45–2:55 | Freedom loop 总结 | in → owned → portable |

录制时运行：

```bash
cd /workspace/memanto-migration
MEMANTO_RECORD_LIVE=1 \
  examples/migrations/codex-session-okf/recording/record_demo.sh
```

每个 Scene 结束后脚本会暂停。确认画面稳定后按 Enter 进入下一幕。
