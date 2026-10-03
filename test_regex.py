import re

pattern = re.compile(
    r"(['\"]?)\b(api[_-]?key|session[_-]?token|access[_-]?token|refresh[_-]?token|"
    r"password|secret)\b\1(\s*[:=]\s*)(['\"]?)(.*?)\4(?=[\s,}]|\Z)",
    re.IGNORECASE,
)
text1 = '{"password": "server-secret"}'
text2 = 'password: "server-secret"'
text3 = "secret=mysecret"
print("Result1:", pattern.sub(r"\1\2\1\3\4[REDACTED]\4", text1))
print("Result2:", pattern.sub(r"\1\2\1\3\4[REDACTED]\4", text2))
print("Result3:", pattern.sub(r"\1\2\1\3\4[REDACTED]\4", text3))
