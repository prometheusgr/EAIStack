# Adding Database Models & Migrations

This is the canonical worked example for adding a new database table or schema change. Follow this pattern exactly — new tables should look like this one, not invent a new shape.

Governing standards live in [AGENTS.md](../AGENTS.md); this doc is the how-to.

## 1. Write a Failing Test First (TDD)
```python
# tests/unit/test_new_model.py
def test_new_model_creation():
    """Test that new model persists to database."""
    model = NewModel(user_id="user-1", field="value")
    session.add(model)
    session.commit()

    retrieved = session.query(NewModel).filter_by(user_id="user-1").first()
    assert retrieved is not None
    assert retrieved.field == "value"
```

## 2. Define the SQLAlchemy Model
```python
# app/db/models.py
class NewModel(Base):
    """Description of what this model represents."""
    __tablename__ = "new_models"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    field = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    def __repr__(self):
        return f"<NewModel(id={self.id}, user_id={self.user_id}, field={self.field})>"
```

**Model best practices:**
- Always include `id` (UUID primary key), `user_id` (for data isolation), `created_at`, `updated_at`
- Add `index=True` to frequently queried columns (user_id, doc_id, etc.)
- Use proper types (String, Text, DateTime, JSON, Vector for pgvector)
- Include foreign keys with `ondelete='CASCADE'` for referential integrity
- Add soft-delete support with optional `deleted_at` column if needed

## 3. Generate the Alembic Migration
```bash
cd backend
# Alembic inspects models and generates migration
alembic revision --autogenerate -m "Add NewModel table"
```

This creates a new file in `alembic/versions/`.

## 4. Review the Generated Migration
Always review the generated migration file:
```python
# alembic/versions/xxx_add_new_model_table.py
def upgrade() -> None:
    op.create_table(
        'new_models',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False, index=True),
        sa.Column('field', sa.String(255), nullable=False),
        # ... other columns
        sa.PrimaryKeyConstraint('id')
    )

def downgrade() -> None:
    op.drop_table('new_models')
```

**Verify:**
- All columns are present with correct types
- Indexes are on the right columns
- Foreign keys have proper `ondelete` behavior
- Primary keys are defined correctly

## 5. Test the Migration Locally
```bash
cd backend

# Apply the migration
alembic upgrade head

# Run your new test to verify it works
pytest tests/unit/test_new_model.py -v

# Test rollback
alembic downgrade -1

# Re-apply to verify idempotency
alembic upgrade head
```

## 6. Commit Both Files
**Always commit the model AND the migration together:**
```bash
git add app/db/models.py
git add alembic/versions/xxx_add_new_model_table.py
git commit -m "Add NewModel with user isolation

- Stores new_field data per user
- Includes user_id index for query performance
- Soft-delete ready with deleted_at column
"
```

## 7. Run Full Test Suite
```bash
pytest tests/unit/ -v
```

All tests must pass, including the new model test and existing database tests.

---

## Migration Troubleshooting

**If a migration fails:**

1. **Column type mismatch** — Check that SQLAlchemy column types match database types. Use `compare_type=True` in env.py.
2. **Foreign key constraints** — Ensure parent table exists before creating child table. Alembic respects table order.
3. **Default values** — Use `server_default=` for database-level defaults, `default=` for Python-side defaults.
4. **pgvector columns** — Use raw SQL for Vector types: `op.execute("ALTER TABLE ... ADD COLUMN embedding vector(1536)")`

**To reset migrations in development (WARNING: loses data):**
```bash
# Drop all tables and version history
alembic downgrade base

# Re-apply from scratch
alembic upgrade head
```

**To inspect current schema:**
```bash
# View current migration version
alembic current

# View full history
alembic history --verbose

# Generate offline SQL (don't apply it)
alembic upgrade head --sql
```
