# Timeline Visualization Examples

**For**: Developers building dashboards and visualization tools
**Status**: Reference Examples

---

## Introduction

MEMANTO's hybrid timeline model (automatic timestamps + semantic timeline) enables powerful visualizations of agent activity, project progress, and memory patterns over time.

This guide provides practical examples for visualizing timeline data.

---

## Data Sources

### Level 1: Automatic Timestamps
Every memory has:
- `created_at`: When memory was stored
- `updated_at`: When memory was last modified

### Level 2: Semantic Timeline
Agents can store:
- **Sessions**: `type=fact`, `tags=[timeline, session-start]`
- **Milestones**: `type=event`, `tags=[timeline, milestone]`
- **Phases**: `type=fact`, `tags=[timeline, phase-transition]`

---

## Example 1: Activity Heatmap

**Use Case**: Visualize when agent is most active

**Query**:
```bash
curl -X POST "http://localhost:8000/api/v2/agents/{agent_id}/recall/changed-since" \
  -H "X-Session-Token: {session_token}" \
  -H "Content-Type: application/json" \
  -d '{"since":"2025-12-01T00:00:00Z","limit":100}'
```

**Visualization** (Python + Matplotlib):
```python
import matplotlib.pyplot as plt
from datetime import datetime
from collections import Counter

# Parse timestamps from memories
timestamps = [
    datetime.fromisoformat(m['created_at'].replace('Z', ''))
    for m in memories if 'created_at' in m
]

# Group by hour of day
hours = Counter(ts.hour for ts in timestamps)

# Plot heatmap
plt.figure(figsize=(12, 4))
plt.bar(hours.keys(), hours.values())
plt.xlabel('Hour of Day (UTC)')
plt.ylabel('Memory Count')
plt.title('Agent Activity Heatmap')
plt.xticks(range(24))
plt.show()
```

**Output**:
```
Agent Activity Heatmap
     │
 150 │         ██
 100 │     ██  ██  ██
  50 │  ██ ██  ██  ██  ██
   0 └─────────────────────
     0  4  8  12 16 20 24
         Hour of Day (UTC)
```

---

## Example 2: Project Timeline with Milestones

**Use Case**: Show project progress with key events

**Query Semantic Timeline**:
```bash
curl "http://localhost:8000/api/v2/agents/{agent_id}/recall?\
query=timeline+milestone&\
memory_types=event,fact&\
limit=50" \
-H "X-Session-Token: {session_token}"
```

**Visualization** (Gantt-style timeline):
```python
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# Extract milestone events
milestones = [
    {
        'title': m['title'],
        'date': datetime.fromisoformat(m['created_at'].replace('Z', '')),
        'type': m['type']
    }
    for m in memories if 'milestone' in m.get('tags', [])
]

# Plot timeline
fig, ax = plt.subplots(figsize=(14, 6))

for i, milestone in enumerate(milestones):
    ax.scatter(milestone['date'], 0, s=200, marker='o',
               color='blue' if milestone['type'] == 'event' else 'green')
    ax.text(milestone['date'], 0.1, milestone['title'],
            rotation=45, ha='right', fontsize=9)

ax.set_ylim(-0.5, 1)
ax.set_xlabel('Date')
ax.set_title('Project Timeline with Milestones')
ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
ax.grid(axis='x', alpha=0.3)
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
```

**Output**:
```
Project Timeline with Milestones
         │
         │  Phase H      Namespace    Agent
         │  Complete     Bug Fix      Restoration
    1.0  │     ●            ●             ●
         │     │            │             │
         │─────┼────────────┼─────────────┼─────→
       0 └─────────────────────────────────────
         Dec 27      Dec 27         Dec 27
```

---

## Example 3: Memory Type Distribution Over Time

**Use Case**: Track what types of memories agent creates over time

**Query** (fetch everything since Dec 1, then client-side filter for the upper bound):
```bash
curl -X POST "http://localhost:8000/api/v2/agents/{agent_id}/recall/changed-since" \
  -H "X-Session-Token: {session_token}" \
  -H "Content-Type: application/json" \
  -d '{"since":"2025-12-01T00:00:00Z","limit":100}'
```

