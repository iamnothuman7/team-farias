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

## Revisão do app no celular, login e primeira tela

Corrigida uma configuração JavaScript que reativava `globalViewTransitions` apesar do valor falso no HTML. A auditoria anterior usava movimento reduzido e não exercitava esse caminho. A auditoria agora usa a preferência normal e verifica explicitamente que a captura da página está desativada.

O cabeçalho público passa a ser fixo, com superfície opaca ao formar a cápsula, recorte apenas no conteúdo interno e menu separado. O layout respeita áreas seguras e mantém os controles dentro do cabeçalho. A primeira tela mantém a montagem inteira em seis viewports, incluindo 1366×768 e 1920×1080; o convite de instalação fica somente no rodapé do site, sem abertura automática na entrada. A rolagem permanece disponível com barra discreta.

Login reconstruído com formulário único, identificação da marca, campos de 54 px, mostrar/ocultar senha, ajuda e retorno ao site. Removido o foco automático que acionava o teclado na abertura. No sistema mobile, revisados cabeçalho fixo, navegação inferior, drawer, cards, formulários, nomes longos, tabelas em lista e ações. A barra inferior se esconde quando o teclado reduz a área visível durante a edição.

O card de instalação é ocultado após confirmação ou indicação manual do atalho. A janela fecha ao detectar o modo app, confirmação tardia ou instalação reconhecida em outra aba. O temporizador não ignora dispensas recentes nem navegação para outra página. A [detecção de instalação varia entre navegadores](https://web.dev/learn/pwa/detection); por isso o reconhecimento considera o modo de exibição, os eventos e o registro deste navegador, sem marcar todos os aparelhos do aluno como instalados.

O HTMX atualiza os arquivos CSS com hash após uma publicação, sem reenviar formulários ou interromper a navegação.

Validação: 111 testes Django e 31 testes Node aprovados; 27 testes de core repetidos após o ajuste final da home. Auditoria de 128 combinações sem overflow e com os fluxos de cobrança, produtos, login e navegação aprovados. `scripts/audit-mobile.py` verificou cinco viewports em Chromium e WebKit, com modo standalone e áreas seguras simulados, retorno ao app, login/logout, menu e persistência da instalação. Uma rodada final em Chromium verificou também teclado e atualização dos estilos via HTMX. Capturas de login, perfil e home foram inspecionadas. Não foi utilizado um iPhone físico; WebKit no Windows não reproduz todas as particularidades do Safari no aparelho.

## Matrículas, planos e financeiro: formulários e popups

Padronizados os diálogos de pagamento e confirmação com o visual do app, resumo em coluna, títulos associados por acessibilidade, botões de toque e corpo rolável com ações sempre acessíveis. O popup acompanha a altura e a posição do viewport visual quando o teclado aparece. O campo focado é trazido para a área visível; a geometria permanece estável durante a mudança de foco para os botões enquanto o teclado recolhe.

A baixa limpa método e observação ao reabrir o formulário, evitando reaproveitar dados de outra tentativa. A observação permite múltiplas linhas e respeita o limite de 200 caracteres. Matrícula e mensalidade avulsa mostram por inteiro a opção de turma, plano e aluno selecionada abaixo do controle nativo no mobile. A descrição dos planos agora usa várias linhas. Erros gerais foram padronizados e avisos ficam acima da navegação inferior, com fechamento por toque.

Auditoria reproduzível: `scripts/audit-management-mobile.py`, somente em banco local de desenvolvimento e com cadastros sintéticos removidos ao final. Foram verificadas 52 combinações de estado/tamanho/motor em Chromium e WebKit, com larguras de 320, 390 e 844 px, além de uma rodada final de 20 verificações em 390 px após os ajustes de teclado. Telas: plano vazio/com erros/edição/listagem, matrícula incompleta/seleções longas/conclusão/confirmação de recusa, financeiro com desconto inválido, popup de pagamento, confirmação de reabertura. Nomes longos e valor máximo foram exercitados. Não houve overflow nos limites verificados nem erros JavaScript.

Fluxos confirmados no PostgreSQL: matrícula cria aluno, vínculo com plano e primeira cobrança; edição do plano; desconto inválido não cria cobrança, desconto válido cria; cancelar baixa não paga; confirmar baixa paga; cancelar reabertura preserva o pagamento; confirmar reabertura volta a cobrança para aberta e remove a baixa. O método e a observação são limpos após cancelar e reabrir o popup. A observação e as ações permaneceram visíveis com viewport visual reduzido e troca de foco para Confirmar baixa.

Também passaram 34 testes Django de gestão/financeiro e 31 testes JavaScript. Capturas inspecionadas; teclado e áreas seguras simulados, sem uso de aparelho físico. Dados reais de produção não foram usados nos fluxos de escrita.

## Caixa da escolinha: entradas, saídas e despesas

A navegação Financeiro agora abre o Caixa, com acesso às Mensalidades e às Categorias. Receitas avulsas e despesas possuem descrição, categoria, pessoa/empresa, valor, vencimento, observações e situação. A baixa registra data real e forma de pagamento. O resumo distingue entradas e saídas confirmadas, saldo anterior, resultado, saldo registrado, valores a receber/pagar e atrasos do período. Despesas pagas podem ser consultadas por categoria.

Mensalidades não são copiadas para lançamentos manuais. O caixa lê os pagamentos pela data efetiva, enquanto a aba Mensalidades mantém a organização por competência. Reabrir uma mensalidade remove sua baixa do caixa automaticamente. Valores pendentes e cancelados não compõem o saldo realizado; o saldo é calculado pelos registros existentes, sem conexão bancária. Pedidos de produtos no WhatsApp não geram receitas automaticamente.

Novas categorias podem ser criadas e desativadas. Dez categorias iniciais cobrem receitas avulsas, produtos, eventos, patrocínios, aluguel, equipe, equipamentos, manutenção, taxas e outras despesas. Alterar o tipo de uma categoria utilizada é bloqueado. Lançamentos pendentes podem ser editados ou cancelados; realizados precisam ser reabertos antes da correção. Cancelados podem ser recuperados. O histórico preserva autor, data e valores anteriores/posteriores. Não há exclusão de lançamentos pela interface.

As operações usam transações e bloqueio de registros. Chaves de envio impedem duplicação em reenvios; reutilizar o formulário com valores diferentes pede abrir outro lançamento. A edição rejeita versões desatualizadas. Valores positivos, compatibilidade da categoria, data de baixa e método são validados no servidor; restrições no banco preservam valor/situação consistentes. As páginas e exportações são restritas à administração. O CSV respeita os filtros, desativa cache e protege células de texto contra interpretação como fórmulas.

Formulários, seletores, histórico e confirmações seguem o padrão mobile do app. Valores usam agrupamento de milhares; os cartões de pendências passam para uma coluna em telas pequenas. O popup de baixa acompanha o viewport visual e as áreas seguras. O guia Como usar explica o fluxo e a diferença entre competência, vencimento e caixa. O aviso da navegação inclui mensalidades e lançamentos manuais vencidos.

Validação de regras: 145 testes da suíte Django completa passaram, seguidos por 63 testes de financeiro e core após os últimos ajustes; 31 testes JavaScript passaram. Incluem permissões/CSRF, vírgula decimal, valores inválidos, categorias desativadas, reenvio, edição desatualizada, baixa, cancelamento, reabertura, recuperação, datas futuras, integração das mensalidades e exportação privada. As migrações adicionam tabelas e categorias; não alteram valores de cobranças existentes. Credenciais e dados de produção não fazem parte do código nem das fixtures.

A auditoria `scripts/audit-finance-mobile.py` verificou 98 combinações de estado/tamanho/motor em Chromium e WebKit: 320×740, 390×844, 844×390 e 1366×768. Foram exercitados filtros inválidos, formulários pendentes/realizados com erros, categorias com nomes longos, histórico expandido, baixa com data futura, teclado e áreas seguras simulados, reabertura cancelada/confirmada, cancelamento/recuperação, edição, desativação de categoria, entrada com vírgula decimal e download CSV. Os valores foram consultados no PostgreSQL após as ações. Nenhum overflow ou erro JavaScript foi identificado na rodada aprovada. O sidebar desktop foi verificado abrindo no hover e recolhendo ao sair. Capturas foram inspecionadas; não foi utilizado aparelho físico.

Regressão dos módulos existentes: `scripts/audit-browser.py` passou nas 128 verificações de layout do site e áreas de administrador/aluno, com pedido de produto, revisão da mensagem de WhatsApp (sem envio), edição com upload de foto, login/logout, navegação HTMX e reabertura de cobrança. O seletor de reabertura do teste foi restringido à cobrança sintética do próprio teste. `scripts/audit-management-mobile.py` passou novamente nas 52 verificações de matrícula, plano e mensalidade, incluindo criação, validação, pagamento, cancelamento de confirmação e reabertura. Os cadastros temporários foram removidos ao final. Rodadas interrompidas por falta de memória ao executar vários navegadores em paralelo foram descartadas; os resultados aprovados vieram de execuções sequenciais.

`scripts/audit-mobile.py` também passou em Chromium e WebKit: cinco viewports por motor, cápsula, menu, login de aluno, navegação, logout, teclado simulado, instalação reconhecida por evento ou confirmação manual após recarregar/navegar e troca dos estilos por HTMX. Os testes de baixa e de pedidos não fazem transferências, cobranças bancárias nem enviam mensagens reais.
