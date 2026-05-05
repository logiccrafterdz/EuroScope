# Contributing to EuroScope

First off, thank you for considering contributing to EuroScope! It's people like you that make open source such a great community.

## Development Setup

1. Fork the repository and clone it locally.
2. Ensure you have Python 3.11+ installed.
3. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
   ```
4. Install the development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

## Workflow

1. Create a new branch for your feature or bugfix: `git checkout -b feature/your-feature-name`
2. Make your changes and test them thoroughly.
3. Run the test suite: `pytest tests/`
4. Commit your changes using descriptive commit messages.
5. Push to your fork and submit a Pull Request.

## Code Style

- We use `black` for code formatting.
- We use `flake8` for linting.
- We use `isort` for import sorting.
- We use `pytest` for testing.

Before submitting a Pull Request, please ensure all tests pass and your code is formatted correctly.

## Pull Request Process

1. Ensure your PR description clearly describes the problem and solution. Include the relevant issue number if applicable.
2. Update the README.md with details of changes to the interface, if applicable.
3. Your PR will be reviewed by maintainers, who may request changes.
