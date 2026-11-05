# Produtos e revisão mobile — 05/11/2026

## Entrega

- Catálogo público em `/produtos/` e catálogo no aplicativo em `/app/produtos/`.
- Gestão de produtos pela administração em `/painel/produtos/`: foto, descrição, categoria, valor opcional, tamanhos, cores, nome e número na estampa, publicação, pausa de pedidos e ordem de exibição.
- Pedido com validação no servidor e revisão da mensagem antes de abrir o WhatsApp. Não há cobrança automática, envio automático de mensagem, confirmação de estoque ou registro de venda nesta etapa.
- Campos de personalização aparecem conforme a configuração do produto. A quantidade se refere a peças iguais; versões diferentes são combinadas em outro pedido.
- Catálogo começa vazio. Nenhuma foto, preço ou produto fictício é publicado.
- Imagens limitadas a 8 MB e 16 megapixels, verificadas e convertidas para WebP, sem metadados. SVG e arquivos que não são imagens são rejeitados. A edição é restrita à administração.
- Menu público em cápsula após rolar, com regras separadas para desktop e celular. Convite de instalação com altura automática, texto legível e espaço próprio.
- Confirmação de reabertura por diálogo do sistema, com cancelamento e foco no controle de fechar. O banco só muda após confirmação explícita.
- Ajustes para e-mails e nomes longos, campo de foto, tabelas em cartões no tablet, botões e margens no celular. Removidos o CTA duplicado de WhatsApp e o link antigo de notícias no rodapé.
- Desativadas as transições que capturavam a página inteira e podiam distorcer a interface durante navegação HTMX. A navegação continua sem recarregamento completo.

## Testes automatizados

111 testes Django em PostgreSQL e 25 testes Node passaram. A suíte Django foi repetida com a versão de produção de [Pillow 12.3.0](https://pypi.org/project/pillow/12.3.0/), incluindo a conversão e validação de fotos. Incluem permissões por perfil, matrículas e planos, cobrança e reabertura, agenda, presença, pontuação, notificações, instalação, catálogo, upload de fotos, opções inválidas, CSRF, produtos não publicados, mensagem codificada e confirmação de ações.

A confirmação de pagamento, reabertura e novo pagamento verificam que há apenas um pagamento vigente. Cancelar a confirmação não altera a cobrança. A reabertura desfaz a baixa anterior e volta a mensalidade para aberto; não é um estorno bancário.

## Navegador

Os testes usam uma instância isolada do Edge por [Playwright](https://playwright.dev/python/docs/browsers), contas e registros sintéticos no PostgreSQL local. O script `scripts/audit-browser.py` testa larguras de 320, 390, 768 e 1366 px, verifica os limites dos elementos e salva capturas. Os registros de teste são removidos ao final. Não envia mensagens no WhatsApp.

Resultado final: **128 combinações de tela e largura aprovadas**, sem elementos de conteúdo ultrapassando os limites verificados e sem erros JavaScript no navegador. As capturas da confirmação de cobrança e dos pedidos foram inspecionadas.

Fluxos exercitados: menu mobile e cápsula, navegação HTMX, montagem e edição de pedido, upload e edição de produto, login administrativo e de aluno, menu lateral, logout, cancelamento e confirmação de reabertura em celular e notebook, com consulta ao banco após cada alteração.

Esta verificação não substitui o teste em um iPhone ou Android físico. O recebimento real de notificações push depende da autorização em cada aparelho e continua fora desta auditoria de catálogo e layout.

## Operação

A administração entra em **Produtos Team Farias → Novo produto**, usa uma foto real e escolhe as opções disponíveis. Para vender sem estampa, deixe desmarcadas as opções de nome e número. Para artigos sem tamanho ou cor, deixe esses campos vazios. Salve como rascunho enquanto prepara os dados; publique após conferir.

O cliente usa **Escolher detalhes → Revisar pedido → Continuar no WhatsApp**. A mensagem permanece editável antes do envio. A equipe confirma o valor final, disponibilidade e entrega na conversa.

A alteração solicitada de acesso administrativo é feita diretamente no banco, preservando a conta e suas permissões. Credenciais não fazem parte do código, das migrações ou dos arquivos de teste versionados.

## Refinamento da instalação e crédito NaBio

A janela compartilhada pelo site e pelo sistema usa uma superfície mais simples, ações secundárias discretas e instruções específicas para iOS, Android e computador. No celular aparece próxima à borda inferior; em telas maiores fica centralizada. A rolagem interna atende telas baixas, com foco visível e respeito à preferência por movimento reduzido. Quando o navegador disponibiliza instalação direta, as instruções manuais ficam ocultas.

A logo original transparente da NaBio foi incorporada ao rodapé com o texto “Feito por:” e link externo para https://nabio.pro/, em nova aba. O arquivo original foi preservado.

Validação deste ajuste: 25 testes Node aprovados, verificação Django sem problemas e cinco combinações de viewport (320×640, 390×844, 768×900, 1366×768 e 844×390) em navegador isolado. Foram verificados os limites da janela e do rodapé, as instruções por dispositivo, lembrar/redefinir atalho e fechamento por botão e Escape. A aparência da confirmação nativa de instalação continua sendo controlada pelo navegador.
