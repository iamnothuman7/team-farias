# Produção — Team Farias

## Arquitetura e isolamento

Domínio: https://teamfarias.nabio.pro. Ubuntu 22.04, Python 3.10, Django 5.2,
Gunicorn, PostgreSQL 14 e Nginx. Aplicação em `127.0.0.1:8100`, acessível externamente
somente por HTTPS. Porta interna não é aberta no firewall. Dois workers, duas threads,
limite de memória de 512 MiB; o serviço não executa como root.

Recursos exclusivos:

| Recurso | Identificação |
| --- | --- |
| Usuário Linux | `teamfarias`, sem shell de login |
| Serviço | `teamfarias.service` |
| Diretório | `/var/www/apps/teamfarias` |
| Banco | `teamfarias_prod` |
| Papel PostgreSQL | `teamfarias_app`, sem superusuário, CREATEDB ou CREATEROLE |
| Ambiente | `shared/.env`, root:teamfarias, modo 0640 |
| Código ativo | `current` aponta para `releases/DATA-COMMIT` |
| Release anterior | `previous` |
| Dependências | `.venv` própria em cada release; `venv` aponta para a ativa |
| Estáticos públicos | `shared/staticfiles` |
| Manifesto de estáticos | `staticfiles` dentro de cada release |
| Uploads | `shared/media` (nenhum fluxo de upload existe nesta versão) |
| Logs | `shared/logs` e `journalctl -u teamfarias` |
| Backups | `shared/backups`, acesso exclusivo de root |
| Desafio ACME | `shared/acme/.well-known/acme-challenge` |
| Nginx | `/etc/nginx/sites-available/teamfarias` e link em `sites-enabled` |
| TLS | `/etc/letsencrypt/live/teamfarias.nabio.pro` |

Não modifique recursos de outros projetos. Não reutilize a porta 8040 do Jumbi.
A auditoria de 03/11/2026 examinou listeners, systemd, Nginx, containers e declarações
de portas em `/var/www/apps`. A porta 8100 estava ausente de todos os inventários.
Há também reservas sem processo ativo; não são portas disponíveis.

## Variáveis

Definidas apenas no ambiente privado, sem segredos neste documento:

- `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_SSLMODE`
- `DJANGO_MEDIA_ROOT`, `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_SECURE_COOKIES`
- `DJANGO_HSTS_SECONDS`, `DJANGO_HSTS_INCLUDE_SUBDOMAINS`, `DJANGO_HSTS_PRELOAD`

Não defina `DJANGO_STATIC_ROOT` globalmente neste deploy: o Django utiliza o manifesto da própria
release e o Nginx serve a coleção compartilhada, mantendo hashes antigos para rollback.
Não carregue `seed_demo` em produção. Configure o preço interno real em `/painel/configuracoes/`;
a página pública não divulga preços. E-mail transacional não está configurado.

## Publicação e atualização

1. No checkout local, revise o diff e os segredos. Rode `python manage.py test --noinput`,
   `python manage.py makemigrations --check --dry-run` e `python manage.py check`.
2. Faça commit explícito somente dos arquivos do Team Farias, envie à `main` e confirme
   `git ls-remote origin refs/heads/main` igual ao commit testado.
3. Gere `git archive --format=tar.gz --output=release.tar.gz COMMIT` e calcule seu SHA256.
   Transfira o arquivo por SFTP para `shared/incoming` (root, modo 0700).
4. Execute como root o script versionado de preparação:

```bash
bash /var/www/apps/teamfarias/current/deploy/release.sh ARQUIVO COMMIT SHA256
systemd-analyze verify /etc/systemd/system/teamfarias.service
nginx -t
systemctl restart teamfarias.service
curl --fail https://teamfarias.nabio.pro/health/
```

