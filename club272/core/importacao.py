"""
Importação de cadastros em lote a partir de CSV ou Excel.

Extraído da tela de cadastro em lote, onde a leitura da planilha, o vínculo das
fotos e a gravação no banco estavam entrelaçados com widgets do Tkinter. Aqui
não há interface: a tela chama estas funções e apenas mostra o progresso.
"""

import os
import shutil
from dataclasses import dataclass, field

import pandas as pd

from club272 import config
from club272.core.encoding import extrair_encoding, serialize_encoding

# Nomes aceitos para cada coluna — planilhas reais variam de caixa e idioma.
COLUNAS = {
    "id": ("id", "ID", "Id"),
    "nome": ("nome", "Nome", "name", "Name", "NOME"),
    "grupo": ("grupo", "Grupo", "group", "Group", "GRUPO"),
    "telefone": ("telefone", "Telefone", "phone", "Phone", "TELEFONE"),
    "foto": ("foto", "Foto", "photo", "Photo", "FOTO"),
}

EXTENSOES_FOTO = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

GRUPO_PADRAO = "Geral"


@dataclass
class Cadastro:
    """Uma linha da planilha, já normalizada."""

    id: str
    nome: str
    grupo: str = GRUPO_PADRAO
    telefone: str = ""
    foto: str = ""
    id_gerado: bool = False

    @property
    def tem_foto(self):
        return bool(self.foto) and os.path.exists(self.foto)


@dataclass
class Resultado:
    """Saldo de um processamento em lote."""

    sucessos: int = 0
    ignorados: int = 0
    erros: int = 0
    mensagens: list = field(default_factory=list)

    @property
    def total(self):
        return self.sucessos + self.ignorados + self.erros


def _valor(linha, chaves, padrao=""):
    """Lê a primeira coluna existente entre os apelidos, tratando NaN."""
    for chave in chaves:
        if chave not in linha:
            continue
        bruto = linha[chave]
        if pd.isna(bruto):
            continue
        texto = str(bruto).strip()
        # Rede de segurança para DataFrames que não passaram por ler_planilha:
        # "11999999999.0" volta a ser "11999999999".
        if texto.endswith(".0") and texto[:-2].isdigit():
            texto = texto[:-2]
        if texto and texto.lower() not in ("nan", "none"):
            return texto
    return padrao


def ler_planilha(caminho):
    """Lê CSV ou Excel e devolve o DataFrame.

    Tudo é lido como texto (`dtype=str`). Sem isso o pandas infere número em
    colunas como telefone e ID, e "11999999999" volta como 11999999999.0 —
    ou, em números maiores, em notação científica.

    O CSV é tentado em UTF-8 e depois em Latin-1, que é o que o Excel em
    português costuma gerar.
    """
    extensao = os.path.splitext(caminho)[1].lower()

    if extensao in (".xlsx", ".xls"):
        return pd.read_excel(caminho, dtype=str)

    for codificacao in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return pd.read_csv(caminho, encoding=codificacao, dtype=str)
        except UnicodeDecodeError:
            continue
    raise ValueError("Não foi possível ler o CSV em UTF-8 nem em Latin-1.")


def montar_cadastros(df, database, caminho_origem=None):
    """Converte o DataFrame em `Cadastro`, gerando IDs onde faltarem.

    IDs em branco recebem um `TSU_XXXXX` sequencial, continuando de onde o
    banco parou e sem colidir com IDs informados na própria planilha.
    """
    proximo = _proximo_numero(database)
    cadastros = []

    for posicao, (_, linha) in enumerate(df.iterrows(), start=1):
        informado = _valor(linha, COLUNAS["id"])

        if informado:
            identificador = informado
            gerado = False
            # Se a planilha já traz um TSU_, o contador precisa passar dele.
            if identificador.startswith(config.TSU_PREFIX):
                sufixo = identificador[len(config.TSU_PREFIX):]
                if sufixo.isdigit():
                    proximo = max(proximo, int(sufixo) + 1)
        else:
            identificador = f"{config.TSU_PREFIX}{proximo:05d}"
            proximo += 1
            gerado = True

        cadastro = Cadastro(
            id=identificador,
            nome=_valor(linha, COLUNAS["nome"], f"Usuário {posicao}"),
            grupo=_valor(linha, COLUNAS["grupo"], GRUPO_PADRAO),
            telefone=_valor(linha, COLUNAS["telefone"]),
            foto=_resolver_foto(_valor(linha, COLUNAS["foto"]), caminho_origem),
            id_gerado=gerado,
        )
        cadastros.append(cadastro)

    return cadastros


