import json
import os
import sys

def convert_chatgpt_to_okf(input_file, output_dir):
    """
    Converts a ChatGPT exported conversations.json into OKF (Open Knowledge Format) markdown bundle.
    """
    if not os.path.exists(input_file):
        print(f"Error: Input file '{input_file}' not found.")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    for conv in data:
        title = conv.get("title", "Untitled Conversation")
        mapping = conv.get("mapping", {})
        
        messages = []
        for node_id, node in mapping.items():
            msg = node.get("message")
            if msg and msg.get("content") and msg["content"].get("parts"):
                role = msg.get("author", {}).get("role", "unknown")
                parts = msg["content"]["parts"]
                text = "".join([p for p in parts if isinstance(p, str)])
                if text.strip():
                    messages.append(f"*{role.upper()}*: {text.strip()}")

        if not messages:
            continue

        count += 1
        filename = f"memory_chatgpt_{count}.md"
        filepath = os.path.join(output_dir, filename)

        okf_content = f"""---
title: "{title}"
source: "ChatGPT Export"
type: "conversation"
---

# {title}

{"\n\n".join(messages)}
"""
        with open(filepath, "w", encoding="utf-8") as out:
            out.write(okf_content)

    print(f"Successfully converted {count} conversations into OKF markdown files in '{output_dir}'.")
    print(f"\nNext step to import into Memanto:")
    print(f"  memanto migrate okf {output_dir}")

if __name__ == "__main__":
    input_path = sys.argv[1] if len(sys.argv) > 1 else "sample_chatgpt_export.json"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "./okf_bundle"
    convert_chatgpt_to_okf(input_path, output_path)