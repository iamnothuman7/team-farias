# Auditoria funcional e responsiva — 04/11/2026

## Alterações

- Planos em `/painel/planos/`: cadastro, edição, ativação e desativação. A matrícula exige escolher um plano ativo e guarda o preço acordado. Os valores continuam fora do site público.
- Comunicados privados: removidos da página inicial e da navegação pública; os antigos endereços de notícias retornam 404. Alunos leem publicações destinadas a alunos; professores leem publicações internas da equipe. Rascunhos e publicações futuras não ficam disponíveis ao aluno.
- Web Push com autorização em cada aparelho. O aviso na tela bloqueada é genérico; a leitura requer login. Cadastro protegido por CSRF, endpoints restritos aos provedores conhecidos, vínculo por usuário, limite de aparelhos, remoção ao sair da sessão e desativação pelo aluno.
- Fila persistente, envio por timer, tentativas com intervalo crescente e remoção de inscrições expiradas. Uma publicação não é reenviada por simples edição. A migração não dispara os comunicados antigos.
- Guia em `/ajuda/`, no final da navegação lateral, com conteúdo adequado ao perfil.
- Regras próprias para celular, tablet e notebook. Tabelas administrativas viram cartões identificados no celular. Textos longos, formulários, agenda, matrícula, perfil, configuração e guias foram conferidos com dados sintéticos preenchidos.
- Retirados os dois destinos iguais de WhatsApp no convite final e o WhatsApp do cabeçalho, que repetia o convite principal. A seção “O celular na mão” ganhou uma composição própria com resumo da rotina.

## Falhas corrigidas durante a revisão

- Professor podia acessar a edição de treino de outra turma e gerar treinos para todas as turmas.
- Histórico e totais de pontuação do professor não estavam restritos às próprias turmas.
- Aluno sem turma podia ver treinos de outras turmas no calendário.
- POST direto permitia ao professor alterar campos administrativos de cadastro.
- Uma segunda confirmação de pagamento podia gerar outro registro de pagamento.
- Mensalidade avulsa exigia um campo de situação que não aparecia no formulário.
- Descontos inválidos e totais financeiros sem abatimento de desconto.
- Aprovação de matrícula sem revalidar vagas, turma ativa e plano ativo; validação reforçada sob transação.
- Horários com fim antes do início; filtros inválidos que podiam resultar em erro do servidor.
- Cards de turma e boas-vindas com conteúdo cortado em 320 px.
- Botão Sair deslocado durante a expansão da lateral no notebook.

## Verificação

- Suíte Django em PostgreSQL: 96 testes, incluindo matriz de rotas por perfil e navegação HTMX, criação de matrícula, seleção de plano, primeira cobrança, permissões, agenda, presença, pontos, financeiro, configurações, privacidade e fila de notificações.
- Node: 19 testes dos estados de instalação e notificações, incluindo permissão negada, cancelamento, falha no servidor, desativação e troca de páginas por HTMX.
- Browser: páginas administrativas e de aluno em 320, 390, 768 e 1366 px; formulários e detalhes em 320 e 1366 px; página pública também em 1024 px. Conferência dos limites dos elementos além da largura total do documento, para detectar conteúdo cortado dentro de cards.
- Interações no banco local: login, logout, criação de plano, matrícula com seleção desse plano, confirmação de valor da primeira mensalidade e diálogo de pagamento. Dados sintéticos de teste não são enviados à produção.
- Verificações de migração, sintaxe JavaScript, integridade do diff e configuração de implantação.

Esta auditoria cobre os cenários descritos; não é uma garantia de ausência de qualquer falha possível. Não foi realizado recebimento físico em um telefone. Transporte de push, indisponibilidade e expiração foram testados com respostas simuladas. A entrega final depende da permissão, do navegador, do aparelho e do serviço de push.

A confirmação de pagamento foi exercitada no navegador. Ao confirmar a reabertura, a ferramenta de navegação travou e não voltou a responder; a reabertura está validada pela suíte automatizada, mas sua última confirmação visual ficou pendente. A última correção do card público de turma em 320 px também não pôde ser reconferida visualmente após esse travamento.

## Operação de notificações

O aluno entra na conta, abre **Comunicados** e toca em **Ativar notificações**. Para iPhone/iPad, use um dispositivo compatível com Web Push e abra o app adicionado à Tela de Início. Veja a documentação do [WebKit](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/).

Na administração, os contadores significam **aceito pelo provedor**, **na fila** e **falha após tentativas**. Não significam leitura pelo aluno. Publicações futuras entram na fila após a data prevista; rascunhos não são enviados. Despublicar cancela envios ainda pendentes, mas não recolhe um aviso já recebido.
