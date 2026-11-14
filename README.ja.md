# binaural-voice：TTS の音声を耳元で話させ、頭のまわりを動かす

[简体中文](README.md) | **日本語**

TTS で生成したボイスメッセージはどれもモノラルで、イヤホンで聴くと声が頭の真ん中で鳴っているように聞こえます。この小さなツールは、モノラルの音声を**バイノーラル（両耳）ステレオ**にレンダリングします。Neumann KU100 ダミーヘッドで実測した**近距離（ニアフィールド）**の HRIR（25cm から）を使って耳元で話しかけられているように聞かせ、さらに原稿中の**位置タグ**に従って、声を頭のまわりでゆっくり移動させます。

**ヘッドホン（イヤホン）で聴く場合にのみ効果があります。**

- 耳元：25cm の近距離実測データを使用しています。耳元で話すときの低域の持ち上がりも、左右の耳の大きな音量差も、音量調整で模したものではなく実測に基づくものです
- 移動：原稿に `[左耳]` `[右耳]` `[脑后]` `[面前]` `[贴近]` `[退开]` と書くと、話しながら声がゆっくりその位置へ移動します
- 声が出ている間だけ移動し、息継ぎの間はその場にとどまるため、片方の耳からもう片方の耳へ瞬間移動することはありません
- タグを一つも書かなかった場合は、動き方をランダムに一つ選びます

## クイックスタート

```bash
pip install numpy scipy
```

**モノラルの音声がすでにある場合**（TTS でも録音でも構いません）：

```bash
ffmpeg -i voice.mp3 -ac 1 voice.wav
python binaural_voice.py voice.wav out.wav                        # ランダムな動き方
python binaural_voice.py voice.wav out.wav '[{"t": 0, "tag": "右耳"}, {"t": 2.4, "tag": "脑后"}]'
```

`t` は、何秒目からその位置へ向かい始めるかを表します。

**ElevenLabs でタグ付きの原稿を直接読み上げる場合**：

```bash
export ELEVENLABS_API_KEY=...
export ELEVENLABS_VOICE_ID=...
python speak.py "[右耳][whispers] Don't move. [脑后] I'm right behind you. [左耳] And now I'm here." out.wav
```

- デフォルトの出力は 24kHz です。Pro 以上のプランであれば、`ELEVENLABS_FORMAT=pcm_44100` を設定すると 44.1kHz に変更できます
- 出力は WAV です。m4a に変換する場合は `ffmpeg -i out.wav -c:a aac -b:a 192k out.m4a` を使います。ビットレートは下げすぎないでください

## 位置タグ

| タグ | 効果 |
|---|---|
| `[左耳]` `[右耳]`（左耳・右耳） | 耳元へ移動、25cm |
| `[脑后]`（頭の後ろ） | 頭の後ろへ移動、約 31cm |
| `[面前]`（正面） | 顔の正面へ移動、約 42cm |
| `[贴近]`（近づく） | 距離だけを変更：25cm まで近づく |
| `[退开]`（離れる） | 距離だけを変更：50cm まで離れる。声は自然に遠く、小さくなります |

- 冒頭に書いた場合：話し始めた時点でその位置にいます
- 文の途中に書いた場合：そこから、話しながらゆっくり移動していきます
- 片方の耳からもう片方の耳へ移るときは、頭の後ろを回り込み、顔の前は横切りません
- タグが決めるのは行き先だけで、速さはスクリプトが決めます。半周するのに発声時間で 4.5 秒かけ、短い音声では最大 4 割まで速めます。そのため、どう書いても音が飛ぶことはありません
- 新しいタグが来ると、現在の位置からそのまま進路を変えます。`[贴近]` と `[退开]` は、進行中の回り込みを中断しません
- 新しい位置に着くと、距離はその位置のデフォルト値に戻ります
- すでに耳元（25cm、データセットで最も近い距離）にいる場合は、`[贴近]` を書いても変化はありません。主に `[退开]` の後や、頭の後ろ・正面にいるときに使います

タグがない場合は、次の動き方からランダムに一つ選びます：最初から最後まで片方の耳元にいる／片方の耳からもう片方の耳へ回り込む（音声が十分に長ければ、頭の後ろで一度止まる）／頭の後ろから耳元へ回り込む／正面から耳元へ近づく。

## 自分のアプリケーションに組み込む

1. **読み上げる前に、原稿から位置タグを取り除きます**。eleven_v3 は、知らない角括弧を演技の指示として解釈し、演じてしまうためです。あわせて、各タグが、取り除いた後の文字列の何文字目にあたるかを記録しておきます
2. **`/v1/text-to-speech/{voice_id}/with-timestamps`** で合成します。料金は通常のエンドポイントと同じで、1 回のリクエストで音声と、文字ごとの開始・終了時刻の両方が返ってきます
3. タグの直後にある文字の開始時刻を取り、秒に換算します
4. `binaural_voice.py in.wav out.wav '<cues JSON>'` を呼び出します

