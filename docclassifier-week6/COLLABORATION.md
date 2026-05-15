# Collaboration Guide

---

## Project roles

| Role | Responsibilities |
|---|---|
| **AI Engineer** | Model training (Colab), model card, `app/classifier/`, `golden_expected.json` |
| **Backend Engineer** | API, services, repositories, domain models, workers, infra adapters |
| **DevOps / Platform** | Docker Compose, Dockerfile, CI/CD, Vault config, Alembic migrations |

---

## Branch strategy

```
main          ← production-ready; protected; all PRs require review
dev           ← integration branch; CI required to pass
feature/*     ← short-lived feature branches off dev
fix/*         ← bug-fix branches off dev or main
services-*    ← service-layer work; merges into dev
```

Hotfixes to production go directly from `fix/*` to `main` with a cherry-pick to `dev`.

---

## Commit message format

```
<type>(<scope>): <short description>

[optional body]
[optional footer: refs #issue-number]
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`

Examples:
```
feat(api): add DELETE /users/{id} endpoint
fix(worker): pass batch_id to PredictionCreate constructor
docs(readme): add latency budget verification steps
ci: fix seed_admin entrypoint in smoke test
```

---

## Pull request checklist

Before opening a PR:

- [ ] `uv run ruff check app/ streamlit-dashboard.py` — no lint errors
- [ ] `uv run mypy app/ --ignore-missing-imports` — no type errors
- [ ] `uv run python test_local.py` — all structural tests pass
- [ ] If model weights changed: `uv run python app/classifier/eval/golden.py` passes
- [ ] If a new API endpoint was added: Casbin policy added to `casbin/policy.csv` AND inserted into running DB
- [ ] If a new service method was added: corresponding test in `test_services_integration.py`
- [ ] Description explains the *why*, not just the *what*

---

## Code review guidelines

**Reviewers look for:**

1. **Layer compliance** — No SQLAlchemy in services or API; no HTTP exceptions in repos or services
2. **Transaction ownership** — Mutations wrapped in `async with self.db.begin():`
3. **Cache invalidation** — Every mutation calls the appropriate `cache.delete()` keys
4. **Audit completeness** — State-changing operations write an audit entry inside the same transaction
5. **RBAC coverage** — New endpoints have a Casbin policy and a test that 403s without the right role
6. **No hardcoded secrets** — All sensitive values via Vault or env fallback
7. **Idempotency** — Worker jobs and SFTP ingestion are safe to retry

---

## Local development setup

```powershell
# Clone + install
git clone <repo-url>
cd docclassifier-week6
git lfs pull               # fetch model weights
uv sync --group dev        # install all deps including dev tools

# Run pre-commit checks
uv run ruff check app/ streamlit-dashboard.py
uv run mypy app/ --ignore-missing-imports
uv run python test_local.py

# Start the stack
cp .env.example .env
docker compose up --build -d

# Seed admin
docker compose run --rm --entrypoint python api scripts/seed_admin.py

# Run dashboard locally (talks to the Docker stack)
uv run streamlit run streamlit-dashboard.py
```

---

## Working with the model

Model training happens on Google Colab (free T4 GPU).

1. Open `app/classifier/train.ipynb` on Colab
2. Mount Google Drive or upload the RVL-CDIP dataset
3. Train: linear probe for 20 epochs, then partial unfreezing for 20 epochs
4. Export `classifier.pt` and `model_card.json` to `app/classifier/models/`
5. Commit both files via Git LFS:
   ```powershell
   git lfs track "*.pt"          # already configured in .gitattributes
   git add app/classifier/models/
   git commit -m "feat(model): retrain ConvNeXt-Tiny, test_top1=0.72"
   ```
6. Regenerate the golden set:
   ```powershell
   uv run python app/classifier/eval/regenerate_golden.py
   git add app/classifier/eval/
   git commit -m "test(golden): regenerate after model retrain"
   ```
7. Run `golden.py` to verify before pushing

---

## Adding a new API endpoint — full checklist

1. **Domain** — add any new Pydantic models in `app/domain/`
2. **Repository** — add the data-access method; return domain model; no commit
3. **Service** — add business logic; wrap in `async with db.begin()`; invalidate cache; write audit
4. **Router** — add route; call enforcer; map exceptions to HTTPException
5. **Register** — if new router, include it in `app/api/main.py`
6. **Casbin** — add policy line in `casbin/policy.csv`; insert into running DB:
   ```sql
   INSERT INTO casbin_rule (ptype, v0, v1, v2) VALUES ('p', 'admin', '/new', 'POST');
   ```
7. **Restart** — `docker compose restart api` to reload Casbin enforcer
8. **Test** — add integration test; verify 403 for roles that should be denied
9. **Docs** — update README role-permission matrix
