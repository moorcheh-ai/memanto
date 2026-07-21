import re
import os
import tempfile
import html
import yaml

def load_okf_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    entries = []
    # Split by the entry delimiter
    parts = content.split('<!-- okf-entry -->')
    
    for part in parts:
        # FIX: Reassign the stripped string back to part so startswith works
        part = part.strip()
        if not part:
            continue
            
        # Extract YAML front matter and body using regex to be safe
        match = re.match(r'^---\n(.*?)\n---\n(.*)$', part, re.DOTALL)
        if not match:
            continue
            
        yaml_str = match.group(1)
        body = match.group(2).strip('\n')
        
        front_matter = yaml.safe_load(yaml_str)
        if not front_matter:
            front_matter = {}
            
        # FIX: Read x_memanto as a dict to check the flag
        x_meta = front_matter.get('x_memanto', {})
        is_escaped = isinstance(x_meta, dict) and x_meta.get('escaped') is True
        
        if is_escaped:
            body = html.unescape(body)
            # FIX: Update unescape loop to also process strings nested in lists
            for k, v in front_matter.items():
                if k == 'x_memanto':
                    continue
                if isinstance(v, str):
                    front_matter[k] = html.unescape(v)
                elif isinstance(v, list):
                    front_matter[k] = [html.unescape(item) if isinstance(item, str) else item for item in v]
        
        entries.append({
            'front_matter': front_matter,
            'body': body
        })
    return entries

def save_okf_file(file_path, records):
    with open(file_path, 'w', encoding='utf-8') as file:
        for i, record in enumerate(records):
            front_matter = record['front_matter'].copy()
            body = record['body']
            
            # FIX: Safely update the x_memanto dict without destroying existing keys
            x_meta = front_matter.setdefault('x_memanto', {})
            
            # Check if we need to escape the body or front matter (including lists)
            needs_escape = '<!-- okf-entry -->' in body
            if not needs_escape:
                for v in front_matter.values():
                    if isinstance(v, str) and '<!-- okf-entry -->' in v:
                        needs_escape = True
                        break
                    elif isinstance(v, list):
                        for item in v:
                            if isinstance(item, str) and '<!-- okf-entry -->' in item:
                                needs_escape = True
                                break
                        if needs_escape:
                            break
            
            if needs_escape:
                x_meta['escaped'] = True
                body = html.escape(body)
                # FIX: Apply html.escape to list elements as well
                for k, v in front_matter.items():
                    if k == 'x_memanto':
                        continue
                    if isinstance(v, str):
                        front_matter[k] = html.escape(v)
                    elif isinstance(v, list):
                        front_matter[k] = [html.escape(item) if isinstance(item, str) else item for item in v]
            
            # Write front matter using yaml.safe_dump to handle lists properly
            file.write('---\n')
            yaml.safe_dump(front_matter, file, default_flow_style=False, sort_keys=False, allow_unicode=True)
            file.write('---\n')
            file.write(body + '\n')
            if i < len(records) - 1:
                file.write('<!-- okf-entry -->\n')

if __name__ == "__main__":
    # FIX: Test delimiter escaping in tags and title
    test_records = [{
        'front_matter': {'title': 'Test <!-- okf-entry --> Entry', 'tags': ['python', 'yaml <!-- okf-entry -->']},
        'body': 'This is a test body.\n<!-- okf-entry -->\nMore body.'
    }]
    
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = os.path.join(temp_dir, 'test_okf.txt')
        save_okf_file(file_path, test_records)
        loaded = load_okf_file(file_path)
        
        assert loaded[0]['body'] == test_records[0]['body']
        assert loaded[0]['front_matter']['title'] == test_records[0]['front_matter']['title']
        assert loaded[0]['front_matter']['tags'] == test_records[0]['front_matter']['tags']
        print("OKF Round Trip Test Passed with Delimiters in Title and Tags!")
