# TTS Windows

En Windows-app som läser upp text med Azure Speech SDK. Kör i bakgrunden som en systemtray-ikon och aktiveras via snabbtangenter eller högerklicksmenyn.

## Funktioner

- **Systemtray-ikon** — appen kör alltid i bakgrunden med en högerklicksmeny
- **Läs markerad text** — markera text var som helst och tryck på snabbtangenten
- **Screenshot OCR** — rita en ruta på skärmen, texten känns igen och läses upp
- **Textinmatningsfönster** — klistra in eller skriv text manuellt och läs upp
- **Uppspelningsfönster** — visar texten och highlightar aktuellt ord i realtid
- **Avbryt-knapp** — stoppar uppläsningen omedelbart
- **Inställningsfönster** — byt röst, snabbtangenter och språk direkt i appen

## Krav

- Windows 10/11
- Python 3.10+
- Azure Speech Service-nyckel
- Administratörsrättigheter (krävs av `keyboard`-biblioteket för globala snabbtangenter)

## Installation

```bash
git clone https://github.com/wurf777/tts-windows.git
cd tts-windows
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Kopiera sedan konfigurationsfilen och fyll i dina uppgifter:

```bash
# Git Bash / macOS / Linux:
cp config.example.py config.py

# Windows cmd:
copy config.example.py config.py
```

Redigera `config.py`:

```python
AZURE_SPEECH_KEY = "din-nyckel-här"
AZURE_SPEECH_REGION = "swedencentral"
AZURE_VOICE_NAME = "sv-SE-MattiasNeural"
```

## Användning

Starta appen **som administratör** (krävs för globala snabbtangenter):

```bash
python main.py
```

Appen hamnar i systemtray-fältet. Högerklicka på ikonen för menyn.

### Snabbtangenter (standard)

| Tangent | Funktion |
|---|---|
| `Ctrl+Alt+S` | Läs markerad text |
| `Ctrl+Alt+O` | Screenshot OCR |

Snabbtangenterna kan ändras i `config.py` eller via inställningsfönstret i tray-menyn.

## Konfiguration

Alla inställningar finns i `config.py` (checkas inte in i git):

| Inställning | Beskrivning | Standardvärde |
|---|---|---|
| `AZURE_SPEECH_KEY` | Azure-nyckel | — |
| `AZURE_SPEECH_REGION` | Azure-region | `swedencentral` |
| `AZURE_VOICE_NAME` | Röst (Neural TTS) | `sv-SE-MattiasNeural` |
| `HOTKEY_READ_SELECTED` | Snabbtangent för text | `ctrl+alt+s` |
| `HOTKEY_SCREENSHOT_OCR` | Snabbtangent för OCR | `ctrl+alt+o` |
| `LANGUAGE` | Språk för OCR | `sv` |
| `CLIPBOARD_DELAY_MS` | Fördröjning efter Ctrl+C | `150` |

## Arkitektur

```
main.py              — entrypoint, tkinter mainloop, event-koordinator
tray.py              — systemtray-ikon (pystray, daemon-tråd)
hotkeys.py           — globala snabbtangenter (keyboard, daemon-tråd)
tts_engine.py        — Azure Speech TTS, word boundary-events
playback_window.py   — uppspelningsfönster med ord-highlighting
screenshot.py        — skärmdumpsöverlägg + Windows OCR (winrt)
settings_window.py   — inställningsfönster för röst, tangenter och språk
text_input_window.py — manuellt textinmatningsfönster
config_loader.py     — läser config.py dynamiskt från disk (stöd för exe och skript)
config.py            — lokal konfiguration (ignoreras av git)
config.example.py    — mall för config.py
```

### Trådmodell

- **Main thread** — tkinter mainloop + all UI
- **pystray-tråd** — tray-ikon (daemon)
- **keyboard-tråd** — globala snabbtangenter (daemon)
- **TTS-tråd** — Azure-syntes per uppläsning (daemon)
- **OCR-tråd** — Windows OCR per screenshot (daemon)

TTS- och OCR-trådar kommunicerar med main thread via en `queue.Queue` som pollas var 50 ms.

## Beroenden

| Paket | Syfte |
|---|---|
| `azure-cognitiveservices-speech` | Neural TTS + word boundary-events |
| `pystray` | Systemtray-ikon |
| `keyboard` | Globala snabbtangenter |
| `Pillow` | Bildhantering för screenshot |
| `pyperclip` | Clipboard-åtkomst |
| `winsdk` | Windows Runtime OCR |
| `numpy` | Bildkonvertering för OCR |
