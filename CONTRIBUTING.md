# Contributing

Follow [PEP 8](https://peps.python.org/pep-0008/) for Python naming,
import grouping, spacing, comments and docstrings. Prefer readable names
and short functions over clever abstractions.

Use **KISS**, **DRY**, **YAGNI**, separation of concerns, and avoid premature
optimization. Every change affecting API side effects should have an offline
regression test.

Run locally:

```bash
python -m unittest discover -s tests -v
python -m compileall -q test_generation tests
npx playwright test
```

Do not commit API credentials, generated test artifacts, production data or
secrets. Keep the README and GitHub Actions workflow commands synchronized.
