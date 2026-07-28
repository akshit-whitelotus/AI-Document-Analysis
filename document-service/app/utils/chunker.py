from shared.config.settings import settings

SEPARATORS=["\n\n","\n",". "," "]

def chunk_text(text:str,chunk_size:int=settings.CHUNK_SIZE,chunk_overlap:int=settings.CHUNK_OVERLAP)-> list[str]:
    text=text.strip()
    if not text:
        return []
    chunks= _split(text,chunk_size)
    if chunk_overlap <=0 or len(chunks) <=1:
        return chunks

    overlapped:list[str] = []
    for i,chunk in enumerate(chunks):
        if i ==0:
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
            parts=text.split(sep)
            break
    else:
        parts=list(text)

    chunks: list[str] =[]
    current=""
    for part in parts:
        candidate=current +(sep if current else "") + part
        if len(candidate) <=chunk_size:
            current=candidate
        else:
            if current:
                chunks.append(current)
            current=part
    if current:
        chunks.append(current)

    final:list[str] =[]
    for c in chunks:
        if len(c) > chunk_size:
            final.extend(_split(c,chunk_size))
        else:
            final.append(c)
    return final
