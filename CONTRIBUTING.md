# Contributing

1. Create a branch for the change.
2. Keep examples synthetic; never use real operational documents or identifiers.
3. Add unit tests for every new label alias or parsing behavior.
4. Run `python -m unittest discover -s tests -v`.
5. Run `python scripts/check_release.py`.
6. Review `git status` and `git diff --cached` before committing.

Changes should preserve local-only processing and avoid adding network integrations unless the project's scope is deliberately changed and clearly documented.
