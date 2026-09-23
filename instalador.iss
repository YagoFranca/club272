; Instalador do 272 Club — Inno Setup 6
;
; Compilar:  ISCC.exe instalador.iss
; Exige que `dist\272Club` já exista (rode `python empacotar.py` antes).

#define Nome "272 Club"
#define Versao "4.0.0"
#define Publicador "272 Club"
#define Executavel "272Club.exe"

[Setup]
AppId={{B7E4A1C2-5D3F-4A8B-9E2C-272C1UB40000}
AppName={#Nome}
AppVersion={#Versao}
AppPublisher={#Publicador}
DefaultDirName={autopf}\272Club
DefaultGroupName={#Nome}
OutputDir=dist
OutputBaseFilename=272Club-{#Versao}-instalador
SetupIconFile=club272\assets\272club.ico
UninstallDisplayIcon={app}\{#Executavel}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; O programa grava em %LOCALAPPDATA%, não na pasta de instalação, então não
; precisa de privilégio de administrador para funcionar depois de instalado.
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
; ~450 MB descompactados
ExtraDiskSpaceRequired=471859200

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; \
    GroupDescription: "Atalhos:"

[Files]
Source: "dist\272Club\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#Nome}"; Filename: "{app}\{#Executavel}"
Name: "{group}\Verificar instalação"; Filename: "{app}\{#Executavel}"; \
    Parameters: "--verificar"; \
    Comment: "Checa câmera, modelos e permissões, e abre um relatório"
Name: "{group}\Desinstalar {#Nome}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#Nome}"; Filename: "{app}\{#Executavel}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#Executavel}"; Description: "Abrir o {#Nome} agora"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Só o que o programa gerou dentro da pasta de instalação. Os dados do
; usuário ficam em %LOCALAPPDATA%\272Club e são preservados de propósito:
; é lá que estão o banco, os rostos e as fotos.
Type: filesandordirs; Name: "{app}\_internal"

[Messages]
brazilianportuguese.FinishedLabel=A instalação do [name] foi concluída.%n%nOs dados (banco, fotos e backups) ficam em %LOCALAPPDATA%\272Club e não são removidos ao desinstalar.
