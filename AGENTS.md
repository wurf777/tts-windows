# TTS Windows

Windows text-to-speech app som körs som system tray-ikon. Använder Azure Neural TTS för att läsa text högt med realtids-ordmarkering.

## Funktioner

- Läs markerad text (Ctrl+Alt+S) via clipboard
- Screenshot OCR (Ctrl+Alt+O) - rita region, OCR via Windows Runtime (winsdk)
- Textinmatningsfönster - klistra in/skriv text
- Realtids playback-fönster med ordmarkering
- Inställnings-GUI för röst, API-nyckel, hotkeys, språk (sv/en)

## Arkitektur

- `main.py` - Entrypoint, dold tkinter root, message pump, queue-polling (50ms)
- `tts_engine.py` - Azure TTS worker, thread-safe, word boundary events via queue
- `playback_window.py` - Tkinter Toplevel, text med guldmarkering för aktuellt ord
- `screenshot.py` - Fullskärms-overlay + Pillow screengrab + winsdk OCR (async)
- `config_loader.py` - Löser rätt config.py-sökväg (exe-mapp vs skript-mapp), laddar med exec()
- `settings_window.py` - GUI som skriver direkt till config.py
- `text_input_window.py` - Manuell textinmatning
- `tray.py` - Pystray system tray med kontextmeny
- `hotkeys.py` - Globala hotkeys via keyboard-lib (kräver admin)

## Trådningsmodell

Main thread kör tkinter event loop. Daemon-trådar för pystray, keyboard, TTS och OCR. All IPC via `queue.Queue`, callbacks via `root.after(0, ...)`. Inga direkta UI-anrop från worker-trådar.

## Konfiguration

- `config.py` - Lokala hemligheter (gitignored), skapas utifrån `config.example.py`
- `config_loader.py` - Läser config.py från disk via `exec()` (inte Python-import)
  - Använder `sys.executable`-mappen när appen körs som PyInstaller-exe
  - Använder `__file__`-mappen vid vanlig Python-körning
  - Returnerar `SimpleNamespace` med standardvärden om config.py saknas
- Alla moduler använder `config_loader.load()` — aldrig `import config`
- `config` är explicit exkluderad i `.spec`-filen så den inte buntlas i exe:n

## Bygga exe

Kör alltid med `.venv`-Python, inte system-Python:

```bash
.venv/Scripts/python.exe -m PyInstaller "TTS Windows.spec" --clean
```

Output: `dist/TTS Windows.exe`

**Viktigt:** `config.py` måste ligga i samma mapp som exe-filen (inte inbakad). Kopiera `config.example.py` → `config.py` bredvid exe:n vid första distribution, eller låt användaren fylla i via Inställningar-GUI:t.

## Installerad version hos Christian

Den installerade kopian som Startmeny-genvägen pekar på ligger här:

```text
C:\Program_USB\TTS Windows\TTS Windows.exe
```

Aktiv installerad config ligger bredvid exe:n:

```text
C:\Program_USB\TTS Windows\config.py
```

Vid deploy: bygg först `dist/TTS Windows.exe`, ta backup på befintlig installerad exe med tidsstämpel, kopiera sedan nya exe:n till `C:\Program_USB\TTS Windows\TTS Windows.exe`.

`config.py` är lokal driftdata och innehåller hemligheter. Deploy får inte kopiera över, regenerera eller skriva om installerad `config.py`. Ta en tidsstämplad backup på `C:\Program_USB\TTS Windows\config.py` innan någon configändring. Om användaren uttryckligen ber om configändring: gör bara riktade radändringar för de berörda icke-hemliga nycklarna, skriv aldrig ut API-nyckeln, och kopiera aldrig `dist/config.py`, repo-`config.py` eller `config.example.py` till installerade mappen.

## Språk

Projektet och UI:t är på svenska. Kommunicera på svenska.
