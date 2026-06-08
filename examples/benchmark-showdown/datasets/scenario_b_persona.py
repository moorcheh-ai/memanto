"""
场景B: 动态偏好时序追踪测试
- 模拟用户偏好随时间变化/矛盾的情况
- 测试记忆框架在多轮会话中追踪偏好演变的能力
"""
from __future__ import annotations

from dataclasses import dataclass

from backends.base import MemoryEntry


@dataclass
class PreferenceSession:
    """单次会话中的偏好声明"""
    session_id: int
    entries: list[MemoryEntry]
    expected_current_preferences: dict[str, str]
    description: str


# 时序偏好会话 - 模拟偏好随时间变化
PREFERENCE_SESSIONS: list[PreferenceSession] = [
    PreferenceSession(
        session_id=1,
        description="初始偏好设定",
        entries=[
            MemoryEntry(
                content="I prefer dark roast coffee, black, no sugar. "
                        "I drink it every morning around 7am.",
                memory_type="preference",
            ),
            MemoryEntry(
                content="My favorite programming language is Python. "
                        "I prefer VS Code as my editor with the One Dark theme.",
                memory_type="preference",
            ),
            MemoryEntry(
                content="I'm vegetarian and allergic to peanuts. "
                        "I enjoy Italian and Japanese cuisine.",
                memory_type="preference",
            ),
        ],
        expected_current_preferences={
            "coffee": "dark roast, black, no sugar",
            "editor": "VS Code with One Dark theme",
            "diet": "vegetarian, peanut allergy",
        },
    ),
    PreferenceSession(
        session_id=2,
        description="偏好变化 - 切换到浅焙",
        entries=[
            MemoryEntry(
                content="Actually, I've been trying light roast coffee lately. "
                        "I find it less bitter and I can taste more of the origin flavors. "
                        "Still black, no sugar though.",
                memory_type="preference",
            ),
            MemoryEntry(
                content="I started using Neovim instead of VS Code. "
                        "The modal editing is much faster once you get used to it. "
                        "Using the Catppuccin Mocha theme now.",
                memory_type="preference",
            ),
        ],
        expected_current_preferences={
            "coffee": "light roast, black, no sugar",
            "editor": "Neovim with Catppuccin Mocha theme",
            "diet": "vegetarian, peanut allergy",  # unchanged
        },
    ),
    PreferenceSession(
        session_id=3,
        description="饮食偏好矛盾 - 开始吃鱼",
        entries=[
            MemoryEntry(
                content="I've decided to start eating fish. "
                        "So I'm pescatarian now, not strictly vegetarian. "
                        "Still allergic to peanuts though.",
                memory_type="preference",
            ),
            MemoryEntry(
                content="I discovered cold brew coffee and I love it. "
                        "But I still enjoy a good light roast pour-over in the morning.",
                memory_type="preference",
            ),
            MemoryEntry(
                content="For my birthday, I want a mechanical keyboard. "
                        "Preferably with Cherry MX Brown switches. "
                        "I've been eyeing the Keychron Q1.",
                memory_type="goal",
            ),
        ],
        expected_current_preferences={
            "coffee": "cold brew and light roast pour-over",
            "editor": "Neovim with Catppuccin Mocha theme",
            "diet": "pescatarian, peanut allergy",
            "birthday": "mechanical keyboard, Cherry MX Brown, Keychron Q1",
        },
    ),
    PreferenceSession(
        session_id=4,
        description="最终偏好确认",
        entries=[
            MemoryEntry(
                content="I'm going back to VS Code. Neovim was cool but I need "
                        "the integrated debugger and Copilot support for my current project.",
                memory_type="preference",
            ),
            MemoryEntry(
                content="Update: I actually got the Keychron Q3 instead of Q1. "
                        "The TKL layout works better for my desk setup.",
                memory_type="context",
            ),
        ],
        expected_current_preferences={
            "coffee": "cold brew and light roast pour-over",
            "editor": "VS Code (returned from Neovim)",
            "diet": "pescatarian, peanut allergy",
            "keyboard": "Keychron Q3, Cherry MX Brown (changed from Q1)",
        },
    ),
]

# 偏好追踪查询 - 检索当前最新偏好
PREFERENCE_QUERIES = [
    "What kind of coffee do I prefer right now?",
    "Which code editor am I currently using?",
    "What are my dietary restrictions?",
    "What keyboard do I want for my birthday?",
]

# 期望答案
PREFERENCE_GOLDEN = {
    "What kind of coffee do I prefer right now?": [
        "cold brew and light roast pour-over",
    ],
    "Which code editor am I currently using?": [
        "VS Code",
    ],
    "What are my dietary restrictions?": [
        "pescatarian, peanut allergy",
    ],
    "What keyboard do I want for my birthday?": [
        "Keychron Q3",
    ],
}
