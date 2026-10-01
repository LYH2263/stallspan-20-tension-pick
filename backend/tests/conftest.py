import os

# app.database builds the production engine at import time; tests override the
# get_db dependency, so the module engine is never actually connected. Point it
# at sqlite solely so psycopg2 is not required in the test environment.
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_unused.db")
os.environ.setdefault("SEED_ON_EMPTY", "false")
