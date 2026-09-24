"""
单声道人声 → 双耳立体声（KU100 近场 HRIR），声音在听者头边移动。只对耳机成立。

  python binaural_voice.py in.wav out.wav                  # 没有位置标签：随机抽一种走法
  python binaural_voice.py in.wav out.wav '[{"t": 0, "tag": "右耳"}, {"t": 2.4, "tag": "脑后"}]'

t   = 从第几秒起去那儿（秒）
tag = 左耳 / 右耳 / 脑后 / 面前（去那儿）· 贴近 / 退开（只改远近）

依赖 numpy、scipy。只读写 WAV；mp3 先转：ffmpeg -i in.mp3 -ac 1 in.wav
"""
import json, os, random, sys
import numpy as np
from scipy.io import wavfile
from scipy.signal import fftconvolve, resample_poly

# 位置：方位角（逆时针，0=前 90=左 180=后 270=右）+ 默认距离 m。25cm 是数据集最近的一档
PLACES = {"左耳": (90, 0.25), "右耳": (270, 0.25), "脑后": (180, 0.31), "面前": (0, 0.42)}
NEAR, FAR = 0.25, 0.5          # [贴近] / [退开] 到的距离
HALF_TURN = 4.5                # 绕半圈（180°）用多少「出声秒」
DIST_MOVE = 1.5                # 只改远近用多少出声秒
DRIFT_DEG, DRIFT_M = 5, 0.015  # 停住时的微晃幅度
# 数据集各距离做过归一化，乘回官方给的增益才有自然的远近音量差（见 README 致谢）
GAINS = [1.00, 0.33, 0.25, 0.16, 0.095]

src, dst = sys.argv[1], sys.argv[2]
tag_cues = json.loads(sys.argv[3]) if len(sys.argv) > 3 else []

fs, x = wavfile.read(src)
if np.issubdtype(x.dtype, np.integer):
    x = x / np.iinfo(x.dtype).max
x = x.astype(np.float64)
if x.ndim > 1:
    x = x.mean(axis=1)

# ── 出声时间：走位只在出声时推进，换气停顿时停在原地 ──
# （在停顿里挪，听的人听不见挪的过程，只会觉得声音从一只耳朵瞬移到另一只）
# 10ms 一格，低于峰值 5% 算静；字间 <0.4s 的小缝算在出声；平滑 0.2s 让走停有缓冲
hop = fs // 100
rms = np.array([np.sqrt((x[i:i + hop] ** 2).mean()) for i in range(0, len(x) - hop, hop)])
voiced = rms > rms.max() * 0.05
i = 0
while i < len(voiced):
    j = i
    while j < len(voiced) and not voiced[j]:
        j += 1
    if 0 < i and j < len(voiced) and j - i < 40:
        voiced[i:j] = True
    i = max(j, i + 1)
speed = np.convolve(voiced.astype(float), np.ones(20) / 20, mode="same")
tau = np.concatenate([[0], np.cumsum(speed)]) * 0.01
speech_time = lambda t: np.interp(t, np.arange(len(tau)) * 0.01, tau)
T = tau[-1]

# ── 走位 ──
def random_cues():
    ear = random.choice(["左耳", "右耳"])
    other = "右耳" if ear == "左耳" else "左耳"
    kind = random.choices(["贴耳", "绕过去", "从脑后来", "从面前靠过来"], weights=[1, 2, 1, 1])[0]
    if kind == "贴耳":
        return [(0, ear)]
    if kind == "绕过去":   # 够长就在脑后停一下
        return [(0, ear), (0.2 * T, "脑后"), (0.6 * T, other)] if T > 6 else [(0, ear), (0.3 * T, other)]
    return [(0, "脑后" if kind == "从脑后来" else "面前"), (0.35 * T, ear)]

cues = [(float(speech_time(c["t"])), c["tag"]) for c in tag_cues if c["tag"] in PLACES or c["tag"] in ("贴近", "退开")]
if not cues:                   # 写了标签就全听标签的，一个没写才随机
    cues = random_cues()
