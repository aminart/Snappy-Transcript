from __future__ import annotations
import re
from models.transcript import TranscriptSegment

def _sec(s):
    h,m,rest=s.replace('.',',').split(':'); sec,ms=rest.split(','); return int(h)*3600+int(m)*60+int(sec)+int(ms.ljust(3,'0')[:3])/1000
def parse_srt(text:str):
    blocks=re.split(r'\r?\n\s*\r?\n',text.strip()); out=[]
    for block in blocks:
        lines=block.splitlines()
        ti=next((i for i,x in enumerate(lines) if '-->' in x),None)
        if ti is None:continue
        a,b=[x.strip() for x in lines[ti].split('-->',1)]; body=' '.join(x.strip() for x in lines[ti+1:] if x.strip())
        speaker=None
        m=re.match(r'^(SPEAKER[_ -]?\d+)\s*:\s*(.*)$',body,re.I)
        if m:speaker,body=m.group(1),m.group(2)
        if body:out.append(TranscriptSegment(_sec(a),_sec(b),body,speaker,()))
    if not out:raise ValueError('Aucun segment SRT valide trouvé.')
    return out
