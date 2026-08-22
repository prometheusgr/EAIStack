"""Guards doc-search's read-only model mirror against backend schema drift.

mcp-servers/doc-search/app/models.py re-declares knowledge_base, embeddings,
and system_settings column-for-column, because doc-search is a separate
deployable with no shared package (see that module's docstring and
mcp-servers/doc-search/README.md's "Schema ownership" section). Alembic in
backend/ stays the sole schema authority; doc-search only reads.

Nothing structural stops the two declarations from diverging, and a
divergence is silent: adding a column to backend/app/db/models.py, or
changing Embedding.embedding's Vector dimension, leaves doc-search happily
importing and querying against a stale mapping until it fails at runtime —
or, for the vector dimension specifically, corrupts similarity results
rather than raising at all. These tests turn that into a failing unit test
at the moment the backend model changes.

Only the tables and columns doc-search actually mirrors are compared.
SystemSettings is deliberately a partial mirror (doc-search declares just
the embedding-relevant columns plus the row's identity/audit fields), so it
is checked as a subset: every column doc-search declares must still exist
in the backend with a compatible type, while backend-only columns are fine.
"""

import importlib.util
from pathlib import Path

import pytest

from app.db.models import Base as BackendBase

DOC_SEARCH_MODELS_PATH = (
    Path(__file__).resolve().parents[3] / "mcp-servers" / "doc-search" / "app" / "models.py"
)

# Tables doc-search mirrors in full: every column on the backend side must be
# present on the doc-search side and vice versa.
FULLY_MIRRORED_TABLES = ("knowledge_base", "embeddings")

# Tables doc-search mirrors only partially, by design.
PARTIALLY_MIRRORED_TABLES = ("system_settings",)


def _load_doc_search_base():
    """Import doc-search's models.py by file path, under its own module name.

    Both projects use the package name `app`, and the backend's is already
    imported by the time these tests run, so a plain `import app.models`
    would resolve to the wrong package. Loading by path sidesteps the
    collision without either project having to depend on the other.
    """
    spec = importlib.util.spec_from_file_location(
        "doc_search_models_under_test", DOC_SEARCH_MODELS_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Base


def _column_type_signature(column) -> str:
    """Compare column types by their compiled string form.

    The two projects construct separate instances of the same SQLAlchemy
    types, so identity and equality comparisons are useless; the rendered
    type ("VARCHAR(36)", "VECTOR(768)") is what actually has to match.
    """
    return str(column.type)


@pytest.mark.unit
def test_doc_search_models_file_exists():
    """The parity tests below silently pass if the path is wrong, so assert it."""
    assert DOC_SEARCH_MODELS_PATH.is_file(), (
        f"Expected doc-search models at {DOC_SEARCH_MODELS_PATH}. If the service moved, "
        "update DOC_SEARCH_MODELS_PATH here rather than deleting these parity tests."
    )


@pytest.mark.unit
@pytest.mark.parametrize("table_name", FULLY_MIRRORED_TABLES)
def test_fully_mirrored_table_has_identical_column_names(table_name):
    doc_search_base = _load_doc_search_base()
    backend_columns = set(BackendBase.metadata.tables[table_name].columns.keys())
    doc_search_columns = set(doc_search_base.metadata.tables[table_name].columns.keys())

    assert doc_search_columns == backend_columns, (
        f"{table_name} has drifted between backend/app/db/models.py and "
        f"mcp-servers/doc-search/app/models.py. "
        f"Only in backend: {sorted(backend_columns - doc_search_columns)}. "
        f"Only in doc-search: {sorted(doc_search_columns - backend_columns)}. "
        "Update the doc-search mirror to match the backend (the schema authority)."
    )


@pytest.mark.unit
@pytest.mark.parametrize("table_name", FULLY_MIRRORED_TABLES + PARTIALLY_MIRRORED_TABLES)
def test_mirrored_columns_have_matching_types(table_name):
    """Every column doc-search declares must have the backend's type.

    This is the check that catches a changed Vector dimension, which would
    otherwise produce wrong similarity results instead of a clean failure.
    """
    doc_search_base = _load_doc_search_base()
    backend_table = BackendBase.metadata.tables[table_name]
    doc_search_table = doc_search_base.metadata.tables[table_name]

    mismatches = []
    for column_name, doc_search_column in doc_search_table.columns.items():
        backend_column = backend_table.columns.get(column_name)
        if backend_column is None:
            mismatches.append(f"{column_name}: absent from backend model entirely")
            continue

        backend_type = _column_type_signature(backend_column)
        doc_search_type = _column_type_signature(doc_search_column)
        if backend_type != doc_search_type:
            mismatches.append(f"{column_name}: backend={backend_type} doc-search={doc_search_type}")

    assert not mismatches, (
        f"{table_name} column types have drifted between backend and doc-search: "
        f"{mismatches}. Update mcp-servers/doc-search/app/models.py to match the backend."
    )


@pytest.mark.unit
@pytest.mark.parametrize("table_name", PARTIALLY_MIRRORED_TABLES)
def test_partially_mirrored_table_declares_no_columns_the_backend_lacks(table_name):
    """doc-search may mirror a subset, but never invent a column."""
    doc_search_base = _load_doc_search_base()
    backend_columns = set(BackendBase.metadata.tables[table_name].columns.keys())
    doc_search_columns = set(doc_search_base.metadata.tables[table_name].columns.keys())

    unknown_columns = doc_search_columns - backend_columns
    assert not unknown_columns, (
        f"mcp-servers/doc-search/app/models.py declares {sorted(unknown_columns)} on "
        f"{table_name}, which the backend schema does not have. Querying them would "
        "fail at runtime against the real database."
    )


@pytest.mark.unit
def test_doc_search_mirrors_every_table_it_is_expected_to():
    """Fail if doc-search starts mirroring a table these tests don't cover.

    Without this, adding a fourth mirrored table to doc-search would leave it
    unguarded by the parity checks above, which enumerate tables explicitly.
    """
    doc_search_base = _load_doc_search_base()
    mirrored = set(doc_search_base.metadata.tables.keys())
    expected = set(FULLY_MIRRORED_TABLES) | set(PARTIALLY_MIRRORED_TABLES)

    assert mirrored == expected, (
        f"doc-search mirrors {sorted(mirrored)} but these parity tests cover "
        f"{sorted(expected)}. Add the new table to FULLY_MIRRORED_TABLES or "
        "PARTIALLY_MIRRORED_TABLES so it is drift-checked too."
    )
