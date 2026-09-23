# 272 Club — Sistema Integrado de Reconhecimento Facial

Controle de presença em eventos por reconhecimento facial, com banco local
SQLite e sincronização opcional com o Supabase. Funciona offline.

## Como rodar

```bash
pip install -r requirements.txt
cp .env.example .env      # opcional: credenciais do Supabase
python run.py
```

Uma janela, com navegação lateral entre as telas.

## Estrutura

```
272club/
├── run.py                      # ponto de entrada
├── restaurar_backup.py         # lista e restaura backups do banco
├── .env / .env.example         # credenciais (o .env não é versionado)
├── club272/
│   ├── app.py                  # monta o shell com todas as telas
│   ├── config.py               # caminhos, credenciais e desempenho
│   ├── core/                   # regra de negócio, sem interface
│   │   ├── database.py         # SQLite + sincronização
│   │   ├── encoding.py         # serialização de encodings faciais
│   │   ├── recognition.py      # câmera, detecção e identificação
│   │   ├── importacao.py       # CSV/Excel para cadastro em lote
│   │   └── supabase.py         # cliente da API REST
│   ├── ui/
│   │   ├── theme.py            # design system: cor, tipografia, espaço
│   │   ├── components.py       # Card, Botão, Badge, Tabela, Campo, Ícone…
│   │   ├── shell.py            # janela, sidebar, topbar, barra de status
│   │   ├── assets.py           # logo e ícone
│   │   └── screens/            # uma tela por arquivo
│   └── assets/272club.png
├── data/                       # runtime, fora do controle de versão
│   ├── sistema_integrado.db · images/ · photos/ · backups/
└── templates/template_cadastro_lote.csv
```

A separação é a regra do projeto: **`core/` não importa nada de `ui/`**. Toda a
lógica é testável sem abrir janela, e as telas só montam widgets.

Os ícones vêm da **Segoe Fluent Icons** (a fonte de ícones do Windows), pelo
nome — `Icone(pai, "calendario")`. Emoji não servem: o Tk não desenha emoji
colorido no Windows, e o glifo sai como um borrão monocromático. Sem a fonte
instalada, o componente cai num marcador neutro em vez de um retângulo vazio.

## Telas

| Tela | O que faz |
| --- | --- |
| **Presença** | Reconhece rostos ao vivo e registra presença no evento aberto |
| **Eventos** | Abre e encerra eventos, histórico, listas de presença e relatórios |
| **Membros** | Lista com busca, edição e remoção de cadastros |
| **Cadastro** | Registro individual capturando o rosto pela webcam |
| **Cadastro em lote** | Importa CSV/Excel, vincula fotos e processa |
| **Sincronização** | Estado da nuvem, envio/recebimento, exportação de membros |

### Relatórios

Eventos e membros exportam em **Excel (.xlsx)** por padrão, com título,
cabeçalho fixo, filtro automático, faixas alternadas, larguras ajustadas e um
rodapé de totais. CSV continua disponível na mesma caixa de diálogo.

O CSV usa o **separador de lista da região do Windows** (`;` em pt-BR), lido
do registro — a mesma fonte que o Excel consulta. Com a vírgula padrão do
Python, o Excel brasileiro abria o arquivo com tudo amontoado numa coluna só.
A gravação é em `utf-8-sig`: sem o BOM, os acentos saem errados.

Abrir e encerrar evento fica na tela de **Eventos**, junto do histórico; a
tela de Presença apenas mostra qual evento está em curso. O relatório só
libera depois de encerrar — enquanto o evento corre a lista ainda muda, e um
arquivo exportado no meio vira um número errado circulando por aí.

Só um evento fica aberto por vez: abrir um novo encerra o anterior. Sem essa
garantia o segundo evento ficaria invisível — a busca devolve apenas o
primeiro, e as presenças seguintes iriam para um evento inalcançável.

## Desempenho

O gargalo é o `face_encodings` do dlib: ~400 ms por rosto numa máquina moderna
sem AVX. O alvo de produção é um Core 2 Duo, anterior ao AVX, onde deve passar
de 1 s. Recompilar o dlib não resolve — a instrução não existe nesse
processador.

