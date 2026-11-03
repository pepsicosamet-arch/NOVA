; NOVA kurulum betiği — Inno Setup 6
#define AppName "NOVA"
#define AppVersion "1.4.0"
#define AppPublisher "Samet Şahin"
#define AppURL "https://github.com/pepsicosamet-arch/nova"

[Setup]
AppId={{6E0B7A51-3C2D-4F8E-9A41-5A7E2B0C9D17}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL=https://www.instagram.com/xsametsahinx/
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\Output
OutputBaseFilename=NOVA-{#AppVersion}-Windows-Setup
SetupIconFile=..\assets\nova.ico
UninstallDisplayIcon={app}\NOVA.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=NOVA kişisel asistan
VersionInfoCopyright=© 2026 Samet Şahin

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "Windows açılınca NOVA'yı başlat"; GroupDescription: "Diğer:"; Flags: unchecked

[Files]
Source: "..\dist\NOVA\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\NOVA.exe"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\NOVA.exe"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\NOVA.exe"; Tasks: autostart

[Run]
Filename: "{app}\NOVA.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall
