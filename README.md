# binaural-voice：让 TTS 语音贴在耳边说话、绕着头走

TTS 生成的语音条都是单声道，戴耳机听，声音像在脑袋正中间。这个小工具把单声道人声渲染成**双耳立体声**：用 Neumann KU100 假人头实测的**近场** HRIR（25cm 起），让声音像贴在耳边说话，并且可以按稿子里的**位置标签**，在头周围慢慢移动。

**只对耳机成立。**

- 贴耳：25cm 近场实测数据。耳边说话的低频抬升、两耳之间的巨大音量差，都来自真实测量，不是靠调音量模拟
- 移动：稿子里写 `[左耳]` `[右耳]` `[脑后]` `[面前]` `[贴近]` `[退开]`，声音会一边说一边慢慢挪过去
- 只在出声的时候走，换气停顿时停在原地，所以不会从一只耳朵瞬移到另一只
- 一个标签都没写的话，随机抽一种走法

## 快速开始

```bash
pip install numpy scipy
```

**已经有一段单声道人声**（任何 TTS 或录音都行）：

```bash
ffmpeg -i voice.mp3 -ac 1 voice.wav
python binaural_voice.py voice.wav out.wav                        # 随机走法
python binaural_voice.py voice.wav out.wav '[{"t": 0, "tag": "右耳"}, {"t": 2.4, "tag": "脑后"}]'
```

`t` 是从第几秒起往那个位置走。

**用 ElevenLabs 直接念带标签的稿子**：

```bash
export ELEVENLABS_API_KEY=...
export ELEVENLABS_VOICE_ID=...
python speak.py "[右耳][whispers] Don't move. [脑后] I'm right behind you. [左耳] And now I'm here." out.wav
```

- 默认输出 24kHz。如果是 Pro 及以上套餐，可以设 `ELEVENLABS_FORMAT=pcm_44100` 换成 44.1kHz
- 输出是 WAV。要转成 m4a 的话：`ffmpeg -i out.wav -c:a aac -b:a 192k out.m4a`，码率别压太低

## 位置标签

| 标签 | 效果 |
|---|---|
| `[左耳]` `[右耳]` | 到耳边，25cm |
| `[脑后]` | 到脑后，约 31cm |
| `[面前]` | 到面前，约 42cm |
| `[贴近]` | 只改远近：贴回 25cm |
| `[退开]` | 只改远近：退到 50cm，声音会自然变远变轻 |

- 写在开头：一开口就在那个位置
- 写在句子中间：从这里开始，一边说一边慢慢挪过去
- 从一只耳朵到另一只，会从脑后绕过去，不会从脸前穿过
- 标签只决定去哪里，快慢由脚本决定：绕半圈用 4.5 秒的出声时间，短语音里最多快四成。所以怎么写都不会跳
- 新标签会从当前位置直接改道。`[贴近]` 和 `[退开]` 不会打断正在进行的绕行
- 到了新位置，距离会恢复成那个位置的默认值
- 如果已经贴在耳边（25cm，数据集最近的一档），再写 `[贴近]` 不会有变化。它主要用在 `[退开]` 之后，或者人在脑后、面前的时候

没有标签时，从这几种走法里随机抽一种：整条贴着一只耳朵、从一只耳朵绕到另一只（语音够长时会在脑后停一下）、从脑后绕到耳边、从面前靠到耳边。

## 接进自己的应用

1. **念之前把位置标签从稿子里拿掉**。eleven_v3 会把不认识的方括号当成演出指令去演。同时记下每个标签落在拿掉之后的第几个字
2. 用 **`/v1/text-to-speech/{voice_id}/with-timestamps`** 合成。价格跟普通接口一样，一次请求同时返回音频和逐字的起止时间
3. 取标签后面那个字的开始时间，换算成秒
4. 调用 `binaural_voice.py in.wav out.wav '<cues JSON>'`

第 1 步用 JavaScript 写是这样：

```js
const TAG = /\[(左耳|右耳|脑后|面前|贴近|退开)\]/g;
function splitTags(text) {
  const marks = [];
  let tts = "", last = 0;
  for (const m of text.matchAll(TAG)) {
    tts += text.slice(last, m.index);
    marks.push({ tag: m[1], at: tts.length });
    last = m.index + m[0].length;
  }
  return { tts: tts + text.slice(last), marks };
}
// 合成后：t = alignment.character_start_times_seconds[at]
```

如果稿子是 LLM 写的，在它的工具说明里加一段就行，比如：

> The listener is on headphones and your voice moves around their head. Optional position tags (stripped before speaking): [左耳] / [右耳] / [脑后] / [面前] — go there, slowly, while you talk (at the very start = you're already there; ear to ear passes behind their head); [贴近] lean back in close / [退开] step back. Place them where the words mean it (I'm right behind you → [脑后]). Skip them and a movement is picked for you.

在 M3 Pro 的 Mac 上，16 秒的语音渲染大约 1 秒，适合语音条这种非实时的场景。实时通话就不建议加了。

## 为什么这么做：试听下来的结论

- **近场实测数据明显更好。** 同一句耳语、同一条移动路线、同样的响度，打乱顺序盲听三种做法：Web Audio `PannerNode`（HRTF 模式）、Resonance Audio 网页版、KU100 近场数据离线渲染，近场那条胜出。前两种都没有近场效果：`PannerNode` 的距离只改音量、不改频谱；Resonance Audio 只有 C++ SDK 做了近场，网页版没有
- **别在停顿里移动。** 停顿时没有声音，听的人听不见移动的过程，只会觉得下一句突然换到了另一只耳朵
- **别匀速来回摆。** 按正弦在两耳之间一直晃，听起来很死板。更像真人的节奏是：贴着一只耳朵说一阵，一边说一边慢慢绕，在脑后停一下，再到另一边
- **eleven_v3 的时间戳，开头那段不准。** 稿子开头的语气标签（比如 `[whispers]`）会占掉开头一段时间，把第一个字的时间挤歪；句子中间的时间是准的，跟实际停顿差不到 0.1 秒。所以停顿是从音频能量里找的，位置标签才用时间戳
- **数据集要乘回增益。** 各个距离的 SOFA 文件都各自做过归一化，要乘上官方给的增益表（25cm 为 1.0，50cm 为 0.33，…），远近的音量差才是自然的
- 语音条的稿子一般只有一两句。如果只有一套固定编舞，每条都只能演到前半段，听起来条条一样。所以没写标签时准备了几种短走法随机抽

## 调参

参数都在 `binaural_voice.py` 顶部：

- `PLACES`：各位置的方向和默认距离
- `HALF_TURN`：绕半圈用几秒
- `DIST_MOVE`：只改远近时用几秒
- `DRIFT_DEG` / `DRIFT_M`：停住时微晃的幅度
- 随机走法在 `random_cues()` 里

## 局限

- 只对耳机成立
- 只有水平面，没有上下
- 最近只到 25cm
- 用的是通用的假人头数据，不是按每个人的耳朵测的，有的人会前后听反（脑后听成面前）
- TTS 的耳语很干净，没有真人 ASMR 那种口腔音和呼吸声。声音能到耳边，但「湿」不起来
- 用 24kHz 输出时，高频上限是 12kHz

## 数据来源与授权

`hrir/ku100_nearfield_circ360.npz` 取自：

> J. M. Arend, A. Neidhardt, C. Pörschmann. *Spherical Near-Field (NF) HRIR Compilation of the Neumann KU100.* Zenodo, 2020. [doi:10.5281/zenodo.4297951](https://doi.org/10.5281/zenodo.4297951) — **CC BY 4.0**

- 用的是其中的 `NFHRIR_CIRC360_SOFA`：水平面，1° 间隔，距离 0.25 / 0.5 / 0.75 / 1 / 1.5 m，48kHz，每条 128 点
- 只做了格式转换：SOFA 转成 numpy 的 npz，float32，数据本身没有改动
- 增益表出自同一条记录里的 `NF_Datasets_Gains_infos.pdf`

相关论文：

- J. M. Arend, A. Neidhardt, C. Pörschmann, "Measurement and Perceptual Evaluation of a Spherical Near-Field HRTF Set," *29th Tonmeistertagung*, 2016.
- C. Pörschmann, J. M. Arend, A. Neidhardt, "A Spherical Near-Field HRTF Set for Auralization and Psychoacoustic Research," *142nd AES Convention*, 2017.

想自己从原始数据转换的话（需要 `h5py`）：

```python
import h5py, numpy as np
d = ["025", "050", "075", "100", "150"]
ir = np.stack([h5py.File(f"HRIR_CIRC360_NF{x}.sofa")["Data.IR"][:] for x in d]).astype(np.float32)
np.savez_compressed("hrir/ku100_nearfield_circ360.npz", ir=ir, fs=48000, dists=np.array([0.25, 0.5, 0.75, 1.0, 1.5]))
```
