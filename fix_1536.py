import os
import json
import stat

def create_session_directory(agent):
    session_dir = os.path.join(os.path.expanduser('~/.memanto/sessions'))
    if not os.path.exists(session_dir):
        os.makedirs(session_dir, mode=0o700)
    return session_dir

def create_session_file(agent, session_token):
    session_dir = create_session_directory(agent)
    session_file = os.path.join(session_dir, f'{agent}.json')
    with open(session_file, 'w', mode=0o600) as f:
        json.dump({'session_token': session_token}, f)
    return session_file

def update_session_file(agent, session_token):
    session_dir = create_session_directory(agent)
    session_file = os.path.join(session_dir, f'{agent}.json')
    temp_file = os.path.join(session_dir, f'{agent}.tmp')
    with open(temp_file, 'w', mode=0o600) as f:
        json.dump({'session_token': session_token}, f)
    os.replace(temp_file, session_file)

def load_session(agent):
    session_dir = create_session_directory(agent)
    session_file = os.path.join(session_dir, f'{agent}.json')
    if os.path.exists(session_file):
        with open(session_file, 'r') as f:
            return json.load(f)
    return None

def main():
    agent = 'test_agent'
    session_token = 'test_session_token'
    create_session_file(agent, session_token)
    print(load_session(agent))
    update_session_file(agent, 'new_session_token')
    print(load_session(agent))

if __name__ == '__main__':
    main()