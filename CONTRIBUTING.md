# Contributing to saas-support

Thanks for your interest! Here's how to get started.

---

## 🍴 Fork & Run Locally

1. Fork the repo and clone your fork:
   ```bash
   git clone https://github.com/mazetezr/saas-support.git
   cd saas-support
   ```

2. Copy the example env file and fill in your values:
   ```bash
   cp .env.example .env
   ```

3. Start the stack with Docker Compose:
   ```bash
   docker compose up --build
   ```

4. Run database migrations:
   ```bash
   docker compose exec bot alembic upgrade head
   ```

---

## 🔀 Submitting a PR

1. Create a branch from `master`:
   ```bash
   git checkout -b feat/your-feature
   ```

2. Make your changes, commit with a clear message, and push:
   ```bash
   git commit -m "feat: describe what you did"
   git push origin feat/your-feature
   ```

3. Open a Pull Request against `master` and describe what you changed and why.

---

## 🐛 Reporting Bugs

Open a [GitHub Issue](https://github.com/mazetezr/saas-support/issues) with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Relevant logs or screenshots

---

## 🎨 Code Style

- **Python 3.13**, follow [PEP 8](https://peps.python.org/pep-0008/)
- Use `async/await` consistently (this is a fully async codebase)
- Keep functions focused and small
- No unused imports

A quick check before committing:
```bash
pip install flake8
flake8 bot/
```
