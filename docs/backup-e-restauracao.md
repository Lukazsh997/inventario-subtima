# Backup e restauração

## O que o backup contém

Cada backup é um único arquivo `patrimonio-AAAAMMDD-HHMMSS-<rótulo>.tar` com:

- `database.dump`: banco completo (`pg_dump`, formato custom).
- `media.tar.gz`: arquivos do volume de dados (logotipos e modelos).
- `info.txt` (versão do sistema e data) e `SHA256SUMS` (conferência de integridade).

Banco e arquivos ficam sempre no mesmo pacote, para nunca serem restaurados fora de sincronia.

## Quando os backups são gerados

| Rótulo | Quando |
|---|---|
| `diario` | Todo dia no horário `BACKUP_TIME` (padrão 02:00), pelo serviço `scheduler` |
| `pre-migracao` | Automaticamente, antes de aplicar migrações em uma atualização |
| `pre-restauracao` | Automaticamente, antes de qualquer restauração |
| `manual` | Quando alguém executa o comando abaixo |

Os backups com mais de `BACKUP_RETENTION_DAYS` dias (padrão 30) são apagados.

**Guarde os backups fora do servidor.** Defina `BACKUP_PATH` com um compartilhamento de rede ou disco externo montado no host. O diretório precisa pertencer ao UID 1000 (`chown 1000:1000 <dir>`).

## Backup manual

```sh
docker compose exec app /app/docker/entrypoint.sh backup manual
docker compose exec app ls -lh /backups
```

## Restauração

1. Pare a aplicação para que ninguém grave dados durante a restauração:
   ```sh
   docker compose stop app scheduler
   ```
2. Liste os backups e restaure o escolhido. O `--sim` é a confirmação explícita:
   ```sh
   docker compose run --rm app restore
   docker compose run --rm app restore patrimonio-20261110-020000-diario.tar --sim
   ```
   O script confere o checksum, gera um backup `pre-restauracao` do estado atual e então substitui banco e arquivos.
3. Suba de novo: `docker compose up -d`.

## Teste de restauração

Faça um teste por trimestre em um servidor de homologação: restaure o backup diário mais recente e confira se usuários, setores e registros recentes estão lá. O procedimento foi validado no desenvolvimento, com banco e arquivos voltando ao estado do backup e os gatilhos de auditoria preservados.
