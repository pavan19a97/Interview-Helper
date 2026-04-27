import asyncio
import json
import os
import queue as sync_queue
import sys
import time

import pyaudiowpatch as pyaudio
import websockets
from dotenv import load_dotenv

load_dotenv()

_DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
if not _DEEPGRAM_API_KEY:
    print("[audio_engine] ERROR: DEEPGRAM_API_KEY is not set in .env — transcription will fail", flush=True)
_CHUNK = 2048

# Proactively reconnect after this many seconds to avoid Deepgram's ~10-min session limit
_MAX_CONN_SECS = 480  # 8 minutes

from core.transcript_postprocess import get_dg_keyterms_qs, postprocess_transcript

print("[audio_engine] Initializing...", flush=True)

# Module-level flags so main.py can signal both engines to clear their buffers
_clear_loopback_buffer = False
_clear_mic_buffer = False


def clear_transcript_buffers():
    """Called by main.py on mute to flush any in-flight partial transcript."""
    global _clear_loopback_buffer, _clear_mic_buffer
    _clear_loopback_buffer = True
    _clear_mic_buffer = True


def _find_mic_device(pa: pyaudio.PyAudio):
    """Return (device_index, sample_rate, channels) for the default WASAPI mic input."""
    try:
        wasapi_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    except OSError:
        raise RuntimeError("WASAPI not available on this system.")

    default_in_idx = wasapi_info.get("defaultInputDevice", -1)
    if default_in_idx == -1:
        raise RuntimeError("No default WASAPI input device found.")

    info = pa.get_device_info_by_index(default_in_idx)
    ch = min(int(info["maxInputChannels"]), 2) or 1
    print(f"[mic_engine] Default mic: {info['name']}, {info['defaultSampleRate']}Hz, {ch}ch", flush=True)
    return default_in_idx, int(info["defaultSampleRate"]), ch


def _find_loopback_device(pa: pyaudio.PyAudio):
    """Return (device_index, sample_rate, channels) for the default WASAPI loopback."""
    print("[audio_engine] Searching for loopback device...", flush=True)
    try:
        wasapi_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    except OSError:
        raise RuntimeError("WASAPI not available on this system.")

    default_out_idx = wasapi_info["defaultOutputDevice"]
    device_info = pa.get_device_info_by_index(default_out_idx)
    print(f"[audio_engine] Default output: {device_info['name']}", flush=True)

    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info.get("isLoopbackDevice") and info["name"].startswith(device_info["name"]):
            ch = int(info["maxInputChannels"]) or 1
            print(f"[audio_engine] Found loopback: device {i}, {info['defaultSampleRate']}Hz, {ch}ch", flush=True)
            return i, int(info["defaultSampleRate"]), ch

    raise RuntimeError("No WASAPI loopback device found for the default output.")


