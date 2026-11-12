; Instalador del AgenteUTN (laboratorio Seguridad de TI II - UTN).
;
; Correcciones respecto a la versión original del entregable:
;   - Nombre, editor y versión del instalador.
;   - Icono en el instalador, en los accesos directos y en el desinstalador.
;   - El 7-Zip ya NO se instala en silencio: aparece como componente
;     OPCIONAL desmarcado por defecto en la página de componentes del
;     asistente (el usuario debe marcarlo para instalarlo).
;
; Requiere Inno Setup 6 y 7z-installer-x64.exe en installer/redist/.

#define MyAppName "AgenteUTN"
#define MyAppVersion "2.0"
#define MyAppPublisher "Seguridad de TI II - UTN"
#define MyAppExeName "AgenteUTN.exe"
#define MyAppIco "..\assets\agente.ico"

[Setup]
AppId={{D91C6E72-18B9-4F6B-9B2D-4CD5B9E23810}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\AgenteUTN
DefaultGroupName={#MyAppName}
OutputDir=output
OutputBaseFilename=AgenteUTN_Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
WizardStyle=modern
SetupIconFile={#MyAppIco}
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Types]
Name: "completa"; Description: "Instalación completa (AgenteUTN)"; Flags: iscustom

[Components]
Name: "agente"; Description: "AgenteUTN - Aplicación de diagnóstico"; Types: completa; Flags: fixed
Name: "sevenzip"; Description: "7-Zip - Compresor de archivos (opcional)"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; Flags: unchecked

[Files]
Source: "..\dist\AgenteUTN.exe"; DestDir: "{app}"; Components: agente; Flags: ignoreversion
Source: "redist\7z-installer-x64.exe"; DestDir: "{tmp}"; Components: sevenzip; Flags: deleteafterinstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Components: agente
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Components: agente; Tasks: desktopicon

[Run]
Filename: "{tmp}\7z-installer-x64.exe"; Parameters: "/S"; StatusMsg: "Instalando 7-Zip..."; Components: sevenzip; Flags: waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "Ejecutar AgenteUTN"; Components: agente; Flags: nowait postinstall skipifsilent
