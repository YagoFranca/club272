"""
Design system do 272 Club.

Fonte única de verdade para cor, tipografia, espaçamento e raio de canto.
Nenhuma tela deve escrever um `#rrggbb` literal — se falta um tom aqui, ele é
adicionado aqui.

A paleta é derivada da própria logo. Analisando os pixels dentro do recorte
circular, cerca de 70% dos tons com saturação relevante caem no matiz 20°
(cobre/terracota), com um vermelho puro (matiz 0°) num detalhe menor. Daí:

  - fundo em preto quente, com fundo marrom, em vez do azul-noite anterior;
  - acento em cobre, o tom que domina a arte;
  - vermelho reservado para perigo, que é o papel que ele já cumpre na logo.

Todos os pares de texto sobre fundo foram verificados contra o WCAG AA
(4.5:1 para texto normal, 3:1 para texto de apoio).
"""


class Cor:
    """Papéis de cor. Escolha pelo papel, não pelo tom."""

    # Planos de fundo, do mais fundo ao mais elevado. Neutros quentes: mantêm
    # a temperatura da logo sem competir com o acento.
    FUNDO = "#14100E"
    SUPERFICIE = "#1E1815"
    SUPERFICIE_ALTA = "#2A211C"
    SUPERFICIE_HOVER = "#372B23"

    BORDA = "#493829"
    BORDA_SUAVE = "#2E241E"

    # Texto, em ordem decrescente de ênfase. Brancos levemente quentes para
    # não destoar do fundo.
    TEXTO = "#F5EDE7"
    TEXTO_SECUNDARIO = "#C4AD99"
    TEXTO_APAGADO = "#8F7A68"
    TEXTO_SOBRE_ACENTO = "#14100E"

    # Marca: o cobre da logo.
    ACENTO = "#E29464"
    ACENTO_HOVER = "#EFA97C"

    # Estados. Verde e âmbar puxados para o quente, para conviverem com o
    # cobre em vez de brigar com ele.
    SUCESSO = "#96A85C"
    SUCESSO_HOVER = "#83944D"
    ALERTA = "#E0A344"
    ALERTA_HOVER = "#C88C32"
    PERIGO = "#E05A47"
    PERIGO_HOVER = "#C74534"
    NEUTRO = "#5A4638"
    NEUTRO_HOVER = "#48372B"

    # Fundos tênues para badges e faixas de destaque.
    ACENTO_FUNDO = "#3A2416"
    SUCESSO_FUNDO = "#232815"
    ALERTA_FUNDO = "#33260E"
    PERIGO_FUNDO = "#2B1310"


class Fonte:
    """Escala tipográfica. Tuplas prontas para `font=`."""

    FAMILIA = "Segoe UI"
    MONO = "Consolas"

    # Fontes de ícone do Windows, em ordem de preferência. Emoji não servem
    # aqui: o Tk não desenha emoji colorido no Windows, e o glifo sai como um
    # borrão monocromático — foi o que aconteceu com os ícones de estado
    # vazio. Estas são fontes de ícone monocromáticas, feitas para interface.
    ICONES = ("Segoe Fluent Icons", "Segoe MDL2 Assets")

    DISPLAY = (FAMILIA, 26, "bold")
    TITULO = (FAMILIA, 19, "bold")
    SUBTITULO = (FAMILIA, 15, "bold")
    CORPO_FORTE = (FAMILIA, 13, "bold")
    CORPO = (FAMILIA, 13)
    PEQUENO = (FAMILIA, 11)
    MICRO = (FAMILIA, 10)
    CODIGO = (MONO, 12)


class Espaco:
    """Escala de espaçamento (múltiplos de 4)."""

    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 24
    XXL = 32
    XXXL = 48


class Raio:
    """Raio de canto."""

    SM = 6
    MD = 10
    LG = 14
    PILULA = 999
