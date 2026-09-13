---
title: CogniMem 记忆导出 - OKF 捆绑包
description: 通过 CogniMem → OKF 适配器迁移的记忆，共52条
timestamp: 2026-07-25T18:54:15Z
tags: [cognimem, migration, memory]
x_memanto:
  source: cognimem-migration-adapter
  adapter_version: 1.0.0
---

# 🧠 CogniMem 记忆导出

> 通过 CogniMem → OKF 迁移适配器导出 • 52 条记忆 • 11 个 Agent

## 捆绑包结构

```
okf-bundle/
├── index.md              # 此文件
├── memories/
│   ├── index.md          # 记忆目录
│   ├── event/        # 事件记忆
│   ├── fact/        # 事实记忆
│   ├── observation/        # 观察记忆
│   ├── preference/        # 偏好记忆
│   │   ├── index.md
│   │   └── *.md
├── metrics/
│   └── overview.md       # 统计概览
```

## 使用方法

```bash
# 1. 将此捆绑包导入 Memanto
memanto migrate okf ./okf-bundle --dry-run    # 预览
memanto migrate okf ./okf-bundle --agent my-agent  # 执行

# 2. 或从 Memanto 导出为 OKF（往返验证）
memanto memory export --okf
```

## 迁移摘要

从 CogniMem 数据库读取了 **52** 条事实三元组，映射到 **4** 种 Memanto 记忆类型。

- **源系统**: CogniMem（认知记忆系统）
- **目标系统**: Memanto + OKF
- **导出时间**: {stats['timestamp']}
- **适配器版本**: 1.0.0