# Getting your data out

Neither OpenAI nor Anthropic offers an API for your personal conversation
history. The account data export is the only supported route for both, which is
precisely the lock-in this example exists to demonstrate.

Both work the same way: request an archive, they build it server side, then they
email a download link. Keep the `.zip` as it is; the adapter reads the
conversation files straight out of the archive.

The canonical field mapping for both sources lives in the
[README](README.md#mapping-table). What follows is the source-specific part:
where to click, what the archive contains, and what each export quietly leaves out.

---

## ChatGPT

### Getting your export

1. Sign in at [chatgpt.com](https://chatgpt.com).
2. Click your profile icon, then **Settings**.
3. Open **Data controls**, then **Export data**, and confirm.
4. OpenAI emails a download link. Expect anywhere from minutes to a day.
5. Keep the `.zip`. The adapter reads the conversation files from inside it.

### What the archive contains

A small export holds a single `conversations.json`. Past roughly a hundred
conversations OpenAI shards it instead, 100 per file, and drops the unsharded
name entirely:

```
conversations-000.json      conversations 1 to 100
conversations-001.json      conversations 101 to 200
...                         one file per additional 100
shared_conversations.json   id and title stubs for shared links, NOT history
chat.html                   a rendered copy, not machine readable
file-*.dat                  attachments and generated images
```

The adapter reads every `conversations-NNN.json` in order, plus a plain
`conversations.json` if that is what your archive has.

`shared_conversations.json` is the trap worth knowing about. Its name ends with
the same text, but it holds only id and title stubs with no `mapping`, so a
reader that matches on the suffix picks it up and reports a handful of empty
conversations instead of your whole history. Matching is on the exact file name
for that reason.

### Saved memories are a separate job

The export does **not** reliably contain the list under
**Settings, Personalization, Manage memories**. There is no API for it either.

Two routes, and `--inspect` tells you which applies to your archive:

```bash
python liberate.py --inspect --chatgpt ~/Downloads/chatgpt-export.zip
```

If `bio writes` or `memory snapshots` come back above zero, ChatGPT recorded
those memory events inside your conversations and they are recoverable. If both
are zero, copy the list by hand into a text file and pass `--saved`.

Custom instructions appear as `user_editable_context` nodes, repeated in every
single conversation. The reader skips them deliberately, because importing them
once per conversation would create hundreds of duplicates. Use `--saved` if you
want them.

### Shape of the data

ChatGPT stores a conversation as a node graph, not a list, because editing a
message branches the thread. The live thread is the parent chain hanging off
`current_node`.

```json
{
  "conversation_id": "...",
  "title": "...",
  "create_time": 1750000000.0,
  "current_node": "node-c",
  "mapping": {
    "node-c": { "parent": "node-b", "message": { "author": {"role": "user"},
                "content": {"content_type": "text", "parts": ["..."]} } }
  }
}
```

The reader walks that chain upward and reverses it, so messages come out in the
order they were written. The walk is cycle guarded: a malformed export can point
two nodes at each other, and an unguarded walk would hang.

### Commands

```bash
python liberate.py --inspect --chatgpt ~/Downloads/chatgpt-export.zip

python liberate.py --agent my-agent --chatgpt ~/Downloads/chatgpt-export.zip \
  --saved my_memories.txt --limit 25 --out okf_bundle

bash run.sh my-agent ~/Downloads/chatgpt-export.zip
```

Start with `--limit 25`. Each conversation costs one extraction call, and a real
archive can hold hundreds.

---

## Claude

### Getting your export

1. Sign in at [claude.ai](https://claude.ai).
2. Click your initials in the lower left, then **Settings**.
3. Open **Privacy**, then **Export data**.
4. Anthropic emails a download link. It can take minutes to a day, and the link
   expires, so download promptly.
5. Keep the `.zip` as it is. The adapter reads straight out of the archive.

Available on Free, Pro and Max individual accounts. A Team or Enterprise export
has to be requested by the organisation's primary owner.

Your Pro subscription is sufficient. No API access is involved at any point.

### What the archive contains

```
users.json            account record
login_history.json    not used
conversations.json    every conversation, this is the only file we read
```

### Commands

```bash
# Look before you migrate. Free, read only, no API call.
python liberate.py --inspect --claude ~/Downloads/claude-export.zip

# Migrate
python liberate.py --agent my-agent --claude ~/Downloads/claude-export.zip \
  --exclude-file .private-patterns --out okf_bundle

# Or the whole pipeline in one command
CLAUDE=~/Downloads/claude-export.zip bash run.sh my-agent
```

### Shape of the data

```json
[
  {
    "uuid": "conversation id",
    "name": "conversation title",
    "created_at": "2026-08-06T07:34:53Z",
    "chat_messages": [
      { "uuid": "...", "sender": "human", "text": "...", "created_at": "..." },
      { "uuid": "...", "sender": "assistant",
        "content": [ { "type": "text", "text": "..." } ] }
    ]
  }
]
```

Older exports carry the message body on `text`. Newer ones leave `text` empty
and split the body into typed `content` blocks. The reader handles both, taking
`text` first and falling back to joining the text blocks.

### Worth knowing

**Claude Code sessions are not in this export.** claude.ai exports cover the web
and desktop app only. If most of your Claude use is Claude Code, expect a small
archive.

**Memory summaries are separate.** If you use Claude's memory feature, copy that
text into a file and pass it with `--saved`.