**Visualization** (Stacked Area Chart):
```python
import pandas as pd
import matplotlib.pyplot as plt

# Convert to DataFrame
df = pd.DataFrame([
    {
        'date': pd.to_datetime(m['created_at'].replace('Z', '')).date(),
        'type': m['type']
    }
    for m in memories if 'type' in m and 'created_at' in m
])

# Group by date and type
grouped = df.groupby(['date', 'type']).size().unstack(fill_value=0)

# Plot stacked area
fig, ax = plt.subplots(figsize=(12, 6))
grouped.plot.area(ax=ax, alpha=0.7, stacked=True)
ax.set_xlabel('Date')
ax.set_ylabel('Memory Count')
ax.set_title('Memory Type Distribution Over Time')
ax.legend(title='Memory Type', bbox_to_anchor=(1.05, 1))
plt.tight_layout()
plt.show()
```

**Output**:
```
Memory Type Distribution
         │
     50  │                    ┌─────────┐ commitment
         │                ┌───┤         │
     40  │            ┌───┤   │         │
         │        ┌───┤   │   │         │ decision
     30  │    ┌───┤   │   │   │         │
         │┌───┤   │   │   │   │         │ fact
     20  ││   │   │   │   │   │         │
         └────────────────────────────────→
         Dec 1    Dec 7   Dec 14  Dec 21
```

---

## Example 4: Session Duration Analysis

**Use Case**: How long are typical agent sessions?

**Query Sessions**:
```bash
curl "http://localhost:8000/api/v2/agents/{agent_id}/recall?\
query=session+start&\
tags=timeline,session-start&\
limit=100" \
-H "X-Session-Token: {session_token}"
```

**Calculation**:
```python
from datetime import datetime

# Extract session starts
sessions = sorted([
    datetime.fromisoformat(m['created_at'].replace('Z', ''))
    for m in memories if 'session-start' in m.get('tags', [])
])

# Calculate durations (time between sessions)
durations = [
    (sessions[i+1] - sessions[i]).total_seconds() / 3600  # hours
    for i in range(len(sessions) - 1)
]

# Plot histogram
import matplotlib.pyplot as plt

plt.figure(figsize=(10, 6))
plt.hist(durations, bins=20, edgecolor='black')
plt.xlabel('Session Duration (hours)')
plt.ylabel('Frequency')
plt.title('Agent Session Duration Distribution')
plt.axvline(sum(durations)/len(durations), color='red',
            linestyle='--', label=f'Mean: {sum(durations)/len(durations):.1f}h')
plt.legend()
plt.show()
```

---

## Example 5: Weekly Progress Dashboard

**Use Case**: Show agent progress week-over-week

**Combined Query**:
```python
def get_weekly_stats(agent_id, session_token, week_start):
    """Get statistics for a specific week"""

    week_end = week_start + timedelta(days=7)

    url = f"http://localhost:8000/api/v2/agents/{agent_id}/recall/changed-since"
    headers = {"X-Session-Token": session_token}
    response = requests.post(
        url, headers=headers, json={"since": f"{week_start.isoformat()}Z", "limit": 100}
    )
    upper_bound = f"{week_end.isoformat()}Z"
    memories = [m for m in response.json()['memories'] if m.get("created_at", "") <= upper_bound]

    return {
        'week': week_start.strftime('%Y-%m-%d'),
        'total_memories': len(memories),
        'decisions': sum(1 for m in memories if m.get('type') == 'decision'),
        'facts': sum(1 for m in memories if m.get('type') == 'fact'),
        'milestones': sum(1 for m in memories if 'milestone' in m.get('tags', []))
    }

# Get last 4 weeks
import pandas as pd
from datetime import datetime, timedelta

today = datetime.utcnow()
weeks = [today - timedelta(weeks=i) for i in range(4, 0, -1)]
stats = [get_weekly_stats(agent_id, session_token, week) for week in weeks]

# Create dashboard
df = pd.DataFrame(stats)

fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Total memories
axes[0, 0].bar(df['week'], df['total_memories'], color='skyblue')
axes[0, 0].set_title('Total Memories per Week')
axes[0, 0].tick_params(axis='x', rotation=45)

# Decisions
axes[0, 1].plot(df['week'], df['decisions'], marker='o', color='orange', linewidth=2)
axes[0, 1].set_title('Decisions Made per Week')
axes[0, 1].tick_params(axis='x', rotation=45)

# Memory type breakdown
memory_types = df[['decisions', 'facts']].T
axes[1, 0].stackplot(range(len(df)), memory_types.values, labels=memory_types.index)
axes[1, 0].set_title('Memory Type Breakdown')
axes[1, 0].legend()

# Milestones
axes[1, 1].bar(df['week'], df['milestones'], color='green')
axes[1, 1].set_title('Milestones Achieved per Week')
axes[1, 1].tick_params(axis='x', rotation=45)

plt.suptitle(f'Agent {agent_id} - Weekly Progress Dashboard', fontsize=16)
plt.tight_layout()
plt.show()
```