手順 1 を JavaScript で書くと次のようになります。

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
// 合成後：t = alignment.character_start_times_seconds[at]
```

原稿を LLM（AI エージェント）に書かせる場合は、そのツールの説明に次のような一段を加えるだけで済みます。

> The listener is on headphones and your voice moves around their head. Optional position tags (stripped before speaking): [左耳] / [右耳] / [脑后] / [面前] — go there, slowly, while you talk (at the very start = you're already there; ear to ear passes behind their head); [贴近] lean back in close / [退开] step back. Place them where the words mean it (I'm right behind you → [脑后]). Skip them and a movement is picked for you.

M3 Pro 搭載の Mac では、16 秒の音声のレンダリングに約 1 秒かかります。ボイスメッセージのような非リアルタイムの用途に向いています。リアルタイム通話への組み込みはおすすめしません。

## なぜこうしたのか：聴き比べから得た結論

- **近距離の実測データのほうが明らかに良い。** 同じささやき声・同じ移動経路・同じラウドネスで、Web Audio の `PannerNode`（HRTF モード）、Resonance Audio の Web 版、KU100 近距離データによるオフラインレンダリングの 3 方式を、順番をシャッフルしてブラインドで聴き比べたところ、近距離データのものが選ばれました。前の 2 つにはどちらもニアフィールド効果がありません。`PannerNode` は距離によって音量が変わるだけでスペクトルは変わらず、Resonance Audio は C++ SDK にしかニアフィールド処理がなく、Web 版にはありません
- **無音の間に移動させない。** 間には音がないため、聴き手には移動の過程が聞こえず、次の文が突然もう片方の耳に飛んだように感じられます
- **一定の速さで往復させない。** 正弦波で両耳の間を揺らし続けると、機械的に聞こえます。より人間らしいのは、片方の耳元でしばらく話し、話しながらゆっくり回り込み、頭の後ろで一度止まってから反対側へ行く、というリズムです
- **eleven_v3 のタイムスタンプは冒頭部分が不正確。** 原稿冒頭の話し方を指定するタグ（`[whispers]` など）が最初の一定時間を占めるため、最初の文字の時刻がずれます。文の途中の時刻は正確で、実際の間とのずれは 0.1 秒未満です。そのため、間（ポーズ）は音声のエネルギーから検出し、タイムスタンプは位置タグにだけ使っています
- **データセットにはゲインを掛け戻す必要がある。** 各距離の SOFA ファイルはそれぞれ個別に正規化されているため、公式のゲイン表（25cm が 1.0、50cm が 0.33、…）を掛けて、はじめて距離による音量差が自然になります
- ボイスメッセージの原稿はたいてい 1〜2 文です。固定の振り付けが 1 パターンしかないと、どのメッセージでも振り付けの前半までしか進まず、どれも同じに聞こえます。そこで、タグがない場合に備えて短い動き方を何種類か用意し、ランダムに選ぶようにしました

## パラメーター調整

パラメーターはすべて `binaural_voice.py` の冒頭にあります。

- `PLACES`：各位置の方向とデフォルトの距離
- `HALF_TURN`：半周に何秒かけるか
- `DIST_MOVE`：距離だけを変えるときに何秒かけるか
- `DRIFT_DEG` / `DRIFT_M`：止まっている間の微小な揺れの幅
- ランダムな動き方は `random_cues()` の中にあります

## 制限事項

- ヘッドホン（イヤホン）で聴く場合にのみ効果があります
- 水平面のみで、上下方向はありません
- 最も近い距離は 25cm までです
- 一人ひとりの耳に合わせて測ったものではなく汎用のダミーヘッドのデータを使っているため、人によっては前後が逆に聞こえる（頭の後ろの音が正面から聞こえる）ことがあります
- TTS のささやき声はきれいすぎて、実際の ASMR のような口の音や息づかいがありません。声は耳元まで来ますが、「湿り気」は出せません
- 24kHz で出力した場合、高域の上限は 12kHz です

## データの出典とライセンス

AGPL-3.0 に、著作者表示に関する追加条項を 1 つ加えています（[NOTICE](./NOTICE) を参照）。本プロジェクトを含む、または本プロジェクトに基づく著作物は、同じく AGPL-3.0 で公開する必要があり（ネットワークサービスとして他者に提供する場合も含みます）、NOTICE に記載の著作者表示を残さなければなりません。`hrir/` 内のデータはこの対象外で、原著者による CC BY 4.0 が引き続き適用されます。

`hrir/ku100_nearfield_circ360.npz` の出典：

> J. M. Arend, A. Neidhardt, C. Pörschmann. *Spherical Near-Field (NF) HRIR Compilation of the Neumann KU100.* Zenodo, 2020. [doi:10.5281/zenodo.4297951](https://doi.org/10.5281/zenodo.4297951) — **CC BY 4.0**

- 使用しているのはその中の `NFHRIR_CIRC360_SOFA` です：水平面、1° 間隔、距離 0.25 / 0.5 / 0.75 / 1 / 1.5 m、48kHz、各 128 サンプル
- 行ったのはフォーマット変換のみです（SOFA から NumPy の npz へ、float32）。データ自体には手を加えていません
- ゲイン表は、同じレコードに含まれる `NF_Datasets_Gains_infos.pdf` によるものです

関連論文：

- J. M. Arend, A. Neidhardt, C. Pörschmann, "Measurement and Perceptual Evaluation of a Spherical Near-Field HRTF Set," *29th Tonmeistertagung*, 2016.
- C. Pörschmann, J. M. Arend, A. Neidhardt, "A Spherical Near-Field HRTF Set for Auralization and Psychoacoustic Research," *142nd AES Convention*, 2017.

元データから自分で変換する場合（`h5py` が必要です）：

```python
import h5py, numpy as np
d = ["025", "050", "075", "100", "150"]
ir = np.stack([h5py.File(f"HRIR_CIRC360_NF{x}.sofa")["Data.IR"][:] for x in d]).astype(np.float32)
np.savez_compressed("hrir/ku100_nearfield_circ360.npz", ir=ir, fs=48000, dists=np.array([0.25, 0.5, 0.75, 1.0, 1.5]))
```
