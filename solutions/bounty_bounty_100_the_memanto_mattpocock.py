import requests
import re
import base64

def get_github_repo_readme(owner, repo):
    """Fetch the README content of a GitHub repository."""
    url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    headers = {"Accept": "application/vnd.github.v3+json"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    # Content is base64‑encoded; decode to UTF‑8 text
    content = base64.b64decode(data["content"]).decode("utf-8")
    return content

def extract_skills(readme_text):
    """Extract skill items from README.
    Assumes skills are listed as bullet points starting with '- ' or '* '.
    """
    # Match lines that begin with optional whitespace, a dash or asterisk, then space
    skill_pattern = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)
    skills = skill_pattern.findall(readme_text)
    # Strip surrounding whitespace and discard empty strings
    return [s.strip() for s in skills if s.strip()]

def main():
    owner = "mattpocock"
    repo = "skills"
    try:
        readme = get_github_repo_readme(owner, repo)
        skills = extract_skills(readme)
        if skills:
            print(f"Skills found in {owner}/{repo}:")
            for i, skill in enumerate(skills, 1):
                print(f"{i}. {skill}")
        else:
            print("No skills detected in the README.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()