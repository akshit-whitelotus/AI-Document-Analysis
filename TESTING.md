# Testing this project

## What's here and verified

| Service | Location | Tests | Status |
|---|---|---|---|
| `shared` | `shared/tests/` | JWT + password hashing | 9/9 passing |
| `auth-service` | `auth-service/tests/` | register/login/refresh/me, business logic + API | 15/15 passing |
| `document-service` | `document-service/tests/` | upload/list/get, ownership isolation, chunker properties | 17/17 passing |
| `chat-service` | `chat-service/tests/` | RAG query, owner_id enforcement, caching | 9/9 passing |
| `ai-worker-service` | `ai-worker-service/tests/` | FaissStore owner isolation, Celery task, embedder, search route | 18/18 passing |
| `gateway-service` | `gateway-service/tests/` | proxy forwarding, header allowlist, rate limiting | 9/9 passing |

**77/77 tests, all from actual `pytest` runs against this codebase** (not
just written-and-assumed) - see "How I verified this" at the bottom if you
want to reproduce that.

### Two real bugs found and fixed along the way

Writing property-based (`hypothesis`) tests for `document-service/app/utils/chunker.py`
- the function that splits extracted PDF text into chunks before
embedding - surfaced two genuine content-corruption bugs in the app
itself, not in the tests:

1. **Long unbroken runs of text got spurious spaces injected into them.**
   A stale loop variable was reused as the join separator on the
   character-level fallback path, so a chunk like a long URL or hash with
   no spaces/newlines anywhere would come out as `"h t t p s : / / ..."` -
   silently corrupting exactly the kind of token you don't want mangled
   before it's embedded and searched.
2. **The separator at a chunk boundary was silently dropped**, gluing
   adjacent words together (e.g. `"end of sentence"` + `"start of next"`
   became `"end of sentencestart of next"` with the space between them
   gone) whenever a chunk boundary fell exactly between two words.

Both are fixed in `app/utils/chunker.py` (delivered separately, see
below) via a rewrite that keeps separators as tokens in the split stream
instead of discarding them with `str.split()` and trying to patch them
back in afterward - the patch-up approach turned out to have its own
edge case where it could regenerate an identical over-length string
forever (`RecursionError`), so the fix also adds a hard-slice fallback
that guarantees termination no matter what the input looks like. All of
this was verified empirically (not just reasoned about) - see
`document-service/tests/unit/test_chunker_properties.py` and "How I
verified this" below.

All six suites are done. There's nothing left un-started, though the
"Extending this further" section below has a few ideas if you want more
depth in any one area (e.g. load/perf tests, contract tests between
services, testcontainers for a real Postgres/Redis integration tier).

## The pattern, in one paragraph

Every service is layered as **route -> service -> repository interface**.

Because the service layer only ever depends on the repository *interface*
(never on SQLAlchemy directly), we can substitute a small in-memory fake
for the repository in tests - no real Postgres needed. For the API layer,
FastAPI's `app.dependency_overrides` swaps the real dependency (`get_auth_service`,
`get_document_service`, ...) for one built on that same fake, so route tests
exercise real routing/validation/status-codes without a database, Redis, or
RabbitMQ running.

Two kinds of tests per service:
- **`tests/unit/`** - call the `*Service` class directly with a fake
  repository. Fastest, and where most business-rule coverage
  (duplicate email, wrong password, ownership checks, ...) should live.
- **`tests/api/`** - go through the real FastAPI routes with
  `httpx.AsyncClient` + `ASGITransport`, with dependencies overridden.
  Catches routing/schema/status-code mistakes a unit test can't.

## How to run

**Important: run each service's tests from *inside that service's
directory*, as a separate `pytest` invocation.** Every service has its own
top-level `app` package (`auth-service/app`, `document-service/app`, ...).
If you run `pytest` once from the repo root across all of them in a single
process, Python will only resolve `app` to whichever service's tests
import it first, and every other service's tests will silently import
the wrong code (or fail to import at all). Each service's `pytest.ini`
sets `pythonpath = .` for exactly this reason - keep the invocations separate.

