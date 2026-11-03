# Team Farias — acessos e instalação no celular

## 1. Endereços

| Onde | Endereço |
| --- | --- |
| Este computador | http://127.0.0.1:8000 |
| Celular na mesma rede Wi‑Fi | **http://192.168.0.15:8000** |

> O IP `192.168.0.15` é o da máquina agora. Se o roteador trocar o IP, rode `ipconfig` e use o IPv4 novo. Para o PWA completo fora da rede, publique em um domínio com **HTTPS**.

Se o celular não abrir o endereço, libere o Python no firewall do Windows (PowerShell como administrador):

```powershell
New-NetFirewallRule -DisplayName "Team Farias 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

Escaneie o QR com a câmera do celular para abrir a tela de login:

![QR de acesso](acessos-qr.png)

## 2. Credenciais de teste

Senha de **todas** as contas: `teamfarias123`

| Perfil | E-mail | O que demonstra |
| --- | --- | --- |
| Administração | `farias@teamfarias.com.br` | Painel completo, incluindo **Nova matrícula** (a matrícula é feita só pela administração) |
| Professora | `marina@teamfarias.com.br` | Painel restrito às próprias turmas: agenda, presença, pontos e alunos |
| Aluna — Ana Sofia | `ana.almeida@aluno.teamfarias.com.br` | Área do aluno com pontos, calendário, mensalidades e comunicados |
| Aluno — João Pedro | `joao.lima@aluno.teamfarias.com.br` | Outro atleta para comparar ranking e evolução |
| Aluna — Beatriz | `beatriz.castro@aluno.teamfarias.com.br` | Atleta do feminino intermediário |
| Professor — Diego | `diego@teamfarias.com.br` | Segundo professor, com outras turmas |

### Criar uma matrícula de teste

1. Entre como administração.
2. Vá em **Matrículas → Nova matrícula**.
3. Preencha o atleta, escolha turma e plano. A senha pode ficar em branco (o sistema gera uma temporária).
4. Ao salvar, a tela mostra e-mail e senha **uma única vez**, com botão para enviar no WhatsApp.
5. A primeira mensalidade é criada automaticamente no financeiro.

Não existe mais autocadastro no site: todos os botões públicos levam para o WhatsApp da equipe.

As contas de demonstração são recriadas por:

```bash
python manage.py seed_demo --reset
```

## 3. Instalar como app no iPhone

1. Abra o endereço no **Safari**.
2. Toque em **Compartilhar** (quadrado com seta).
3. Escolha **Adicionar à Tela de Início**.
4. Confirme em **Adicionar**.

O ícone do Team Farias aparece na tela inicial e abre em tela cheia, com splash screen da logo.

> No iPhone, a instalação funciona também em endereço HTTP local. O cache offline e o modo aplicativo completo valem quando o site estiver em HTTPS.

## 4. Instalar como app no Android

1. Abra no **Chrome**.
2. Toque no menu **⋮**.
3. Toque em **Instalar app** (ou **Adicionar à tela inicial**).
4. Confirme.

Em HTTP local o Chrome oferece apenas o atalho. Com **HTTPS** o app é instalado de verdade (tela cheia, ícone, cache offline e atualizações automáticas).

## 5. Instalar no computador

Chrome/Edge: ícone de instalação na barra de endereço → **Instalar**.

## 6. Dicas de teste

- O site também tem um botão **Instalar app** no rodapé e um card **“Team Farias na tela inicial”** dentro da área do aluno.
- Depois de instalado, os convites de instalação desaparecem automaticamente.
- Sem internet, o app mostra a tela **“Você está sem conexão”** em vez de erro do navegador.
- A área logada nunca é gravada em cache — dados de alunos não ficam no aparelho.
