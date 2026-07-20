import html
from memanto.okf.constants import ENTRY_DELIMITER, X_MEMANTO_ENCODING_FIELD

def export_to_okf(memory, file_path):
    """
    Export a memory to OKF format with HTML-escaping for literal entry delimiters.

    Args:
        memory: The memory to export
        file_path: Path to save the exported file
    """
    # HTML-escape affected strings
    escaped_body = html.escape(memory.body) if ENTRY_DELIMITER in memory.body else memory.body
    escaped_title = html.escape(memory.title) if ENTRY_DELIMITER in memory.title else memory.title
    escaped_tags = [html.escape(tag) if ENTRY_DELIMITER in tag else tag for tag in memory.tags]

    # Add encoding metadata
    encoding_metadata = {X_MEMANTO_ENCODING_FIELD: 'html'} if ENTRY_DELIMITER in memory.body or ENTRY_DELIMITER in memory.title or any(ENTRY_DELIMITER in tag for tag in memory.tags) else {}

    # Build frontmatter
    frontmatter = {
        'title': escaped_title,
        'tags': escaped_tags,
        'resource': memory.resource,
        'x_memanto': {**memory.x_memanto, **encoding_metadata}
    }

    # Write to file
    with open(file_path, 'w') as f:
        f.write(f'---\n{yaml.dump(frontmatter)}---\n{escaped_body}')