import html
import yaml

def load_okf_file(file_path):
    with open(file_path, 'r') as file:
        content = file.read()
        records = content.split('<!-- okf-entry -->')
        loaded_records = []
        for record in records:
            if record.strip():
                loaded_record = {}
                lines = record.splitlines()
                front_matter = {}
                body = []
                in_body = False
                for line in lines:
                    if line.strip() == '---':
                        in_body = True
                    elif in_body:
                        body.append(line)
                    else:
                        key, value = line.split(': ', 1)
                        front_matter[key] = html.unescape(value)
                loaded_record['front_matter'] = front_matter
                loaded_record['body'] = '\n'.join(body)
                loaded_records.append(loaded_record)
        return loaded_records

def save_okf_file(file_path, records):
    with open(file_path, 'w') as file:
        for i, record in enumerate(records):
            file.write('---\n')
            for key, value in record['front_matter'].items():
                file.write(f'{key}: {html.escape(value)}\n')
            file.write('---\n')
            file.write(record['body'] + '\n')
            if i < len(records) - 1:
                file.write('<!-- okf-entry -->\n')

def test_okf_round_trip():
    records = [
        {
            'front_matter': {
                'title': 'Test Title',
                'tags': ['tag1', 'tag2']
            },
            'body': 'This is a test body with <!-- okf-entry --> embedded.'
        },
        {
            'front_matter': {
                'title': 'Test Title 2',
                'tags': ['tag3', 'tag4']
            },
            'body': 'This is another test body.'
        }
    ]
    save_okf_file('test.okf', records)
    loaded_records = load_okf_file('test.okf')
    assert len(loaded_records) == len(records)
    for i in range(len(records)):
        assert loaded_records[i]['front_matter'] == records[i]['front_matter']
        assert loaded_records[i]['body'] == records[i]['body']

test_okf_round_trip()