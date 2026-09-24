"""
用 ElevenLabs 念一段带位置标签的稿子，渲染成双耳立体声 WAV。

  export ELEVENLABS_API_KEY=...
  export ELEVENLABS_VOICE_ID=...
  python speak.py "[右耳][whispers] Don't move. [脑后] I'm right behind you. [左耳] And now I'm here." out.wav

只用标准库调 API；渲染交给 binaural_voice.py（numpy、scipy）。
"""
import base64, json, os, re, subprocess, sys, tempfile, urllib.error, urllib.request, wave

TAG = re.compile(r"\[(左耳|右耳|脑后|面前|贴近|退开)\]")
FORMAT = os.environ.get("ELEVENLABS_FORMAT", "pcm_24000")   # pcm_44100 只有 Pro 及以上套餐能用
text, out = sys.argv[1], sys.argv[2]

# 1. 念之前拿掉位置标签（eleven_v3 会把不认识的方括号当演出指令），记下每个标签落在拿掉后的第几个字
tts, marks, last = "", [], 0
for m in TAG.finditer(text):
    tts += text[last:m.start()]
    marks.append((m.group(1), len(tts)))
    last = m.end()
tts += text[last:]

# 2. with-timestamps 端点：一次请求同时拿音频和逐字起止时间，价格一样
req = urllib.request.Request(
    f"https://api.elevenlabs.io/v1/text-to-speech/{os.environ['ELEVENLABS_VOICE_ID']}/with-timestamps?output_format={FORMAT}",
    data=json.dumps({"text": tts, "model_id": "eleven_v3"}).encode(),
    headers={"Content-Type": "application/json", "xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
)
try:
    d = json.load(urllib.request.urlopen(req, timeout=120))
except urllib.error.HTTPError as e:
    sys.exit(f"ElevenLabs {e.code}: {e.read().decode()[:300]}")

# 3. 标签换成秒数：取它后面那个字的开始时间（对齐表和发出去的稿子逐字对应；对不上就不用标签）
starts = d["alignment"]["character_start_times_seconds"]
if len(starts) == len(tts):
    cues = [{"tag": tag, "t": starts[min(at, len(starts) - 1)]} for tag, at in marks]
else:
    cues = []
    print("对齐表和稿子字数对不上，这次不用位置标签", file=sys.stderr)

# 4. PCM → WAV → 渲染
fd, tmp = tempfile.mkstemp(suffix=".wav")
os.close(fd)
with wave.open(tmp, "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(int(FORMAT.split("_")[1]))
    w.writeframes(base64.b64decode(d["audio_base64"]))
script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "binaural_voice.py")
subprocess.run([sys.executable, script, tmp, out, json.dumps(cues, ensure_ascii=False)], check=True)
os.remove(tmp)
print("cues:", json.dumps(cues, ensure_ascii=False))