async def run() -> None:
    import sys
    from core.llm_router import stream_answer
    _main = sys.modules['__main__']
    broadcast = _main.broadcast

    print("[audio_engine] Opening audio stream...", flush=True)
    pa = pyaudio.PyAudio()
    try:
        device_idx, sample_rate, channels = _find_loopback_device(pa)
    except Exception as exc:
        pa.terminate()
        print(f"[audio_engine] ERROR - device error: {exc}", flush=True)
        return

    audio_queue: sync_queue.Queue = sync_queue.Queue(maxsize=200)
    _drop_count = [0]

    def _audio_callback(in_data, frame_count, time_info, status):
        try:
            audio_queue.put_nowait(in_data)
        except sync_queue.Full:
            _drop_count[0] += 1
            if _drop_count[0] % 50 == 1:
                print(f"[audio_engine] ! Audio queue full — {_drop_count[0]} chunks dropped", flush=True)
        return (None, pyaudio.paContinue)

    try:
        print(f"[audio_engine] Opening stream: {sample_rate}Hz, {channels}ch, chunk={_CHUNK}", flush=True)
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=sample_rate,
            input=True,
            input_device_index=device_idx,
            frames_per_buffer=_CHUNK,
            stream_callback=_audio_callback,
        )
        stream.start_stream()
        print(f"[audio_engine] OK Audio stream started successfully", flush=True)
    except Exception as exc:
        pa.terminate()
        print(f"[audio_engine] ERROR - stream open error: {exc}", flush=True)
        return

    print(f"[audio_engine] sample rate: {sample_rate}Hz, channels: {channels}", flush=True)

    async def send_audio(ws, deadline: float):
        """Send audio chunks; raise after deadline to force proactive reconnect."""
        loop = asyncio.get_event_loop()
        while True:
            if time.monotonic() >= deadline:
                raise Exception(f"[audio_engine] Proactive reconnect after {_MAX_CONN_SECS}s")
            try:
                data = await asyncio.wait_for(
                    loop.run_in_executor(None, audio_queue.get),
                    timeout=5.0
                )
                await ws.send(data)
            except asyncio.TimeoutError:
                # No audio for 5s — send KeepAlive to prevent Deepgram net0001 timeout
                await ws.send(json.dumps({"type": "KeepAlive"}))

    transcript_buffer = []

    async def receive_results(ws, active_uend):
        global _clear_loopback_buffer
        async for message in ws:
            if _clear_loopback_buffer:
                transcript_buffer.clear()
                _clear_loopback_buffer = False

            try:
                result = json.loads(message)
            except json.JSONDecodeError:
                continue

            msg_type = result.get("type", "Results")

            # Deepgram sent an error — log and force reconnect
            if msg_type == "Error":
                err = result.get("description") or result.get("error_code") or str(result)
                print(f"[audio_engine] Deepgram error message: {err}", flush=True)
                raise Exception(f"Deepgram error: {err}")

            if msg_type == "UtteranceEnd":
                full_text = " ".join(transcript_buffer).strip()
                transcript_buffer.clear()
                full_text = postprocess_transcript(full_text)
                if not _main.settings.muted and full_text:
                    print(f"[audio_engine] utterance: {full_text}", flush=True)
                    broadcast({"type": "transcript", "text": full_text})
                    # Engine is captured at task-creation time. If the user toggles
                    # engine mid-stream the in-flight task finishes on the OLD engine;
                    # the change takes effect on the next utterance. Intentional —
                    # cancelling mid-stream would lose a partial answer.
                    asyncio.create_task(stream_answer(full_text, _main.settings.engine))
                if _main.settings.utterance_end_ms != active_uend:
                    print(f"[audio_engine] utterance_end_ms changed — reconnecting", flush=True)
                    _working = None  # force fresh URL build with new utterance_end_ms
                    raise Exception("utterance_end_ms changed")
                continue

            if msg_type != "Results":
                continue

            if _main.settings.muted:
                continue

            channel = result.get("channel", {})
            alternatives = channel.get("alternatives", [{}])
            text = alternatives[0].get("transcript", "").strip()
            is_final = result.get("is_final", False)

            if not text:
                continue

            if is_final:
                transcript_buffer.append(text)
                broadcast({"type": "transcript", "text": " ".join(transcript_buffer)})
            else:
                broadcast({"type": "transcript", "text": " ".join(transcript_buffer + [text])})

        # async for exited — Deepgram closed connection server-side; trigger reconnect
        raise Exception("server closed connection")

    _base = "wss://api.deepgram.com/v1/listen"
    _working: tuple | None = None

    def _build_attempts(sr, ch):
        uend = _main.settings.utterance_end_ms
        kw = get_dg_keyterms_qs()
        params = (
            f"model=nova-3&smart_format=true&interim_results=true"
            f"&punctuate=true&numerals=true&filler_words=false&profanity_filter=false"
            f"&endpointing=300"
            f"&encoding=linear16&sample_rate={sr}&channels={ch}&utterance_end_ms={uend}"
            + (f"&{kw}" if kw else "")
        )
        url_tok = _base + "?" + params
        url_key = _base + f"?key={_DEEPGRAM_API_KEY}&" + params
        return [
            (f"Token {sr}Hz/{ch}ch", url_tok, {"Authorization": f"Token {_DEEPGRAM_API_KEY}"}),
            (f"key-query {sr}Hz/{ch}ch", url_key, {}),
        ]

    print("[audio_engine] Starting main loop - connecting to Deepgram...", flush=True)

    while True:
        try:
            if _working and _working[2] == _main.settings.utterance_end_ms:
                attempts = [("reconnect", _working[0], _working[1])]
            else:
                _working = None
                attempts = (
                    _build_attempts(sample_rate, channels)
                    + _build_attempts(16000, 1)
                )

            for desc, conn_url, hdrs in attempts:
                try:
                    print(f"[audio_engine] Attempting connection ({desc})...", flush=True)
                    async with websockets.connect(conn_url, additional_headers=hdrs) as ws:
                        active_uend = _main.settings.utterance_end_ms
                        _working = (conn_url, hdrs, active_uend)
                        transcript_buffer.clear()
                        deadline = time.monotonic() + _MAX_CONN_SECS
                        print(f"[audio_engine] OK Connected to Deepgram ({desc})", flush=True)
                        broadcast({"type": "deepgram_status", "connected": True})
                        await asyncio.gather(
                            send_audio(ws, deadline),
                            receive_results(ws, active_uend),
                        )
                except asyncio.CancelledError:
                    print("[audio_engine] Connection cancelled", flush=True)
                    raise
                except Exception as exc:
                    print(f"[audio_engine] Connection ended ({desc}): {exc}", flush=True)
                    if _working and _working[0] == conn_url:
                        # Was connected, now dropped — show red, retry immediately
                        broadcast({"type": "deepgram_status", "connected": False})
                        break
                    continue
            else:
                # All fresh attempts failed
                _working = None
                print("[audio_engine] ! All connection attempts failed — retrying in 2s", flush=True)
                broadcast({"type": "deepgram_status", "connected": False})
                await asyncio.sleep(2)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            print(f"[audio_engine] ! Unexpected error: {exc} — retrying in 2s", flush=True)
            await asyncio.sleep(2)

    print("[audio_engine] Shutting down audio stream...", flush=True)
    stream.stop_stream()
    stream.close()
    pa.terminate()
    print("[audio_engine] OK Shutdown complete", flush=True)