Duas medidas atacam isso **sem afrouxar o critério de identificação**:

**1. O encoder roda em outro processo.** O binding do dlib não libera o GIL:
medido, uma chamada em thread congela a janela por ~440 ms. Em processo
separado, o pior travamento da interface caiu de 505 ms para 72 ms.

**2. Cascata de portões.** Cada etapa só roda se a anterior passar:

| Portão | Custo | Descarta |
| --- | --- | --- |
| houve movimento? | 0,04 ms | sala parada |
| Haar detectou rosto? | 5 ms | cena sem gente |
| caixa estável em 2 passadas? | 0 ms | falso positivo do Haar |
| já resolvido e no mesmo lugar? | 0 ms | quem já foi registrado |
| → encoder | 400 ms+ | só rosto novo |

Medido em 3 s de cada cenário: sala vazia **0 encodings**; estranho parado
**1**; cadastrado **3** (as confirmações) e então rastreado.

O portão de movimento tem duas salvaguardas. A referência só é trocada quando
a análise de fato acontece — comparar sempre com o quadro anterior esconde
movimento lento, e o laço gira mais rápido que a câmera, então boa parte das
comparações seria de um quadro com ele mesmo. E um batimento força a análise a
cada `INTERVALO_BATIMENTO`, limitando o atraso máximo para notar alguém mesmo
que o movimento nunca supere o limiar.

A detecção usa Haar em vez do HOG do dlib. Verificamos que trocar a caixa do
HOG pela do Haar desloca o encoding em **0,086**, contra uma tolerância de
0,45 — não muda o veredito. E a caixa ainda é refinada com HOG no recorte.

### Ajuste por variável de ambiente

O perfil leve já é o padrão (câmera 480×360, 15 fps, detector Haar):

```bash
CLUB272_PERFIL=normal    # máquina boa: 640x480, 30 fps
DETECTOR=hog             # detector mais preciso, 2,6x mais caro
FILTRO_MOVIMENTO=0       # desliga o portão de movimento
INTERVALO_BATIMENTO=1.5  # segundos entre análises forçadas
FACE_TOLERANCE=0.45      # menor = mais rigoroso
CLUB272_DB=caminho.db    # usa outro banco; fotos e backups seguem junto
```

### Escolha da câmera

Por padrão (`CAMERA_INDICE=auto`) o sistema sonda os dispositivos e fica no
primeiro que entrega imagem de verdade. Isso existe porque câmeras virtuais
(NVIDIA Broadcast, OBS) costumam ocupar o índice 0 e **abrir com sucesso
devolvendo quadros pretos** — a prévia ficava escura sem nenhuma explicação.

```bash
CAMERA_INDICE=2          # força um dispositivo específico
CAMERA_MAX_INDICE=4      # quantos sondar na busca automática
CAMERA_DESVIO_MINIMO=1.0 # desvio padrão mínimo para o quadro valer como imagem
```

## Banco de dados

Um arquivo, `data/sistema_integrado.db`. Schema em
[`core/database.py`](club272/core/database.py):

| Tabela | Conteúdo |
| --- | --- |
| `usuarios` | cadastro + encoding facial + status de sync |
| `eventos` | eventos abertos/fechados |
| `presencas_evento` | presenças por evento |
| `sync_log` | histórico das sincronizações |

IDs automáticos seguem `TSU_XXXXX`, a partir de `TSU_10000`.

O arquivo atual traz também `historico_detalhado`, `config_sistema` e as
colunas `email`/`is_deleted`, resquícios de uma versão antiga que nenhum código
usa. Foram preservados, mas não fazem parte do schema criado do zero.

### Importar a base do sistema antigo

O sistema anterior guardava tudo numa tabela `registrations`, com as mesmas
colunas que hoje vivem em `usuarios`. Os encodings faciais são compatíveis —
mesmo dlib, mesmos 128 valores — então quem já estava cadastrado continua
sendo reconhecido sem tirar foto de novo.

```bash
python importar_base_antiga.py local_database.db --fotos Images/
```

Por padrão não sobrescreve quem já existe. Opções: `--substituir`,
`--pular-sem-rosto` e `--normalizar-grupos`, que unifica grafias como
"G 19"/"G19" e "Oficial 0"/"OF 0" na mais usada.