Na primeira publicação, execute `deploy/release.sh` extraído do mesmo arquivo verificado,
antes de existir `current`. Cada arquivo é validado antes da extração. `REVISION` registra o SHA.
Nenhuma release anterior é removida automaticamente. Revise alterações de schema antes de migrar;
backs de banco não tornam uma migração destrutiva automaticamente reversível.

Os modelos de infraestrutura ficam em `deploy/`. Só instale os arquivos correspondentes ao
Team Farias. Use `nginx-http.conf` durante ACME e `nginx-https.conf` após emissão do certificado.
Execute `nginx -t` antes de `systemctl reload nginx`. Não reinicie o Nginx nem outras aplicações.

## Banco, backup e rollback

O papel da aplicação só deve ter acesso ao banco próprio. Não concede criação de bancos ou papéis.
Não mude `pg_hba.conf` nem parâmetros globais do PostgreSQL. Conexões da aplicação são locais.

```bash
bash /var/www/apps/teamfarias/current/deploy/backup.sh
systemctl list-timers teamfarias-backup.timer
```

O timer exclusivo executa diariamente às 05:10 UTC (02:10 em Fortaleza), com até dez minutos de
variação. Backups contêm somente banco, uploads e ambiente do Team Farias. São privados e não vão
para GitHub. Não existe cópia externa automática; configure armazenamento externo antes de depender
do servidor como única cópia. Não há exclusão automática de backups.

Rollback de código (sem reversão automática do banco):

```bash
base=/var/www/apps/teamfarias
old=$(readlink -f "$base/previous")
test -n "$old" && test -d "$old" && test -f "$old/REVISION"
ln -s "$old" "$base/current.rollback"
mv -Tf "$base/current.rollback" "$base/current"
systemctl restart teamfarias.service
curl --fail https://teamfarias.nabio.pro/health/
```

Antes disso, confirme compatibilidade das migrations da release anterior. Restauração de banco exige
janela de manutenção, backup atual e validação isolada com `pg_restore`; não restaure por cima de dados
novos sem uma decisão explícita. No primeiro deploy não existe release anterior: para retirar a aplicação,
pare somente `teamfarias.service` e desabilite somente o seu link Nginx após salvar a configuração.

## TLS e renovação

Certificado exclusivo via `certbot certonly --webroot`, sem alteração automática dos demais vhosts.
A configuração de renovação mantém o webroot. `deploy/renew-hook.sh` valida o Nginx e o recarrega
somente quando `RENEWED_LINEAGE` corresponde ao certificado do Team Farias.
O timer Certbot já existente fornece a renovação; não substitua o timer global.

```bash
certbot renew --cert-name teamfarias.nabio.pro --dry-run
openssl x509 -in /etc/letsencrypt/live/teamfarias.nabio.pro/fullchain.pem -noout -dates
```

HSTS fica em zero durante provisionamento e é ativado somente depois de validar HTTPS e o domínio.

## Saúde, logs e emergência

```bash
systemctl status teamfarias.service --no-pager
journalctl -u teamfarias.service --no-pager -n 100
ss -lntp 'sport = :8100'
curl --fail -H 'Host: teamfarias.nabio.pro' -H 'X-Forwarded-Proto: https' http://127.0.0.1:8100/health/
curl --fail https://teamfarias.nabio.pro/health/
curl -I http://teamfarias.nabio.pro/
```

`/health/` consulta o PostgreSQL e retorna `ok` ou HTTP 503 sem detalhes privados.
Login: `/entrar/`. Configurações: `/painel/configuracoes/`. Administração avançada: `/admin/`.
Troque a senha inicial em `/admin/password_change/` depois do primeiro login.
Os formulários têm CSRF; HTML autenticado não é cacheado. Login possui limite de requisições no Nginx.

## Proteções no navegador e instalação

