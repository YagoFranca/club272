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
│   │   ├── components.py       # Card, Botão, Badge, Tabela, Campo…
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

## Telas

| Tela | O que faz |
| --- | --- |
| **Presença** | Abre evento, reconhece rostos ao vivo e registra presença |
| **Eventos** | Histórico, lista de presença de cada evento e exportação CSV |
| **Membros** | Lista com busca, edição e remoção de cadastros |
| **Cadastro** | Registro individual capturando o rosto pela webcam |
| **Cadastro em lote** | Importa CSV/Excel, vincula fotos e processa |
| **Sincronização** | Estado da nuvem, envio/recebimento, exportação de membros |

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
CLUB272_DB=caminho.db    # usa outro banco (testes, experimentos)
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

## Verificação

```bash
python -m compileall -q club272 run.py     # tudo compila
python -m pyflakes club272/ run.py         # sem nomes indefinidos
python -c "import club272.app"             # dependências no lugar
```

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
