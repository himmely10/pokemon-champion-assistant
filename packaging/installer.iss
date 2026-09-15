#ifndef AppVersion
  #define AppVersion "0.3.0"
#endif
#define AppName "Pokemon Champion Assistant"

[Setup]
AppId={{DD387A7B-6259-48D4-93BC-71B6D64B4100}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Pokemon Champion Assistant contributors
DefaultDirName={localappdata}\Programs\PokemonChampionAssistant
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\artifacts\release
OutputBaseFilename=PokemonChampionAssistant-{#AppVersion}-windows-x64-Setup
SetupIconFile=..\assets\branding\app.ico
UninstallDisplayIcon={app}\PokemonChampionAssistant.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes
LicenseFile=..\THIRD_PARTY_NOTICES.md

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\artifacts\dist\PokemonChampionAssistant\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\PokemonChampionAssistant.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\PokemonChampionAssistant.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PokemonChampionAssistant.exe"; Description: "Launch Pokemon Champion Assistant"; Flags: nowait postinstall skipifsilent

; Personal data is outside {app}; uninstall deliberately has no user-data deletion.
