import asyncio
import json
import os
import queue as sync_queue
import sys

import pyaudiowpatch as pyaudio
import websockets
from dotenv import load_dotenv

load_dotenv()

_DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
_CHUNK = 2048

print("[audio_engine] Initializing...", flush=True)


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
        # pyaudiowpatch appends " [Loopback]" to the output device name
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

    # Thread-safe queue filled by pyaudio's internal callback thread
    audio_queue: sync_queue.Queue = sync_queue.Queue(maxsize=100)

    def _audio_callback(in_data, frame_count, time_info, status):
        try:
            # Use put with timeout to prevent blocking
            audio_queue.put(in_data, timeout=0.1)
        except sync_queue.Full:
            pass  # drop oldest data if we fall behind
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
        print(f"[audio_engine] ✓ Audio stream started successfully", flush=True)
    except Exception as exc:
        pa.terminate()
        print(f"[audio_engine] ERROR - stream open error: {exc}", flush=True)
        return

    print(f"[audio_engine] sample rate: {sample_rate}Hz, channels: {channels}", flush=True)

    async def send_audio(ws):
        loop = asyncio.get_event_loop()
        while True:
            # queue.get() with timeout to prevent indefinite blocking
            try:
                data = await asyncio.wait_for(
                    loop.run_in_executor(None, audio_queue.get),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                # Queue timeout - recheck connection
                continue
            await ws.send(data)

    transcript_buffer = []

    async def receive_results(ws):
        async for message in ws:
            try:
                result = json.loads(message)
            except json.JSONDecodeError:
                continue

            msg_type = result.get("type", "Results")

            if msg_type == "UtteranceEnd":
                full_text = " ".join(transcript_buffer).strip()
                transcript_buffer.clear()
                if not _main.current_muted and len(full_text.split()) >= 4:
                    print(f"[audio_engine] utterance: {full_text}", flush=True)
                    broadcast({"type": "transcript", "text": full_text})
                    await stream_answer(full_text, _main.current_engine)
                continue

            if msg_type != "Results":
                continue

            if _main.current_muted:
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

    _base = "wss://api.deepgram.com/v1/listen"
    _working: tuple | None = None  # (url, headers) of last successful connection

    def _build_attempts(sr, ch):
        params = (
            f"model=nova-2&smart_format=true&interim_results=true"
            f"&encoding=linear16&sample_rate={sr}&channels={ch}&utterance_end_ms=1500"
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
            # Prefer the last working combo; fall back to device then 16kHz/mono
            if _working:
                attempts = [("reconnect", *_working)]
            else:
                attempts = (
                    _build_attempts(sample_rate, channels)
                    + _build_attempts(16000, 1)
                )

            for desc, conn_url, hdrs in attempts:
                try:
                    print(f"[audio_engine] Attempting connection ({desc})...", flush=True)
                    async with websockets.connect(conn_url, additional_headers=hdrs) as ws:
                        _working = (conn_url, hdrs)
                        transcript_buffer.clear()
                        print(f"[audio_engine] ✓ Connected to Deepgram ({desc})", flush=True)
                        await asyncio.gather(send_audio(ws), receive_results(ws))
                except asyncio.CancelledError:
                    print("[audio_engine] Connection cancelled", flush=True)
                    raise
                except Exception as exc:
                    print(f"[audio_engine] Connection failed ({desc}): {exc}", flush=True)
                    if _working and _working[0] == conn_url:
                        # Was connected, then dropped — retry same method next loop
                        break
                    continue
            else:
                # All fresh attempts failed
                _working = None
                print("[audio_engine] ⚠ All connection attempts failed — retrying in 1s", flush=True)
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            print(f"[audio_engine] ⚠ Unexpected error: {exc} — retrying in 1s", flush=True)
            await asyncio.sleep(1)

    print("[audio_engine] Shutting down audio stream...", flush=True)
    stream.stop_stream()
    stream.close()
    pa.terminate()
    print("[audio_engine] ✓ Shutdown complete", flush=True)
