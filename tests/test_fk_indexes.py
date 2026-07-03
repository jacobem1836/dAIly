"""Regression test for audit H6: unindexed foreign keys.

Postgres does not auto-index foreign key columns, so every `WHERE user_id = X`
query against these tables sequential-scanned. Migration 008_add_fk_indexes
adds btree indexes; this test asserts the ORM column definitions agree (so a
future model change can't silently drift from the migration) by checking each
FK column's SQLAlchemy `index` flag directly on the Column object.
"""


def test_integration_token_user_id_is_indexed():
    from daily.db.models import IntegrationToken

    assert IntegrationToken.__table__.c.user_id.index is True


def test_pairing_code_user_id_is_indexed():
    from daily.db.models import PairingCode

    assert PairingCode.__table__.c.user_id.index is True


def test_device_token_user_id_is_indexed():
    from daily.db.models import DeviceToken

    assert DeviceToken.__table__.c.user_id.index is True


def test_signal_log_user_id_is_indexed():
    from daily.profile.signals import SignalLog

    assert SignalLog.__table__.c.user_id.index is True


def test_action_log_user_id_is_indexed():
    from daily.actions.models import ActionLog

    assert ActionLog.__table__.c.user_id.index is True


def test_migration_008_creates_expected_fk_indexes():
    """Migration 008 must create exactly the indexes matching the ORM columns above."""
    import importlib.util
    from pathlib import Path

    module_path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "008_add_fk_indexes.py"
    )
    spec = importlib.util.spec_from_file_location("migration_008", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    tables_indexed = {table for _name, table, _col in module._INDEXES}
    assert tables_indexed == {
        "integration_tokens",
        "pairing_codes",
        "device_tokens",
        "signal_log",
        "action_log",
    }
    for _name, _table, column in module._INDEXES:
        assert column == "user_id"

    assert module.down_revision == "007_briefing_config_timezone"
