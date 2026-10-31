# Client-Positionskorrektur 1.0.4 / Client position correction

Start und ruhige sitzende Fahrt vorwärts/rückwärts mit 1.0.4 vom Nutzer am 31.10.2026 bestätigt. / The user confirms startup and smooth seated forward/reverse driving with 1.0.4 on 2026-10-31.

Funktionsumfang, Grenzen, Varianten und Installation: [übergeordnete Dokumentation](../README.md).

`build.py` baut ausschließlich aus vorhandenem JDK 25, Create und passenden NeoForge-Clientbibliotheken. Parameter: `--libraries`, `--jdk`, `--create`, `--annotations`, `--output-dir`. Es lädt nichts herunter. Für zwei unabhängige Ausgabeverzeichnisse gegen Original und bekannte Iris-Variante bauen; die JARs müssen bytegleich sein.

`verify.py` prüft zwei Builds, die gebauten Helfer/Mixin-Wrapper und den Konflikt anhand tatsächlicher Minecraft-Methodenkörper. Parameter: `--first-build`, `--second-build`, `--libraries`, `--jdk`, `--output-dir`. Die einfachen API-Stellvertreter prüfen die Auswahlgrenzen; der ASM-Teil liest echte Minecraft-26.3-Methoden aus der bereits vorhandenen gepatchten Clientdatei. Dies ersetzt keinen vollständigen Mixin-Spielstart oder eine echte Zugfahrt.

Build from cached matching libraries using `build.py`; verify two output directories using `verify.py` with the parameters above. No dependency is downloaded. API substitutes exercise the built gates/wrappers; the ASM fixture retains actual 26.3 movement/camera method bodies. This does not replace a complete game/Mixin launch or actual driving acceptance.

Own code: MIT. [NOTICE](NOTICE), [file checksums](../README.md#dateien--files).
