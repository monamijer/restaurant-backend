"""The single place where a table's status changes.

Phase 3 only has the manual override used by staff. Phase 4 adds the automatic
transitions (reservation arrives, order opens, bill paid) to this same module."""


def set_table_status(table, new_status):
    table.status = new_status
    table.save(update_fields=["status", "updated_at"])
    return table