---

## Example 6: Real-Time Activity Stream

**Use Case**: Live-updating stream of agent activity

**WebSocket Implementation** (FastAPI):
```python
from fastapi import WebSocket
import asyncio
import json

@app.websocket("/ws/agent/{agent_id}/activity")
async def activity_stream(websocket: WebSocket, agent_id: str, session_token: str):
    await websocket.accept()

    last_check = datetime.utcnow()

    while True:
        # Query for new memories since last check
        now = datetime.utcnow()
        url = f"http://localhost:8000/api/v2/agents/{agent_id}/recall/changed-since"
        headers = {"X-Session-Token": session_token}
        response = requests.post(
            url, headers=headers, json={"since": f"{last_check.isoformat()}Z", "limit": 50}
        )
        new_memories = response.json()['memories']

        if new_memories:
            await websocket.send_json({
                'timestamp': now.isoformat(),
                'new_memories': len(new_memories),
                'latest': new_memories[0] if new_memories else None
            })

        last_check = now
        await asyncio.sleep(5)  # Check every 5 seconds
```

**Frontend** (JavaScript):
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/agent/claude_dev/activity?session_token=your_session_token');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    // Add to activity feed
    const feed = document.getElementById('activity-feed');
    const item = document.createElement('div');
    item.className = 'activity-item';
    item.innerHTML = `
        <span class="timestamp">${data.timestamp}</span>
        <span class="badge">${data.new_memories} new memories</span>
        <p>${data.latest?.title || 'No title'}</p>
    `;
    feed.prepend(item);
};
```

---

## Example 7: Temporal Query Comparison

**Use Case**: Compare agent activity between two time periods

```python
def compare_periods(agent_id, session_token, period1_start, period1_end, period2_start, period2_end):
    """Compare two time periods"""

    def get_stats(start, end):
        url = f"http://localhost:8000/api/v2/agents/{agent_id}/recall/changed-since"
        headers = {"X-Session-Token": session_token}
        upper = f"{end.isoformat()}Z"
        raw = requests.post(
            url, headers=headers, json={"since": f"{start.isoformat()}Z", "limit": 100}
        ).json()['memories']
        memories = [m for m in raw if m.get("created_at", "") <= upper]

        return {
            'total': len(memories),
            'types': Counter(m.get('type') for m in memories),
            'avg_confidence': sum(m.get('confidence', 0) for m in memories) / len(memories) if memories else 0
        }

    period1 = get_stats(period1_start, period1_end)
    period2 = get_stats(period2_start, period2_end)

    # Visualization
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # Total comparison
    axes[0].bar(['Period 1', 'Period 2'], [period1['total'], period2['total']])
    axes[0].set_title('Total Memories')

    # Type distribution comparison
    types = set(period1['types'].keys()) | set(period2['types'].keys())
    x = range(len(types))
    axes[1].bar([i-0.2 for i in x], [period1['types'].get(t, 0) for t in types],
                width=0.4, label='Period 1')
    axes[1].bar([i+0.2 for i in x], [period2['types'].get(t, 0) for t in types],
                width=0.4, label='Period 2')
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(types, rotation=45)
    axes[1].set_title('Memory Types')
    axes[1].legend()

    # Confidence comparison
    axes[2].bar(['Period 1', 'Period 2'],
                [period1['avg_confidence'], period2['avg_confidence']])
    axes[2].set_title('Average Confidence')
    axes[2].set_ylim(0, 1)

    plt.tight_layout()
    plt.show()
