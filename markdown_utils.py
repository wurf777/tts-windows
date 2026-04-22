import re
import html

def process_markdown(text: str, voice_name: str):
    """
    Parses markdown and returns:
    (clean_text, ssml_text, formatting_tags)
    """
    lang = "-".join(voice_name.split("-")[:2]) if "-" in voice_name else "sv-SE"
    
    display_text = ""
    ssml_parts = []
    format_tags = []
    
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
            ssml_parts.append(f"<s>{html.escape(content)}</s><break time='500ms'/>")
            continue

        # Handle Inline styles (Bold/Italic)
        clean_line = ""
        ssml_line = ""
        last_pos = 0
        
        # Matches **bold**, __bold__, *italic*, _italic_
        pattern = re.compile(r"(\*\*|__)(.*?)\1|(\*|_)(.*?)\3")
        
        for match in pattern.finditer(line):
            # Text before the match
            pre = line[last_pos:match.start()]
            clean_line += pre
            ssml_line += html.escape(pre)
            
            tag_start = len(display_text) + len(clean_line)
            
            if match.group(1): # Bold
                content = match.group(2)
                clean_line += content
                ssml_line += f"<emphasis level='strong'>{html.escape(content)}</emphasis>"
                format_tags.append(("bold", tag_start, tag_start + len(content)))
            else: # Italic
                content = match.group(4)
                clean_line += content
                ssml_line += f"<emphasis level='moderate'>{html.escape(content)}</emphasis>"
                format_tags.append(("italic", tag_start, tag_start + len(content)))
            
            last_pos = match.end()
        
        # Remainder of line
        post = line[last_pos:]
        clean_line += post
        ssml_line += html.escape(post)
        
        display_text += clean_line + "\n"
        ssml_parts.append(ssml_line)

    ssml_body = " ".join(ssml_parts)
    ssml = (
        f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
        f"xmlns:mstts='http://www.w3.org/2001/mstts' xml:lang='{lang}'>"
        f"<voice name='{voice_name}'>"
        f"{ssml_body}"
        f"</voice></speak>"
    )
    
    return display_text.strip(), ssml, format_tags
