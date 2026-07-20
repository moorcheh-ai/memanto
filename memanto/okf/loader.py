import html
from memanto.okf.constants import ENTRY_DELIMITER, X_MEMANTO_ENCODING_FIELD

def load_from_okf(file_path):
    """
    Load a memory from OKF format with HTML-unescaping for affected strings.

    Args:
        file_path: Path to the OKF file to load

    Returns:
        The loaded memory
    """
    with open(file_path, 'r') as f:
        content = f.read()

    # Split records
    records = content.split(ENTRY_DELIMITER)

    memories = []
    for record in records:
        if not record.strip():
            continue

        # Parse frontmatter and body
        frontmatter, body = parse_frontmatter(record)

        # HTML-unescape if encoded
        if frontmatter.get('x_memanto', {}).get(X_MEMANTO_ENCODING_FIELD) == 'html':
            body = html.unescape(body)
            frontmatter['title'] = html.unescape(frontmatter.get('title', ''))
            frontmatter['tags'] = [html.unescape(tag) for tag in frontmatter.get('tags', [])]

        # Create memory
        memory = Memory(
            body=body,
            title=frontmatter.get('title', ''),
            tags=frontmatter.get('tags', []),
            resource=frontmatter.get('resource', ''),
            x_memanto=frontmatter.get('x_memanto', {})
        )
        memories.append(memory)

    return memories