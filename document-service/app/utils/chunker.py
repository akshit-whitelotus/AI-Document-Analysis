import re

from shared.config.settings import settings

SEPARATORS=["\n\n","\n",". "," "]

def chunk_text(text:str,chunk_size:int=settings.CHUNK_SIZE,chunk_overlap:int=settings.CHUNK_OVERLAP) -> list[str]:
    text=text.strip()
    if not text:
        return []
    chunks= _split(text,chunk_size)
    if chunk_overlap <=0 or len(chunks) <=1:
        return chunks
    overlapped:list[str] = []
    for i,chunk in enumerate(chunks):
        if i == 0:
            overlapped.append(chunk)
            continue
        prev_tail=chunks[i-1][-chunk_overlap:]
        overlapped.append(prev_tail+chunk)
    return overlapped

def _split(text:str,chunk_size:int) -> list[str]:
    if len(text) <=chunk_size:
        return [text]
    for sep in SEPARATORS:
        if sep in text:
            # Keep the seperator itself as its own token (via a capturing
            # group) instead of str.spilt(), which discards it . Every
            # token - text or seperator - ends up in exactly one output 
            # chunk, so nothing from the original text is ever lost.
            tokens=re.split(f"({re.escape(sep)})",text)
            break
    else:
        tokens=list(text)
    chunks: list[str] =[]
    current=""
    for token in tokens:
        canditate=current+token
        if len(canditate) <=chunk_size:
            current=canditate
        else:
            if current:
                chunks.append(current)
            current=token
    if current:
        chunks.append(current)

    if len(chunks)==1 and chunks[0] ==text:
        # Splitting on the chosen seperator made no progress at all (e.g.
        # a single token - possibly the seperator itself, like "\n\n" when
        # chunk_size==1 - that's already longer than chunk_size on its 
        # own). Recursing further would just regenerate the same string
        # forever, so fall back to a hard fixed-size slice, which always
        # terminates no matter what the input looks like.
        return [text[i:i+chunk_size] for i in range(0,len(text),chunk_size)]
    final:list[str] =[]
    for c in chunks:
        if len(c) > chunk_size:
            final.extend(_split(c,chunk_size))
        else:
            final.append(c)
    return final
