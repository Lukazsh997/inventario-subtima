# Homologação e colocação em produção

## 1. Antes de subir

- [ ] Servidor com Docker e Docker Compose (ou Portainer), 2 vCPU, 4 GB de RAM e 20 GB livres.
- [ ] `.env` preenchido: `SECRET_KEY` nova (`python3 -c "import secrets; print(secrets.token_urlsafe(50))"`), `DB_PASSWORD` forte, `ALLOWED_HOSTS` com o nome e o IP de acesso, `ADMIN_INITIAL_PASSWORD`.
- [ ] `BACKUP_PATH` apontando para um disco que **não** seja o mesmo do Docker, ou rotina copiando o volume `backups` para outro servidor.
- [ ] Proxy HTTPS (recomendado; obrigatório para a câmera do celular).

## 2. Subir e verificar

```sh
docker compose up -d --build
sh scripts/verificar-implantacao.sh --rapido
```

`verificar_implantacao` mostra uma linha por item: `OK`, `AVISO` ou `FALHA`. Em produção, não pode haver `FALHA`. O aviso "nenhum backup encontrado" some depois do primeiro backup.

## 3. Teste de persistência (obrigatório, uma vez)

Fora do horário de uso, depois de cadastrar alguns dados reais:

```sh
sh scripts/verificar-implantacao.sh
```

O script faz um backup, tira um instantâneo (quantidade de usuários, setores, equipamentos, operações, termos, auditoria e um marcador gravado no volume de arquivos), **derruba e recria todos os containers** (`docker compose down` sem `-v`) e confere que nada se perdeu. Termina com "Teste de persistência concluído com sucesso".

No Portainer sem acesso ao terminal do servidor, o mesmo teste pela interface:
1. Console do container `app` → `python manage.py verificar_implantacao --json`; copie o resultado.
2. Na stack: *Stop* e depois *Start* (ou *Update the stack*).
3. Console do `app` → `python manage.py verificar_implantacao --json` de novo e compare: o `marcador` deve ser idêntico e nenhuma contagem pode ter diminuído.

## 4. Teste de restauração (obrigatório, uma vez)

Siga [backup-e-restauracao.md](backup-e-restauracao.md) em uma **stack de teste** (outro nome de projeto, por exemplo `docker compose -p patrimonio-teste`), restaurando o backup da produção. Confira se login, equipamentos e PDFs dos termos aparecem.

## 5. Carga inicial

1. Setores e locais (administrador).
2. Servidores recebedores (podem ser cadastrados também durante as operações).
3. Categorias e materiais de consumo com o estoque mínimo.
4. Equipamentos: planilha em **Equipamentos → Importar planilha** (veja [operacao.md](operacao.md)) ou leitura das etiquetas um a um.
5. Usuários da equipe, cada um com seu login e perfil.

## 6. Reversão (se uma atualização der errado)

Toda atualização que traz migrações gera antes um backup `patrimonio-…-pre-migracao.tar`.

1. Volte `APP_VERSION` para a versão anterior (a imagem anterior continua no servidor com a tag antiga).
2. Restaure o backup `pre-migracao`:
   ```sh
   docker compose stop app scheduler
   docker compose run --rm app restore /backups/patrimonio-AAAAMMDD-HHMMSS-pre-migracao.tar --sim
   docker compose up -d
   ```
3. Rode `verificar_implantacao`.

Operações feitas entre a atualização e a reversão se perdem; por isso, teste cada atualização logo depois de aplicá-la.
