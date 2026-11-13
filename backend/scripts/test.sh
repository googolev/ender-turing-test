#!/usr/bin/env bash

set -e
set -x

# Tests delete all users and items, so they run against a separate *_test database.
# xtrace is paused so the URL with the password stays out of the log.
{ set +x; } 2>/dev/null
DATABASE_URL="$(python -m tests.prepare_db)"
export DATABASE_URL
set -x

FASTAPI_ENV=development coverage run -m pytest tests/
coverage report
coverage html --title "${@-coverage}"