async def run_mic() -> None:
    """Capture microphone input, transcribe via Deepgram, broadcast as user speech."""
    import sys
    from core.context_manager import get_context
    _main = sys.modules['__main__']
    broadcast = _main.broadcast

    print("[mic_engine] Starting mic capture...", flush=True)
    pa = pyaudio.PyAudio()
    try:
        device_idx, sample_rate, channels = _find_mic_device(pa)
    except Exception as exc:
        pa.terminate()
        print(f"[mic_engine] No mic found, skipping: {exc}", flush=True)
        return

    audio_queue: sync_queue.Queue = sync_queue.Queue(maxsize=200)

    def _audio_callback(in_data, frame_count, time_info, status):
        try:
            audio_queue.put_nowait(in_data)
        except sync_queue.Full:
            pass
        return (None, pyaudio.paContinue)

    try:
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=sample_rate,
            input=True,
            input_device_index=device_idx,
            frames_per_buffer=_CHUNK,
            stream_callback=_audio_callback,
        )
        stream.start_stream()
        print(f"[mic_engine] OK Mic stream started: {sample_rate}Hz, {channels}ch", flush=True)
    except Exception as exc:
        pa.terminate()
        print(f"[mic_engine] ERROR opening mic stream: {exc}", flush=True)
        return

    _base = "wss://api.deepgram.com/v1/listen"
    _working: tuple | None = None

    def _build_attempts(sr, ch):
        uend = _main.settings.utterance_end_ms
        kw = get_dg_keyterms_qs()
        params = (
            f"model=nova-3&smart_format=true&interim_results=true"
            f"&punctuate=true&numerals=true&filler_words=false&profanity_filter=false"
            f"&endpointing=300"
            f"&encoding=linear16&sample_rate={sr}&channels={ch}&utterance_end_ms={uend}"
            + (f"&{kw}" if kw else "")
        )
        url_tok = _base + "?" + params
        url_key = _base + f"?key={_DEEPGRAM_API_KEY}&" + params
        return [
            (f"Token {sr}Hz/{ch}ch", url_tok, {"Authorization": f"Token {_DEEPGRAM_API_KEY}"}),
            (f"key-query {sr}Hz/{ch}ch", url_key, {}),
        ]

    async def send_audio(ws, deadline: float):
        loop = asyncio.get_event_loop()
        while True:
            if time.monotonic() >= deadline:
                raise Exception(f"[mic_engine] Proactive reconnect after {_MAX_CONN_SECS}s")
            try:
                data = await asyncio.wait_for(
                    loop.run_in_executor(None, audio_queue.get), timeout=5.0
                )
                await ws.send(data)
            except asyncio.TimeoutError:
                await ws.send(json.dumps({"type": "KeepAlive"}))

    transcript_buffer = []

    async def receive_results(ws, active_uend):
        global _clear_mic_buffer
        ctx = get_context()
        async for message in ws:
            if _clear_mic_buffer:
                transcript_buffer.clear()
                _clear_mic_buffer = False

            try:
                result = json.loads(message)
            except json.JSONDecodeError:
                continue

            msg_type = result.get("type", "Results")

            if msg_type == "Error":
                err = result.get("description") or result.get("error_code") or str(result)
                print(f"[mic_engine] Deepgram error message: {err}", flush=True)
                raise Exception(f"Deepgram error: {err}")

            if msg_type == "UtteranceEnd":
                full_text = " ".join(transcript_buffer).strip()
                transcript_buffer.clear()
                full_text = postprocess_transcript(full_text)
                if full_text:
                    print(f"[mic_engine] user said: {full_text}", flush=True)
                    ctx.add_user_speech(full_text)
                    broadcast({"type": "user_speech", "text": full_text})
                if _main.settings.utterance_end_ms != active_uend:
                    _working = None  # force fresh URL build with new utterance_end_ms
                    raise Exception("utterance_end_ms changed")
                continue

            if msg_type != "Results":
                continue

            channel = result.get("channel", {})
            alternatives = channel.get("alternatives", [{}])
            text = alternatives[0].get("transcript", "").strip()
            is_final = result.get("is_final", False)

            if not text:
                continue

            if is_final:
                transcript_buffer.append(text)
                broadcast({"type": "mic_transcript", "text": " ".join(transcript_buffer)})
            else:
                broadcast({"type": "mic_transcript", "text": " ".join(transcript_buffer + [text])})

        # async for exited — Deepgram closed connection server-side; trigger reconnect
        raise Exception("server closed connection")

    while True:
        try:
            if _working and _working[2] == _main.settings.utterance_end_ms:
                attempts = [("reconnect", _working[0], _working[1])]
            else:
                _working = None
                attempts = (
                    _build_attempts(sample_rate, channels)
                    + _build_attempts(16000, 1)
                )

            for desc, conn_url, hdrs in attempts:
                try:
                    print(f"[mic_engine] Connecting ({desc})...", flush=True)
                    async with websockets.connect(conn_url, additional_headers=hdrs) as ws:
                        active_uend = _main.settings.utterance_end_ms
                        _working = (conn_url, hdrs, active_uend)
                        transcript_buffer.clear()
                        deadline = time.monotonic() + _MAX_CONN_SECS
                        print(f"[mic_engine] OK Connected to Deepgram ({desc})", flush=True)
                        broadcast({"type": "mic_deepgram_status", "connected": True})
                        await asyncio.gather(
                            send_audio(ws, deadline),
                            receive_results(ws, active_uend),
                        )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    print(f"[mic_engine] Connection ended ({desc}): {exc}", flush=True)
                    if _working and _working[0] == conn_url:
                        broadcast({"type": "mic_deepgram_status", "connected": False})
                        break
                    continue
            else:
                _working = None
                print("[mic_engine] ! All mic connection attempts failed — retrying in 3s", flush=True)
                broadcast({"type": "mic_deepgram_status", "connected": False})
                await asyncio.sleep(3)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            print(f"[mic_engine] ! Unexpected error: {exc} — retrying in 3s", flush=True)
            await asyncio.sleep(3)

    stream.stop_stream()
    stream.close()
    pa.terminate()
    print("[mic_engine] OK Mic shutdown complete", flush=True)