```bash
# one-time setup: install shared + all service deps into a venv,
# same as the Dockerfile does
python -m venv .venv && source .venv/bin/activate
pip install -e .              # installs the `shared` package
pip install pytest pytest-asyncio httpx

# each service also needs its own runtime deps installed, e.g.:
pip install fastapi "sqlalchemy>=2.0" asyncpg "pydantic[email]" \
    "python-jose[cryptography]" "passlib[bcrypt]==1.7.4" "bcrypt==4.0.1" \
    python-multipart redis tenacity structlog pymupdf faiss-cpu numpy celery hypothesis

# ai-worker-service's tests stub out sentence_transformers (see
# tests/conftest.py) so you do NOT need to install it or download any
# model - that's deliberate, it's a huge/slow dependency and the actual
# embedding math isn't what those tests check.

# these env vars just need to be *present and well-formed* - none of
# these tests make a real DB/Redis/RabbitMQ connection
export POSTGRES_HOST=localhost POSTGRES_PORT=5432 POSTGRES_DB=test \
       POSTGRES_USER=test POSTGRES_PASSWORD=test \
       JWT_SECRET_KEY=test-secret JWT_ALGORITHM=HS256 ACCESS_TOKEN_EXPIRE_MINUTES=30 \
       REDIS_HOST=localhost REDIS_PORT=6379 \
       RABBITMQ_HOST=localhost RABBITMQ_PORT=5673 RABBITMQ_USER=guest RABBITMQ_PASSWORD=guest

# ai-worker-service also reads these directly - throwaway values are fine,
# tests override the actual paths used per-test anyway, this just needs
# to be present so Settings() doesn't fail to load:
export EMBEDDING_MODEL=fake-model VECTOR_STORE_DIR=/tmp/vs UPLOAD_DIR=/tmp/up

cd shared             && pytest tests -q ; cd ..
cd auth-service        && pytest -q ; cd ..
cd document-service    && pytest -q ; cd ..
cd chat-service         && pytest -q ; cd ..
cd ai-worker-service     && pytest -q ; cd ..
cd gateway-service        && pytest -q ; cd ..
```

Or add a `Makefile`/CI job that just loops over the service directories
and runs `pytest` in each - see "CI" below.

## Extending this further

Everything planned is done and verified, but if you want to go deeper:

- **Integration tier with real infra**: spin up real Postgres/Redis/RabbitMQ
  via `docker compose` (or `testcontainers-python`) for a smaller set of
  true end-to-end tests - e.g. actually run `alembic upgrade head` against a
  throwaway Postgres and hit the real repositories, or run a real Celery
  worker against a real RabbitMQ for one true `process_document` test. The
  fakes/mocks used everywhere else trade that realism for speed, which is
  the right tradeoff for most tests but not all of them.
- **Contract tests between services**: e.g. assert chat-service's
  `SearchRequest` payload shape matches what ai-worker-service's
  `SearchRequest` schema actually accepts, so a field rename on one side
  fails a test instead of failing silently at 3am.
- **Load/perf tests**: `FaissStore.search()` does a full-index scan and
  filters in Python (see the comment in `faiss_store.py`) - fine at small
  scale, but worth a benchmark test once you have real document volume, to
  know when to switch to a filtered/approximate index instead.
- **Property-based tests** (`hypothesis`) for `pdf_extractor.py`'s
  page-boundary handling and multi-page joins - the same technique that
  found the two chunker.py bugs above (see `test_chunker_properties.py`)
  would be worth pointing at this next; it just needs real/synthetic PDF
  fixtures rather than plain strings, which is more setup.

## CI

