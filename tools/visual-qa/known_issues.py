"""Known fit issues, read from tools/known-issues.yaml: id -> the pieces it names. An issue is open while it is listed.
Reads only the `- id:` and `pieces: [...]` lines, the shape site/known-issues.ts checks, so no YAML library is needed."""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FILE = 'tools/known-issues.yaml'


def known_issues():
    issues, current = {}, None
    for line in open(os.path.join(ROOT, FILE), encoding='utf8'):
        m = re.match(r'- id: (\S+)', line)
        if m:
            current = m.group(1)
            issues[current] = set()
        m = re.match(r'\s+pieces: \[(.*)\]', line)
        if m and current:
            issues[current] = set(re.findall(r'\d{3}', m.group(1)))
    return issues