As respostas HTML usam Content-Security-Policy: scripts e conexões somente da própria origem,
sem eval, objetos ou frames. Imagens HTTPS externas continuam permitidas para a logo configurável;
estilos inline são necessários para a cor da marca e os indicadores. Em HTTPS, URLs de recursos HTTP
são promovidas para HTTPS. Isso complementa o certificado e o HSTS; não substitui nenhum deles.
HTMX não executa scripts recebidos nem expressões eval. Permissões de câmera, microfone,
geolocalização e pagamento ficam desativadas, pois esta versão não utiliza essas APIs.

O manifesto estável está em `/manifest.webmanifest`, mantendo o ID `/app/` das instalações
anteriores. O service worker v7 preserva a regra de não armazenar páginas com sessão/CSRF.
O convite aparece a cada visita; instalações reconhecidas substituem o convite pelo status.
`appinstalled`, modo standalone e `getInstalledRelatedApps` são usados quando disponíveis.
Apenas aceitar a janela de instalação não grava uma instalação concluída. Um atalho declarado
manualmente aparece como “Atalho informado”, sem fingir confirmação do navegador. O registro
é local a cada navegador/perfil e pode não estar disponível em modo privado ou com armazenamento
bloqueado. No iOS, a aba do Safari nem sempre pode detectar o app instalado; abrir pelo ícone
confirma o modo app. Um novo `beforeinstallprompt` corrige um registro confirmado desatualizado.

Validação: `python manage.py test --noinput` e `node --test scripts/test-install.cjs`.
Os testes JavaScript simulam os eventos; não instalam um aplicativo no dispositivo de quem executa.

Quando o Chrome mostra certificado válido e ainda exibe “Não seguro”, confira o painel de
segurança e os recursos da aba afetada. Não ignore avisos nem desative proteções para instalar.
Uma nova aba HTTPS permite comparar com o estado anterior; o servidor sozinho não consegue
inspecionar extensões, exceções ou conteúdo injetado naquele perfil do navegador.

Referências: [CSP e HTTPS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/upgrade-insecure-requests),
[configuração HTMX](https://htmx.org/docs/#config),
[reconhecimento de PWA](https://developer.chrome.com/docs/capabilities/get-installed-related-apps).

Em falha, leia apenas logs do Team Farias, compare `current/REVISION` com o commit publicado,
verifique PostgreSQL e restaure a release anterior quando compatível. Não interrompa processos alheios
para liberar recursos. Um erro de Nginx deve ser corrigido somente no vhost Team Farias.

A auditoria anterior encontrou 502 em `ramilosengenharia.nabio.pro` e erro de TLS em
`store.nabio.pro`; esses problemas são anteriores e não fazem parte deste deploy.

Referências: [checklist Django](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/),
[Certbot](https://eff-certbot.readthedocs.io/en/stable/using.html),
[Nginx proxy](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header).
# Notificações de comunicados

Use `WEBPUSH_PRIVATE_KEY` com o caminho de uma chave privada P-256 fora da release e do Git, `WEBPUSH_PUBLIC_KEY` com a chave pública X9.62 em base64url, e `WEBPUSH_SUBJECT` com a URL pública do site. A chave privada deve ser legível somente por root e pelo grupo do serviço.

Instale `deploy/teamfarias-push.service` e `deploy/teamfarias-push.timer` em `/etc/systemd/system/` e habilite o timer. Ele executa `manage.py send_push` como usuário `teamfarias`, usando o ambiente privado existente, a cada minuto após concluir a execução anterior. Preserve o par de chaves entre releases; trocar a chave invalida inscrições existentes.

Comandos de conferência: `systemctl status teamfarias-push.timer`, `systemctl status teamfarias-push.service` e `journalctl -u teamfarias-push.service`. O log mostra apenas estado de configuração e quantidade enviada, sem endpoints, chaves de aparelhos ou conteúdo dos comunicados.

Antes de rollback, avalie as migrações de planos e comunicados. Reativar o código anterior não restaura a antiga regra de plano único nem a publicação pública; não restaure o banco sem avaliar cadastros feitos desde o backup.
