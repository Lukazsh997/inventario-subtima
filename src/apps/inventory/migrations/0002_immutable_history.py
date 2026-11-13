"""Histórico imutável: o banco rejeita UPDATE e DELETE em operações, movimentações e acessórios.

Reutiliza a função patrimonio_forbid_change() criada em audit/0002.
"""

from django.db import migrations

TABLES = ["inventory_stockoperation", "inventory_stockmovement", "inventory_operationaccessory"]

CREATE = "\n".join(
    f"CREATE TRIGGER {t}_no_update BEFORE UPDATE ON {t} FOR EACH ROW EXECUTE FUNCTION patrimonio_forbid_change();\n"
    f"CREATE TRIGGER {t}_no_delete BEFORE DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION patrimonio_forbid_change();"
    for t in TABLES
)
DROP = "\n".join(
    f"DROP TRIGGER IF EXISTS {t}_no_update ON {t};\nDROP TRIGGER IF EXISTS {t}_no_delete ON {t};" for t in TABLES
)


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0001_initial"),
        ("audit", "0002_auditlog_append_only"),
    ]

    operations = [migrations.RunSQL(CREATE, DROP)]
