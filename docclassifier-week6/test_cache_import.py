import sys
print("Python path:", sys.path)
print()

from app.infra.cache import (
    InMemoryCacheInvalidator,
    USERS_LIST_KEY,
    BATCHES_LIST_KEY,
    PREDICTIONS_RECENT_KEY,
    batch_key,
    predictions_batch_key,
    user_me_key,
)
print("All imports successful!")
print("USERS_LIST_KEY:", USERS_LIST_KEY)
print("batch_key('123'):", batch_key("123"))