def _proximo_numero(database):
    proximo = database.get_next_tsu_id()
    sufixo = proximo[len(config.TSU_PREFIX):]
    return int(sufixo) if sufixo.isdigit() else config.TSU_START


def _resolver_foto(caminho, caminho_origem):
    """Resolve caminho relativo de foto contra a planilha e a pasta do sistema."""
    if not caminho:
        return ""
    if os.path.isabs(caminho) and os.path.exists(caminho):
        return caminho

    candidatos = [caminho]
    if caminho_origem:
        candidatos.append(os.path.join(os.path.dirname(caminho_origem), caminho))
    candidatos.append(str(config.IMAGES_DIR / os.path.basename(caminho)))

    for candidato in candidatos:
        if os.path.exists(candidato):
            return candidato
    return caminho  # devolve o original para aparecer como pendente


def vincular_fotos(cadastros, pasta):
    """Procura na pasta uma foto por ID ou por nome. Devolve quantas vinculou.

    Compara em minúsculas para não depender da caixa do nome do arquivo, que
    varia bastante entre câmeras e celulares.
    """
    if not os.path.isdir(pasta):
        return 0

    disponiveis = {}
    for arquivo in os.listdir(pasta):
        base, extensao = os.path.splitext(arquivo)
        if extensao.lower() in EXTENSOES_FOTO:
            disponiveis[base.lower()] = os.path.join(pasta, arquivo)

    vinculadas = 0
    for cadastro in cadastros:
        if cadastro.tem_foto:
            continue
        for chave in (cadastro.id.lower(), cadastro.nome.lower()):
            if chave in disponiveis:
                cadastro.foto = disponiveis[chave]
                vinculadas += 1
                break
    return vinculadas


def copiar_foto(usuario_id, origem):
    """Copia a foto para `data/images/` com o ID como nome. Devolve o destino."""
    config.ensure_directories()
    extensao = os.path.splitext(origem)[1] or ".jpg"
    destino = config.IMAGES_DIR / f"{usuario_id}{extensao}"
    shutil.copy2(origem, destino)
    return str(destino)


def processar(cadastros, database, validar_rosto=True, pular_existentes=True,
              progresso=None):
    """Grava os cadastros no banco, gerando os encodings faciais.

    `progresso(indice, total, cadastro, situacao)` é chamado a cada item, para
    a tela acompanhar sem conhecer nada do processamento.
    """
    resultado = Resultado()
    total = len(cadastros)

    for indice, cadastro in enumerate(cadastros, start=1):
        situacao, mensagem = _processar_um(
            cadastro, database, validar_rosto, pular_existentes
        )

        if situacao == "sucesso":
            resultado.sucessos += 1
        elif situacao == "ignorado":
            resultado.ignorados += 1
        else:
            resultado.erros += 1
            resultado.mensagens.append(f"{cadastro.id} · {cadastro.nome}: {mensagem}")

        if progresso:
            progresso(indice, total, cadastro, situacao)

    return resultado


def _processar_um(cadastro, database, validar_rosto, pular_existentes):
    try:
        if pular_existentes and database.buscar_usuario(cadastro.id):
            return "ignorado", "já cadastrado"

        encoding_serializado = None
        caminho_imagem = None

        if cadastro.tem_foto:
            if validar_rosto:
                encoding = extrair_encoding(cadastro.foto)
                if encoding is None:
                    return "erro", "nenhum rosto detectado na foto"
                encoding_serializado = serialize_encoding(encoding)
            caminho_imagem = copiar_foto(cadastro.id, cadastro.foto)
        elif validar_rosto:
            return "erro", "sem foto vinculada"

        gravado = database.adicionar_usuario(
            usuario_id=cadastro.id,
            nome=cadastro.nome,
            grupo=cadastro.grupo,
            telefone=cadastro.telefone,
            encoding=encoding_serializado,
            imagem_path=caminho_imagem,
        )
        if not gravado:
            return "erro", "falha ao gravar no banco"
        return "sucesso", ""
    except Exception as e:
        return "erro", str(e)


def escrever_modelo(caminho=None):
    """Grava o CSV de exemplo usado como ponto de partida."""
    caminho = caminho or (config.TEMPLATES_DIR / "template_cadastro_lote.csv")
    config.TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    linhas = [
        "id,nome,grupo,telefone,foto",
        ",João Silva,TI,11999999999,fotos/joao.jpg",
        "TSU_10001,Maria Santos,RH,11888888888,fotos/maria.jpg",
        ",Pedro Costa,Vendas,11777777777,fotos/pedro.jpg",
    ]
    with open(caminho, "w", encoding="utf-8", newline="") as arquivo:
        arquivo.write("\n".join(linhas) + "\n")
    return str(caminho)
