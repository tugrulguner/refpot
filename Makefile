.PHONY: install test lint format typecheck check changelog-draft changelog build clean

install:
	uv sync --all-groups --locked

test:
	uv sync --all-groups --locked --reinstall-package refpot
	uv run --locked pytest tests/ -v

lint:
	uv run --locked ruff check src/refpot/_core.pyi tests/test_release_contract.py tests/test_developer_docs.py tests/test_doc_parity.py examples/quickstart.py scripts/ src/refpot/sql.py src/refpot/_sql.pyi tests/test_sql_database.py tests/test_sql_docs.py tests/test_relational_native.py tests/test_native_sql.py tests/test_shared_change.py examples/sql_preview.py examples/experimental_native_sql.py examples/experimental_shared_change.py research/shared-change/ research/native-sql/
	uv run --locked ruff format --check src/refpot/_core.pyi tests/test_release_contract.py tests/test_developer_docs.py tests/test_doc_parity.py examples/quickstart.py scripts/ src/refpot/sql.py src/refpot/_sql.pyi tests/test_sql_database.py tests/test_sql_docs.py tests/test_relational_native.py tests/test_native_sql.py tests/test_shared_change.py examples/sql_preview.py examples/experimental_native_sql.py examples/experimental_shared_change.py research/shared-change/ research/native-sql/

format:
	uv run --locked ruff check --fix src/refpot/_core.pyi tests/test_release_contract.py tests/test_developer_docs.py tests/test_doc_parity.py examples/quickstart.py scripts/ src/refpot/sql.py src/refpot/_sql.pyi tests/test_sql_database.py tests/test_sql_docs.py tests/test_relational_native.py tests/test_native_sql.py tests/test_shared_change.py examples/sql_preview.py examples/experimental_native_sql.py examples/experimental_shared_change.py research/shared-change/ research/native-sql/
	uv run --locked ruff format src/refpot/_core.pyi tests/test_release_contract.py tests/test_developer_docs.py tests/test_doc_parity.py examples/quickstart.py scripts/ src/refpot/sql.py src/refpot/_sql.pyi tests/test_sql_database.py tests/test_sql_docs.py tests/test_relational_native.py tests/test_native_sql.py tests/test_shared_change.py examples/sql_preview.py examples/experimental_native_sql.py examples/experimental_shared_change.py research/shared-change/ research/native-sql/

typecheck:
	uv run --locked pyright src/ tests/ examples/ scripts/

check: lint typecheck test

changelog-draft:
	uv run --locked towncrier build --draft --version $$(uv version --short)

changelog:
	uv run --locked towncrier build --yes --version $$(uv version --short)

build:
	uv build

clean:
	rm -rf dist/ build/ *.egg-info .pytest_cache .ruff_cache .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
