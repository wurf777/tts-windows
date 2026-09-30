# TTS-motor: "piper" (lokal, standard) eller "azure" (premium)
TTS_PROVIDER = "piper"

# Piper-modell, relativt till appens mapp. Ladda ned sv_SE-nst-medium
# och lägg både .onnx- och .onnx.json-filen i denna mapp.
PIPER_MODEL_PATH = "models/sv_SE-nst-medium.onnx"

# Azure Speech Service (behövs bara när TTS_PROVIDER = "azure")
AZURE_SPEECH_KEY = "your-key-here"
AZURE_SPEECH_REGION = "swedencentral"
AZURE_VOICE_NAME = "sv-SE-MattiasNeural"

# Hotkeys (keyboard library format: "ctrl+alt+s", "ctrl+shift+r", etc.)
HOTKEY_READ_SELECTED = "ctrl+alt+s"
HOTKEY_SCREENSHOT_OCR = "ctrl+alt+o"
HOTKEY_OPEN_TEXT_INPUT = "ctrl+alt+v"

# Language: "sv" for Swedish, "en" for English
# Controls both OCR language and which voice list is shown in settings
LANGUAGE = "sv"

# Milliseconds to wait after simulating Ctrl+C before reading clipboard
# Increase if selected text is often empty (slow apps like browsers may need 200-300)
CLIPBOARD_DELAY_MS = 150

# Optional local link opened from the tray menu. Keep personal budget URLs in config.py only.
AZURE_COST_URL = "https://portal.azure.com/#view/Microsoft_Azure_CostManagement/Menu/~/costanalysis"