### Backups

`data/backups/` guarda cópias automáticas (antes de cada lote, por exemplo).
Para inspecionar e restaurar:

```bash
python restaurar_backup.py                  # lista com o conteúdo de cada um
python restaurar_backup.py <arquivo.db>     # restaura
```

O banco atual nunca é descartado: vira `antes_de_restaurar_*.db`.

## Configuração

Nada de segredo no código. Tudo vem do `.env`:

| Variável | Para que serve |
| --- | --- |
| `SUPABASE_URL` | URL do projeto Supabase |
| `SUPABASE_KEY` | Chave pública `anon` |
| `SUPABASE_STORAGE_KEY` | Chave `service_role` — privilégio total, só para Storage |
| `SUPABASE_TABLE` | Tabela de usuários (padrão `FaceAttendenceRealTime`) |

Sem `.env`, o sistema sobe offline: cadastro e reconhecimento funcionam, e os
registros ficam pendentes até haver destino.

## Distribuição

```bash
python empacotar.py
```

Gera `dist/272Club/` — pasta com executável e tudo de que ele precisa, sem
exigir Python na máquina de destino. A esteira também **roda a
autoverificação dentro do executável recém-gerado**: é o que pega um arquivo
de dados esquecido no `.spec`, que não quebra a construção nem a abertura e só
some na hora de reconhecer um rosto. Foi assim que descobrimos que os XML das
cascatas Haar não estavam indo junto.

Com o [Inno Setup](https://jrsoftware.org/isdl.php) instalado, sai também
`272Club-x.y.z-instalador.exe`. Sem ele, um `.zip` da pasta.

Modo pasta, e não arquivo único: o `--onefile` extrai ~450 MB para o disco a
cada abertura, e o alvo é um Core 2 Duo.

### Onde ficam os dados no executável

Instalado em "Arquivos de Programas", gravar ao lado do executável falha por
falta de permissão. Então há duas raízes:

| | Em desenvolvimento | Empacotado |
| --- | --- | --- |
| Recursos (logo, modelo CSV) | raiz do projeto | dentro do pacote |
| Dados (banco, fotos, backups, `.env`) | `data/` do projeto | `%LOCALAPPDATA%ºClub` |

Desinstalar **não remove** os dados do usuário — é lá que estão o banco e os
rostos.

## Verificação

```bash
python run.py --verificar                  # checa a instalação inteira
python -m compileall -q club272 run.py     # tudo compila
python -m pyflakes club272/ run.py         # sem nomes indefinidos
```

`--verificar` roda sem abrir janela e grava um relatório ao lado dos dados:
dependências, modelos do dlib, cascata Haar, permissão de escrita, banco,
fonte de ícones, processo do encoder e câmera. É o primeiro comando a rodar
numa máquina onde algo não funciona.

## Notas de manutenção

- **O projeto Supabase `bxdykjxoskysmywtdfoa` não existe mais** — o subdomínio
  retorna NXDOMAIN. O `sync_status = 'synced'` de alguns registros é histórico.
  Para religar, troque `SUPABASE_URL` e `SUPABASE_KEY` no `.env`; nenhuma linha
  de código muda.
- **Encodings faciais não são sincronizados.** O payload leva apenas `id`,
  `name`, `group`, `phone`, `total_attendance` e `last_attendance_time`. A
  única cópia dos rostos é o `.db` local — inclua-o na rotina de backup.
- **Saída de console em UTF-8.** `club272/__init__.py` reconfigura
  `stdout`/`stderr` na carga. Sem isso, os `print()` com emoji derrubam a
  aplicação quando a saída não é um console (arquivo, pipe, ou `.exe` sem
  console).

### Da versão antiga, ainda não portado

- Importação e exportação de encodings em arquivo `.pkl`
- CRUD de usuários direto na nuvem (criar/editar/apagar no Supabase)
- Relatórios mensais e anuais com gráficos — os métodos continuam em
  [`core/supabase.py`](club272/core/supabase.py), sem tela que os use. A
  exportação em CSV cobre o caso mais comum.
- Sincronização automática a cada 60 s: hoje o envio é manual, pela tela de
  Sincronização.
