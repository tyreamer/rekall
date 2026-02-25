# Contributing to Rekall

We love your input! We want to make contributing to this project as easy and transparent as possible, whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features
- Becoming a maintainer

## We Develop with Github
We use github to host code, to track issues and feature requests, as well as accept pull requests.

## Report bugs using Github's [issues](https://github.com/your-org/rekall/issues)
We use GitHub issues to track public bugs. Report a bug by opening a new issue; it's that easy!

## Write bug reports with detail, background, and sample data
**Great Bug Reports** tend to have:

- A quick summary and/or background
- Steps to reproduce
  - Be specific!
  - Give sample `snapshot.json` snippets or `project-state` file structures.
- What you expected would happen
- What actually happens

## Modifying Rekall
1. Fork the repo and create your branch from `master`.
2. Make sure you've installed testing dependencies: `pip install -r requirements-dev.txt` (or generic `pip install pytest`).
3. Ensure the test suite passes: `pytest tests/`.
4. Any new CLI features must add tests to `tests/test_cli.py`.
5. Issue that pull request!

## License
By contributing, you agree that your contributions will be licensed under its MIT License.
