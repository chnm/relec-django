FROM ghcr.io/astral-sh/uv:0.12.18@sha256:3adc3706091ce7c2fe595e669628caedd6d951551b92b258b7e7dbe06d9440bc AS uv

# Tailwind scans templates across the whole project (theme/static_src/tailwind.config.js).
FROM node:22.23.2-trixie-slim@sha256:7b8a0c89c54499bee567618f96578e1a12a800f062fbdbfd1fb6a443fa6f6284 AS assets
WORKDIR /app
COPY . .
RUN cd theme/static_src && npm ci && npm run build

FROM stagex/core-go:sx2026.06.0@sha256:cb940590e2f59d1c87291b15a94ff425a5fdaf55fa07bb65badfde9b956bf262 AS zoneinfo

FROM stagex/pallet-python:sx2026.06.0@sha256:8b238a3f0ee6a4d30fb5a081868d910d8b90362d33ae6674ab6d548d8c9f0fd7 AS base
COPY --from=uv /uv /uvx /bin/
# UV_PYTHON: use the base image's interpreter instead of the .python-version pin.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/bin/python \
    UV_PROJECT_ENVIRONMENT=/venv \
    PATH=/venv/bin:$PATH
# StageX ships no zoneinfo; TIME_ZONE needs it. Unpacked from Go's copy so no
# tzdata dependency is added; Python's zoneinfo reads /usr/share/zoneinfo first.
COPY --from=zoneinfo /usr/lib/go/lib/time/zoneinfo.zip /tmp/zoneinfo.zip
RUN python -c "import zipfile; zipfile.ZipFile('/tmp/zoneinfo.zip').extractall('/usr/share/zoneinfo')" \
    && rm /tmp/zoneinfo.zip
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
COPY --from=assets /app/theme/static/css/dist theme/static/css/dist

# Hermetic CI gate: no database or network; CI builds this target and discards it.
# Model checks (GeneratedField) and pytest need PostgreSQL, so only the
# security checks run here.
FROM base AS test
# A throwaway key long and random enough to pass check --deploy.
ENV DJANGO_SECRET_KEY=test-only-7f3a9c1e5b8d2f6a4c9e1b7d3f5a8c2e6b9d4f1a7c3e8b5d \
    DJANGO_READ_DOT_ENV_FILE=False
RUN python manage.py check --deploy --tag security --fail-level WARNING \
    && python manage.py makemigrations --check --dry-run --skip-checks

FROM base AS runtime
# Empty until the shared workflow passes the triggering commit.
ARG SOURCE_SHA=""
ENV SOURCE_SHA=$SOURCE_SHA \
    APPLICATION_REVISION=$SOURCE_SHA \
    DJANGO_READ_DOT_ENV_FILE=False
RUN DJANGO_SECRET_KEY=build python manage.py collectstatic --no-input --skip-checks
USER 10001:10001
EXPOSE 8000
# The StageX base sets ENTRYPOINT to python, which would wrap the CMD below.
ENTRYPOINT []
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "--access-log", "-", "config.asgi:application"]