Once you're happy with the coverage, a minimal GitHub Actions job that
respects the "one process per service" rule above:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [shared, auth-service, document-service, chat-service, ai-worker-service, gateway-service]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e . pytest pytest-asyncio httpx fastapi \
                 "sqlalchemy>=2.0" asyncpg "pydantic[email]" \
                 "python-jose[cryptography]" "passlib[bcrypt]==1.7.4" \
                 "bcrypt==4.0.1" python-multipart redis tenacity \
                 structlog pymupdf faiss-cpu numpy celery hypothesis
      - run: |
          export POSTGRES_HOST=localhost POSTGRES_PORT=5432 POSTGRES_DB=test \
                 POSTGRES_USER=test POSTGRES_PASSWORD=test \
                 JWT_SECRET_KEY=test JWT_ALGORITHM=HS256 ACCESS_TOKEN_EXPIRE_MINUTES=30 \
                 REDIS_HOST=localhost REDIS_PORT=6379 \
                 RABBITMQ_HOST=localhost RABBITMQ_PORT=5673 RABBITMQ_USER=guest RABBITMQ_PASSWORD=guest \
                 EMBEDDING_MODEL=fake-model VECTOR_STORE_DIR=/tmp/vs UPLOAD_DIR=/tmp/up
          cd ${{ matrix.service == 'shared' && '.' || matrix.service }}
          pytest ${{ matrix.service == 'shared' && 'shared/tests' || '' }} -q
```

## How I verified this

For all six of these (`shared`, `auth-service`, `document-service`,
`chat-service`, `ai-worker-service`, `gateway-service`), I didn't just write
these tests - I built a venv, installed each service's real dependencies,
mimicked exactly what your `Dockerfile` does (copying only `pyproject.toml`
+ `README.md` + `shared/` into a clean build context before
`pip install -e .`), exported the env vars above, and ran `pytest` for
real. That process caught and fixed several bugs **in my test code** (not
your app) along the way:

- Asserted `403` for a missing auth header; your FastAPI version's
  `HTTPBearer` actually returns `401`.
- An in-memory fake repository did an exact dict lookup by UUID object,
  but real code passes JWT `sub` claims as plain strings - needed to
  normalize both sides the way Postgres/asyncpg would.
- Asserted two JWTs minted in the same second would have different
  signatures - they don't, because JWTs are deterministic for identical
  claims. Not a meaningful assertion.
- Wired chat-service's API test through `app.dependency_overrides` for
  `RAGService` before realizing it's attached to `app.state` during
  lifespan, not injected via `Depends()` - fixed by setting
  `app.state.rag_service` directly instead.
- For `ai-worker-service`, I empirically confirmed (rather than assumed)
  that calling a bound Celery task's `.run()` directly outside a real
  worker context makes `self.retry(exc=exc)` re-raise the original
  exception instead of doing real retry bookkeeping - that's what the
  `pytest.raises(...)` failure-path tests in `test_tasks.py` rely on.

I also used the `ai-worker-service` and `gateway-service` suites to
directly re-verify the `owner_id` fix from earlier in this conversation:
I temporarily reverted the `owner_id` line in `tasks.py` back to its old
(unfixed) form and reran `test_tasks.py` - it failed with a clear
"expected call not found" error naming exactly the missing `owner_id`
argument, then passed clean again once the fix was restored. That's the
same thing I'd done earlier for `chat_query_route.py` - proof these tests
actually exercise the fix rather than rubber-stamping it.

That's the value of actually running tests rather than eyeballing them:
several of these would have been silent false-positives (tests that pass
regardless of whether the app is correct) if I'd shipped them unverified.

The `chunker.py` bugs went through the same discipline, one level further:
the first property test I wrote (`test_chunking_with_no_overlap_never_loses_or_corrupts_content`)
failed immediately against the real code with a hypothesis-shrunk minimal
example. I fixed it, and the *fix itself* introduced a second bug
(`RecursionError` on a specific edge case) that a second property test
caught before it ever reached you. The final version passed a 3,000-example
stress run (well beyond the suite's normal 200-300 examples per property)
with zero failures before I called it done.