cues.sort(key=lambda c: c[0])
if cues[0][1] in PLACES and cues[0][0] < 0.3:
    start = PLACES[cues.pop(0)[1]]
else:
    start = PLACES[random.choice(["左耳", "右耳"])]

def az_path(a0, a1):
    a0 %= 360
    short = (a1 - a0 + 180) % 360 - 180
    return short if abs(short) <= 150 else a1 - a0      # 耳到耳走脑后，不穿过脸前

# 方位和远近各走各的轨道：[贴近] [退开] 只改远近，正在绕的方向照常走完。
# 每段 (τ0, τ1, 起点, 变化量)；后一段从前一段在那一刻的值接着走（没走完就改道，不会跳）
az_segs, d_segs = [], []
def track_at(segs, s, init):
    active = [g for g in segs if g[0] <= s]
    if not active:
        return init
    s0, s1, v0, dv = active[-1]
    return v0 + dv * (1 - np.cos(np.pi * min(1.0, (s - s0) / (s1 - s0)))) / 2
pos_at = lambda s: (track_at(az_segs, s, start[0]), track_at(d_segs, s, start[1]))

for s, tag in cues:
    az, d = pos_at(s)
    if tag in PLACES:
        target_az, target_d = PLACES[tag]
        da = az_path(az, target_az)
        nominal = abs(da) / 180 * HALF_TURN if abs(da) > 1 else DIST_MOVE
    else:
        target_d, da, nominal = (NEAR if tag == "贴近" else FAR), 0.0, DIST_MOVE
    dur = max(min(nominal, 0.9 * (T - s)), 0.6 * nominal)   # 短语音里尽量走完，但最多快四成
    if abs(da) > 1:
        az_segs.append((s, s + dur, az, da))
    if abs(target_d - d) > 0.01:
        d_segs.append((s, s + dur, d, target_d - d))
phase = random.uniform(0, 2 * np.pi)

def position(t):
    az, d = pos_at(speech_time(t))
    return (az + DRIFT_DEG * np.sin(2 * np.pi * t / 4.3 + phase) + 2 * np.sin(2 * np.pi * t / 1.9 + 2 * phase),
            d + DRIFT_M * np.sin(2 * np.pi * t / 3.7 + 3 * phase))

# ── 渲染：1024 点帧、50% 重叠 Hann，每帧按当时位置取 HRIR（距离线性插值）卷积后叠加 ──
data = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "hrir", "ku100_nearfield_circ360.npz"))
dists = data["dists"]
H = resample_poly(data["ir"].astype(np.float64), fs, int(data["fs"]), axis=3) * np.array(GAINS)[:, None, None, None]

def hrir_at(az, d):
    a = int(round(az)) % 360
    d = min(max(d, dists[0]), dists[-1])
    k = min(np.searchsorted(dists, d, side="right") - 1, len(dists) - 2)
    w = (d - dists[k]) / (dists[k + 1] - dists[k])
    return (1 - w) * H[k, a] + w * H[k + 1, a]

N, Hop = 1024, 512
win = np.hanning(N + 1)[:N]
L = H.shape[3]
out = np.zeros((len(x) + 2 * N + L, 2))
for s in range(-Hop, len(x), Hop):
    seg = np.zeros(N)
    lo, hi = max(s, 0), min(s + N, len(x))
    seg[lo - s:hi - s] = x[lo:hi]
    h = hrir_at(*position((s + N / 2) / fs))
    for e in (0, 1):
        y = fftconvolve(seg * win, h[e])
        out[s + Hop:s + Hop + len(y), e] += y
out = out[Hop:Hop + len(x) + L]

# 响度跟原声对齐，峰值压在 -1 dBFS 以下
out *= np.sqrt((x ** 2).mean() * 2 / (out ** 2).mean())
out *= min(1.0, 0.89 / np.abs(out).max())
wavfile.write(dst, fs, np.int16(out * 32767))
