import yaml
import html

def load_okf_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    entries = []
    # Split by the entry delimiter
    parts = content.split('<!-- okf-entry -->')
    
    for part in parts:
        if not part.strip():
            continue
            
        # Extract YAML front matter and body
        if part.startswith('---'):
            parts_split = part.split('---', 2)
            if len(parts_split) >= 3:
                front_matter = yaml.safe_load(parts_split[1])
                body = parts_split[2].strip('\n')
                
                # Check if body was escaped
                is_escaped = front_matter.get('x_memanto') == 'escaped'
                if is_escaped:
                    body = html.unescape(body)
                    # Unescape string front matter values if they were escaped
                    for k, v in front_matter.items():
                        if isinstance(v, str) and k != 'x_memanto':
                            front_matter[k] = html.unescape(v)
                
                entries.append({
                    'front_matter': front_matter,
                    'body': body
                })
    return entries

def save_okf_file(file_path, records):
    with open(file_path, 'w', encoding='utf-8') as file:
        for record in records:
            front_matter = record['front_matter'].copy()
            body = record['body']
            
            # Check if we need to escape the body or front matter
            needs_escape = '<!-- okf-entry -->' in body
            if not needs_escape:
                for v in front_matter.values():
                    if isinstance(v, str) and '<!-- okf-entry -->' in v:
                        needs_escape = True
                        break
            
            if needs_escape:
                front_matter['x_memanto'] = 'escaped'
                body = html.escape(body)
                for k, v in front_matter.items():
                    if isinstance(v, str) and k != 'x_memanto':
                        front_matter[k] = html.escape(v)
            
            # Write front matter using yaml.dump to handle lists properly
            file.write('---\n')
            yaml.dump(front_matter, file, default_flow_style=False, sort_keys=False, allow_unicode=True)
            file.write('---\n')
            file.write(body + '\n')
            file.write('<!-- okf-entry -->\n')

if __name__ == "__main__":
    # Test round trip
    test_records = [{
        'front_matter': {'title': 'Test Entry', 'tags': ['python', 'yaml']},
        'body': 'This is a test body.\n<!-- okf-entry -->\nMore body.'
    }]
    
    save_okf_file('test_okf.txt', test_records)
    loaded = load_okf_file('test_okf.txt')
    
    assert loaded[0]['body'] == test_records[0]['body']
    assert loaded[0]['front_matter']['title'] == test_records[0]['front_matter']['title']
    assert loaded[0]['front_matter']['tags'] == test_records[0]['front_matter']['tags']
    print("OKF Round Trip Test Passed!")
