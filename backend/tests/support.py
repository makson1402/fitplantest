"""Helpers shared by tests."""

# `Settings(_env_file=None)` still reads process environment variables. CI (and developers who export them) set
# POSTGRES_*/MONGO_*; tests that build an app must not pick those stores up unless they ask for them explicitly.
NO_STORES = {
    "database_url": None, "postgres_user": None, "postgres_password": None, "postgres_db": None,
    "mongo_url": None, "mongo_initdb_root_username": None, "mongo_initdb_root_password": None,
}