```

---

## Combining Automatic + Semantic Timeline

### Best Practice Pattern

**1. Use automatic timestamps for filtering:**
```python
# Get all memories from last week
requests.post(
    "http://localhost:8000/api/v2/agents/{agent_id}/recall/changed-since",
    json={"since": seven_days_ago, "limit": 100},
    headers={"X-Session-Token": session_token},
)
```

**2. Use semantic timeline for context:**
```python
# Get milestone events from those memories
milestones = [m for m in memories if 'milestone' in m.get('tags', [])]
```

**3. Visualize both together:**
```python
# Plot all activity (automatic) with milestones highlighted (semantic)
plt.scatter(all_dates, all_counts, alpha=0.3, label='All Activity')
plt.scatter(milestone_dates, milestone_counts, s=200, color='red',
            marker='*', label='Milestones')
```

---

## Tools and Libraries

### Python
- **matplotlib**: Static charts and graphs
- **plotly**: Interactive visualizations
- **pandas**: Data manipulation and time series
- **seaborn**: Statistical visualizations

### JavaScript
- **D3.js**: Custom timeline visualizations
- **Chart.js**: Quick charts
- **Vis.js**: Timeline and network graphs
- **ApexCharts**: Modern interactive charts

### Dashboards
- **Streamlit**: Python-based dashboards
- **Grafana**: Real-time monitoring (requires metrics adapter)
- **Observable**: Collaborative visualizations

---

## API Query Patterns

All examples below are `POST` with a JSON body and require `X-Session-Token` + `Content-Type: application/json` headers.

### Get Timeline Data
```bash
# Last 7 days — temporal endpoint, no semantic search
POST /recall/changed-since
{"since":"<7d-ago ISO>"}

# Specific date range — server gives you `since`; client-side filter for the upper bound
POST /recall/changed-since
{"since":"2025-12-20T00:00:00Z","limit":100}
# then keep only m where m["created_at"] <= "2025-12-27T23:59:59Z"

# This month
POST /recall/changed-since
{"since":"<YYYY-MM-01T00:00:00Z>"}

# Combine with type filter (e.g. events / milestones)
POST /recall/changed-since
{"since":"2025-12-01T00:00:00Z","type":["event"]}
```

> The `/recall` (similarity-search) endpoint does **not** accept `created_after` / `created_before` query params. For temporal listing always go through `/recall/changed-since`, `/recall/as-of`, or `/recall/recent`.

---

## Example Dashboard Output

```
┌─────────────────────────────────────────────────────┐
│  Agent: claude_memanto_dev   Tenant: moorcheh_dev    │
├─────────────────────────────────────────────────────┤
│                                                     │
│  This Week's Activity                               │
│  ┌────────────────────────────────────────┐        │
│  │ Memories Created: 47                   │        │
│  │ Decisions Made: 8                      │        │
│  │ Milestones: 3                          │        │
│  │ Avg Confidence: 0.92                   │        │
│  └────────────────────────────────────────┘        │
│                                                     │
│  Timeline (Dec 20 - Dec 27)                        │
│  ┌────────────────────────────────────────┐        │
│  │    ●           ●      ★         ●      │        │
│  │────┼───────────┼──────┼─────────┼──────│        │
│  │  Dec 20     Dec 22  Dec 24   Dec 27   │        │
│  │                                        │        │
│  │  ★ = Milestone    ● = Session         │        │
│  └────────────────────────────────────────┘        │
│                                                     │
│  Memory Type Breakdown                             │
│  ┌────────────────────────────────────────┐        │
│  │ fact        ████████████████ 45%       │        │
│  │ decision    ██████████ 30%             │        │
│  │ event       ████ 15%                   │        │
│  │ commitment  ██ 10%                     │        │
│  └────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────┘
```

---

## Resources

- **MEMANTO API**: [AGENT_RUNTIME_GUIDE.md](AGENT_RUNTIME_GUIDE.md)
- **Temporal Helpers**: [app/utils/temporal_helpers.py](app/utils/temporal_helpers.py)
- **Best Practices**: [AGENT_MEMORY_BEST_PRACTICES.md](AGENT_MEMORY_BEST_PRACTICES.md)

---

**Status**: Production Examples
**Last Updated**: March 2026
