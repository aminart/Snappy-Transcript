from __future__ import annotations

import html
import json
import mimetypes
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import streamlit as st

from models.transcript import TranscriptSegment
from utils.export import timestamp


class _RangeFileHandler(BaseHTTPRequestHandler):
    server_version = "AudioTranscriberLocalMedia/1.0"

    def log_message(self, format, *args):
        return

    def do_GET(self):
        server = self.server
        parsed = urlparse(self.path)
        prefix = f"/{server.token}/"
        if not parsed.path.startswith(prefix):
            self.send_error(404)
            return
        name = unquote(parsed.path[len(prefix):])
        path = server.files.get(name)
        if path is None or not path.is_file():
            self.send_error(404)
            return

        size = path.stat().st_size
        start, end = 0, size - 1
        status = 200
        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            try:
                spec = range_header[6:].split(",", 1)[0]
                left, right = spec.split("-", 1)
                if left:
                    start = int(left)
                    end = int(right) if right else size - 1
                else:
                    suffix = int(right)
                    start = max(0, size - suffix)
                end = min(end, size - 1)
                if start < 0 or start > end:
                    raise ValueError
                status = 206
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "audio/wav")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with path.open("rb") as fh:
                fh.seek(start)
                remaining = length
                while remaining:
                    chunk = fh.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


class _MediaServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _RangeFileHandler)
        self.token = secrets.token_urlsafe(18)
        self.files: dict[str, Path] = {}
        self.lock = threading.Lock()

    def register(self, path: Path) -> str:
        path = path.resolve()
        key = secrets.token_urlsafe(12) + path.suffix.lower()
        with self.lock:
            self.files[key] = path
        return f"http://127.0.0.1:{self.server_port}/{self.token}/{key}"


_MEDIA_SERVER: _MediaServer | None = None
_MEDIA_LOCK = threading.Lock()


def _media_url(path: Path) -> str:
    global _MEDIA_SERVER
    with _MEDIA_LOCK:
        if _MEDIA_SERVER is None:
            _MEDIA_SERVER = _MediaServer()
            threading.Thread(target=_MEDIA_SERVER.serve_forever, name="local-media-server", daemon=True).start()
        return _MEDIA_SERVER.register(path)


def render_sync_player(wav_path: str | Path, segments: list[TranscriptSegment], height: int = 520) -> None:
    """Synchronized player without embedding WAV bytes in the Streamlit WebSocket.

    The WAV is exposed only on 127.0.0.1 through a tokenized local HTTP endpoint
    with Range support. This keeps long recordings out of Streamlit messages while
    preserving seeking and word-level highlighting.
    """
    path = Path(wav_path)
    if not path.is_file():
        st.warning(f"Player synchronisé indisponible : WAV introuvable ({path}).")
        return

    audio_url = _media_url(path)
    payload = []
    rows = []
    word_count = 0
    for i, s in enumerate(segments):
        words = []
        word_html = []
        for j, w in enumerate(s.words):
            words.append({"start": float(w.start), "end": float(max(w.end, w.start + .03))})
            word_html.append(f'<span class="word" data-word="{j}">{html.escape(w.text)}</span>')
            word_count += 1
        payload.append({"start": float(s.start), "end": float(max(s.end, s.start + .05)), "words": words})
        speaker = f'<span class="speaker">{html.escape(s.speaker)}</span>' if s.speaker else ""
        body = " ".join(word_html) if word_html else html.escape(s.text)
        rows.append(
            f'<button class="segment" data-index="{i}" data-start="{float(s.start):.3f}" type="button">'
            f'<span class="time">{timestamp(s.start)}</span><span class="body">{speaker}'
            f'<span class="text">{body}</span></span></button>'
        )

    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    safe_url = html.escape(audio_url, quote=True)
    doc = f'''<!doctype html><html><head><meta charset="utf-8"><style>
:root{{color-scheme:light dark;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
body{{margin:0;background:transparent;color:inherit}}.player{{position:sticky;top:0;z-index:3;padding:4px 0 12px;background:Canvas}}
audio{{width:100%}}.hint{{font-size:12px;opacity:.68;margin:6px 2px 0}}.transcript{{max-height:390px;overflow:auto;padding:4px 2px 10px;scroll-behavior:smooth}}
.segment{{display:grid;grid-template-columns:82px 1fr;width:100%;border:0;border-left:3px solid transparent;background:transparent;color:inherit;text-align:left;padding:8px 10px;cursor:pointer;border-radius:6px}}
.segment:hover{{background:color-mix(in srgb, CanvasText 7%, transparent)}}.segment.active{{background:color-mix(in srgb, Highlight 14%, transparent);border-left-color:Highlight}}
.time{{font:12px ui-monospace,SFMono-Regular,Consolas,monospace;opacity:.58;padding-top:3px}}.speaker{{display:inline-block;font-size:11px;font-weight:700;margin-right:8px;padding:2px 6px;border-radius:999px;background:color-mix(in srgb, Highlight 18%, transparent)}}
.word{{display:inline;border-radius:4px;padding:1px 2px;margin:0 -1px;transition:background .08s,color .08s}}.word.active-word{{background:Highlight;color:HighlightText;box-shadow:0 0 0 2px color-mix(in srgb, Highlight 35%, transparent)}}
</style></head><body><div class="player"><audio id="audio" controls preload="metadata" src="{safe_url}"></audio>
<div class="hint">Clique sur une phrase pour naviguer · surbrillance du segment et du mot courant · {word_count} mots horodatés</div></div>
<div class="transcript">{''.join(rows)}</div><script>
const segments={data};const audio=document.getElementById('audio');const nodes=Array.from(document.querySelectorAll('.segment'));let active=-1,activeWord=null;
function segAt(t){{let lo=0,hi=segments.length-1,best=-1;while(lo<=hi){{let m=(lo+hi)>>1;if(segments[m].start<=t){{best=m;lo=m+1}}else hi=m-1}}if(best<0)return -1;let s=segments[best],next=best+1<segments.length?segments[best+1].start:s.end;return t<Math.max(s.end,next)?best:-1}}
function sync(){{let t=audio.currentTime||0,idx=segAt(t);if(idx!==active){{if(active>=0&&nodes[active])nodes[active].classList.remove('active');active=idx;if(active>=0&&nodes[active]){{nodes[active].classList.add('active');nodes[active].scrollIntoView({{behavior:'smooth',block:'nearest'}})}}}}if(activeWord)activeWord.classList.remove('active-word');activeWord=null;if(active>=0){{let ws=segments[active].words||[];for(let j=0;j<ws.length;j++){{if(t>=ws[j].start&&t<ws[j].end){{activeWord=nodes[active].querySelector(`[data-word="${{j}}"]`);if(activeWord)activeWord.classList.add('active-word');break}}}}}}}}
nodes.forEach(n=>n.addEventListener('click',()=>{{audio.currentTime=Number(n.dataset.start||0);audio.play().catch(()=>{{}});sync()}}));audio.addEventListener('timeupdate',sync);audio.addEventListener('seeked',sync);audio.addEventListener('play',sync);sync();</script></body></html>'''
    st.iframe(doc, height=height)
