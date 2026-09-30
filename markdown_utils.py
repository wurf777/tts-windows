import re
import html
from address_utils import addresses, SpeechMap

def process_markdown(text: str, voice_name: str, address_mode="short", include_mapping=False):
    """
    Parses markdown and returns:
    (clean_text, ssml_text, formatting_tags)
    """
    lang = "-".join(voice_name.split("-")[:2]) if "-" in voice_name else "sv-SE"
    
    display_text = ""
    ssml_parts = []
    format_tags = []
    speech_map = SpeechMap()

    def render(content, offset):
        parts = []
        last = 0
        for start, end, kind in addresses(content):
            plain = content[last:start]
            parts.append(html.escape(plain))
            speech_map.append(plain, offset + last)
            if address_mode == "read":
                spoken = content[start:end]
                speech_map.append(spoken, offset + start)
            else:
                english = lang.startswith("en")
                spoken = ("email address available" if english else "e-postadress finns") if kind == "email" else ("link available" if english else "länk finns")
                if address_mode == "skip":
                    spoken = " "
                speech_map.append(spoken, offset + start, offset + end)
            parts.append(html.escape(spoken))
            last = end
        parts.append(html.escape(content[last:]))
        speech_map.append(content[last:], offset + last)
        return "".join(parts)
    
    lines = text.splitlines()
    for line in lines:
        # Handle Headings
        heading_match = re.match(r"^(#{1,6})\s*(.*)$", line)
        if heading_match:
            content = heading_match.group(2).strip()
            start_idx = len(display_text)
            display_text += content + "\n"
            format_tags.append(("heading", start_idx, len(display_text) - 1))
            
            # SSML: wrap in sentence and add a pause
            ssml_parts.append(f"<s>{render(content, start_idx)}</s><break time='500ms'/>")
            speech_map.append(" ", len(display_text) - 1)
            continue

        # Handle Inline styles (Bold/Italic)
        clean_line = ""
        ssml_line = ""
        last_pos = 0
        
        # Matches **bold**, __bold__, *italic*, _italic_
        pattern = re.compile(r"(\*\*|__)(.*?)\1|(\*|_)(.*?)\3")
        
        address_spans = list(addresses(line))
        for match in pattern.finditer(line):
            # Underscores within URLs/email addresses are literal characters.
            if any(start <= match.start() < end for start, end, _ in address_spans):
                continue
            # Text before the match
            pre = line[last_pos:match.start()]
            ssml_line += render(pre, len(display_text) + len(clean_line))
            clean_line += pre
            
            tag_start = len(display_text) + len(clean_line)
            
            if match.group(1): # Bold
                content = match.group(2)
                clean_line += content
                ssml_line += f"<emphasis level='strong'>{render(content, tag_start)}</emphasis>"
                format_tags.append(("bold", tag_start, tag_start + len(content)))
            else: # Italic
                content = match.group(4)
                clean_line += content
                ssml_line += f"<emphasis level='moderate'>{render(content, tag_start)}</emphasis>"
                format_tags.append(("italic", tag_start, tag_start + len(content)))
            
            last_pos = match.end()
        
        # Remainder of line
        post = line[last_pos:]
        ssml_line += render(post, len(display_text) + len(clean_line))
        clean_line += post
        
        display_text += clean_line + "\n"
        ssml_parts.append(ssml_line)
        speech_map.append(" ", len(display_text) - 1)

    ssml_body = " ".join(ssml_parts)
    ssml = (
        f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
        f"xmlns:mstts='http://www.w3.org/2001/mstts' xml:lang='{lang}'>"
        f"<voice name='{voice_name}'>"
        f"{ssml_body}"
        f"</voice></speak>"
    )
    
    result = (display_text.rstrip("\n"), ssml, format_tags)
    return (*result, speech_map) if include_mapping else result
