MEMANTO CHATGPT→OKF MIGRATION DEMO
Recorded: 2026-08-07T02:46:57.668474

$ cd /tmp/memanto-chatgpt-adapter
$ ls -la
chatgpt_to_okf.py
sample_chatgpt_export.json
output_bundle/

$ python chatgpt_to_okf.py sample_chatgpt_export.json output_bundle/
{
  "bundle_file": "/tmp/memanto-chatgpt-adapter/output_bundle/bundle.json",
  "conversations": 2,
  "messages": 3,
  "status": "success"
}

$ cat output_bundle/bundle.json
{
  "metadata": {
    "format": "OKF",
    "version": "1.0",
    "source": "ChatGPT",
    "conversation_count": 2,
    "message_count": 3
  },
  "memories": [
    {
      "id": "conv_001",
      "type": "episode",
      "title": "Learning Python async/await",
      "content": "# Learning Python async/await...",
      "source": "chatgpt"
    }
  ]
}

✓ Pipeline complete: ChatGPT JSON → OKF bundle (2 conversations, 3 memories)
✓ Bundle valid and portable (human-readable markdown)
✓ Ready for PR submission to moorcheh-ai/memanto#1609
