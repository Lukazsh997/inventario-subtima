"""Torna a tabela de auditoria somente-inserção no próprio banco de dados.

Mesmo que algum código futuro (ou alguém com acesso ao banco pela aplicação)
tente alterar ou apagar um registro de auditoria, o PostgreSQL recusa.
"""

from django.db import migrations

FORBID_FUNCTION = """
CREATE OR REPLACE FUNCTION patrimonio_forbid_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Tabela % e somente-insercao: % nao permitido', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""

CREATE_TRIGGERS = """
CREATE TRIGGER audit_auditlog_no_update BEFORE UPDATE ON audit_auditlog
    FOR EACH ROW EXECUTE FUNCTION patrimonio_forbid_change();
CREATE TRIGGER audit_auditlog_no_delete BEFORE DELETE ON audit_auditlog
    FOR EACH ROW EXECUTE FUNCTION patrimonio_forbid_change();
"""

DROP_TRIGGERS = """
DROP TRIGGER IF EXISTS audit_auditlog_no_update ON audit_auditlog;
DROP TRIGGER IF EXISTS audit_auditlog_no_delete ON audit_auditlog;
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [
        migrations.RunSQL(FORBID_FUNCTION, "DROP FUNCTION IF EXISTS patrimonio_forbid_change();"),
        migrations.RunSQL(CREATE_TRIGGERS, DROP_TRIGGERS),
    ]
