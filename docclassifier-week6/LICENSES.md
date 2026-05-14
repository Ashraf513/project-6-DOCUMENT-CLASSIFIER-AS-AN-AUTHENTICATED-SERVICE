# Licenses

## Dataset: RVL-CDIP

**License:** Research / Non-Commercial Use Only

The RVL-CDIP dataset (Ryerson Vision Lab Complex Document Information Processing) is used
for training and evaluation of the classifier model.

- 400,000 grayscale document images across 16 classes
- Source: http://adamharley.com/rvl-cdip/
- Original IIT-CDIP collection: The IIT Complex Document Information Processing Test Collection

**Restrictions:**
- May not be used for commercial purposes.
- May not be redistributed.
- The trained model weights (`classifier.pt`) derived from this dataset inherit the same
  non-commercial restriction. Do not deploy this service commercially without obtaining
  an appropriate dataset license or retraining on a commercially-licensed dataset.

---

## Python Dependencies

Key dependencies and their licenses:

| Package | License | Notes |
|---------|---------|-------|
| FastAPI | MIT | Web framework |
| SQLAlchemy | MIT | ORM and async DB |
| Alembic | MIT | DB migrations |
| Pydantic v2 | MIT | Data validation |
| fastapi-users | MIT | Auth management |
| PyCasbin | Apache 2.0 | RBAC policy enforcement |
| casbin-sqlalchemy-adapter | Apache 2.0 | Casbin DB adapter |
| hvac | Apache 2.0 | HashiCorp Vault client |
| redis-py | MIT | Redis client |
| fastapi-cache2 | MIT | Redis-backed response cache |
| asyncpg | Apache 2.0 | Async PostgreSQL driver |
| psycopg2-binary | LGPL v3 | Sync PostgreSQL driver (Casbin adapter) |
| pwdlib | MIT | Argon2id password hashing |
| python-jose | MIT | JWT encoding/decoding |
| uvicorn | BSD 3-Clause | ASGI server |
| PyTorch | BSD 3-Clause | Deep learning framework |
| torchvision | BSD 3-Clause | ConvNeXt pretrained models |
| uv | MIT | Package manager |

---

## Docker Base Images

| Image | License |
|-------|---------|
| python:3.11-slim-bookworm | PSF License (Python) + Debian licenses |
| postgres:16-alpine | PostgreSQL License (similar to MIT) |
| redis:7-alpine | BSD 3-Clause |
| minio/minio | GNU AGPL v3 |
| minio/mc | GNU AGPL v3 |
| hashicorp/vault | BSL 1.1 (Business Source License) |
| atmoz/sftp | MIT |
| ghcr.io/astral-sh/uv | MIT |

**Note on HashiCorp Vault (BSL 1.1):**
The Business Source License allows free use for non-production and internal purposes.
For production commercial use, check HashiCorp's current terms or consider OpenBao
(the MIT-licensed community fork).

**Note on MinIO (AGPL v3):**
AGPL requires that if you modify MinIO and provide it as a network service, you must
release your modifications. Using unmodified MinIO as a service component (as done here)
does not trigger the copyleft requirement for the application code.

---

## This Project's Code

The application code in this repository (`app/`, `alembic/`, `casbin/`, `scripts/`) is
academic work produced for an AI Engineering course. No separate open-source license is
applied — check with your institution's IP policy before open-sourcing.
