# Licenses

---

## Training Dataset — RVL-CDIP

The model was trained on the **RVL-CDIP** (Ryerson Vision Lab Complex Document
Information Processing) dataset.

- **Source:** A. W. Harley, A. Ufkes, K. G. Derpanis, "Evaluation of Deep Convolutional Nets for Document Image Classification and Retrieval," in ICDAR, 2015.
- **License:** The dataset is provided for **academic research use only**. Commercial use requires permission from the original authors/institutions.
- **Size:** 400,000 grayscale images across 16 document classes (25,000 per class).
- **Split:** 320,000 train / 40,000 validation / 40,000 test.

This service uses a subset of RVL-CDIP for training and evaluation only. The dataset images are **not** distributed with this repository.

---

## Model weights — `app/classifier/models/classifier.pt`

- Derived from a ConvNeXt-Tiny backbone pretrained on ImageNet-1K (IMAGENET1K_V1).
- Fine-tuned on RVL-CDIP.
- Subject to the **PyTorch / torchvision model weights license** (BSD-style). See: https://github.com/pytorch/vision/blob/main/LICENSE

---

## Key dependency licenses

| Package | License | Notes |
|---|---|---|
| FastAPI | MIT | Web framework |
| SQLAlchemy | MIT | ORM |
| Pydantic | MIT | Data validation |
| fastapi-users | MIT | Auth + user management |
| Casbin | Apache 2.0 | RBAC |
| Redis (client) | MIT | Cache + queue |
| RQ | BSD | Job queue |
| MinIO (client) | Apache 2.0 | Blob storage |
| Paramiko | LGPL 2.1 | SFTP |
| hvac | Apache 2.0 | Vault client |
| PyTorch | BSD | ML framework |
| torchvision | BSD | Vision models |
| Pillow | MIT-CMU | Image processing |
| pwdlib | MIT | Password hashing |
| python-jose | MIT | JWT |
| Streamlit | Apache 2.0 | Dashboard UI |
| alembic | MIT | DB migrations |
| asyncpg | Apache 2.0 | Async Postgres driver |
| httpx | BSD | HTTP client |
| uvicorn | BSD | ASGI server |

---

## Infrastructure image licenses

| Image | License |
|---|---|
| postgres:16-alpine | PostgreSQL License |
| redis:7-alpine | BSD |
| minio/minio | GNU AGPL v3 (self-hosted use) |
| atmoz/sftp | MIT |
| hashicorp/vault | BSL 1.1 (free for non-production use; production requires Vault Enterprise or alternative) |
| dpage/pgadmin4 | PostgreSQL License |

> **Note on Vault licensing:** HashiCorp changed Vault's license to BSL 1.1 in 2023.
> For production deployments, evaluate OpenBao (open-source Vault fork, MPL 2.0) or
> Vault Enterprise. The dev-mode Vault used here is for development and demonstration only.

---

## This codebase

Copyright © 2026 — released under the **MIT License** unless otherwise stated.

```
MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
```
