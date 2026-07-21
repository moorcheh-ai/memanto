import re
import os
import copy
import tempfile
import html
import yaml

def load_okf_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    entries = []
    parts = content.split('<!-- okf-entry -->')
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
            
        match = re.match(r'^---\n(.*?)\n---\n(.*)$', part, re.DOTALL)
        if not match:
            continue
            
        yaml_str = match.group(1)
        body = match.group(2).strip('\n')
        
        front_matter = yaml.safe_load(yaml_str)
        if not front_matter:
            front_matter = {}
            
        x_meta = front_matter.get('x_memanto', {})
        # FIX: unconditionally pop the escaped flag from memory after loading
        is_escaped = isinstance(x_meta, dict) and x_meta.pop('escaped', False) is True
        
        if is_escaped:
            body = html.unescape(body)
            for k, v in front_matter.items():
                if k == 'x_memanto':
                    continue
                if isinstance(v, str):
                    front_matter[k] = html.unescape(v)
                elif isinstance(v, list):
                    front_matter[k] = [html.unescape(item) if isinstance(item, str) else item for item in v]
        
        # Clean up empty x_memanto dict
        if isinstance(x_meta, dict) and not x_meta:
            front_matter.pop('x_memanto', None)
                
        entries.append({
            'front_matter': front_matter,
            'body': body
        })
    return entries

def save_okf_file(file_path, records):
    with open(file_path, 'w', encoding='utf-8') as file:
        for i, record in enumerate(records):
            # FIX: Deep copy front matter to prevent mutating the caller's data
            front_matter = copy.deepcopy(record['front_matter'])
            body = record['body']
            
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
                x_meta = front_matter.setdefault('x_memanto', {})
                x_meta['escaped'] = True
                body = html.escape(body)
                for k, v in front_matter.items():
                    if k == 'x_memanto':
                        continue
                    if isinstance(v, str):
                        front_matter[k] = html.escape(v)
                    elif isinstance(v, list):
                        front_matter[k] = [html.escape(item) if isinstance(item, str) else item for item in v]
            else:
                # FIX: pop the escaped flag if it exists but is no longer needed
                x_meta = front_matter.get('x_memanto', {})
                if isinstance(x_meta, dict) and 'escaped' in x_meta:
                    del x_meta['escaped']
                    if not x_meta:
                        del front_matter['x_memanto']
            
            file.write('---\n')
            yaml.safe_dump(front_matter, file, default_flow_style=False, sort_keys=False, allow_unicode=True)
            file.write('---\n')
            file.write(body + '\n')
            if i < len(records) - 1:
                file.write('<!-- okf-entry -->\n')

if __name__ == "__main__":
    # FIX: Added resources and pre-existing HTML entities to test coverage
    test_records = [{
        'front_matter': {
            'title': 'Test <!-- okf-entry --> Entry',
            'tags': ['python', 'yaml <!-- okf-entry -->'],
            'resources': ['http://example.com/res <!-- okf-entry -->'],
            'pre_existing': 'This &amp; that'
        },
        'body': 'This is a test body. &amp; \n<!-- okf-entry -->\nMore body.'
    }]
    
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = os.path.join(temp_dir, 'test_okf.txt')
        save_okf_file(file_path, test_records)
        loaded = load_okf_file(file_path)
        
        assert loaded[0]['body'] == test_records[0]['body']
        assert loaded[0]['front_matter']['title'] == test_records[0]['front_matter']['title']
        assert loaded[0]['front_matter']['tags'] == test_records[0]['front_matter']['tags']
        assert loaded[0]['front_matter']['resources'] == test_records[0]['front_matter']['resources']
        assert loaded[0]['front_matter']['pre_existing'] == test_records[0]['front_matter']['pre_existing']
        print("OKF Round Trip Test Passed with Resources, Entities, and Delimiters!")
