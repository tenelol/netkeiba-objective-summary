# netkeiba-objective-summary

netkeiba の公開掲示板コメントを取得し、AI-MOP/OpenAI 互換 API で「客観性の高い情報だけ」を要約する小さなツールです。

## Webで使う

macOS/Linux:

```bash
cd /Users/tener/project/netkeiba-objective-summary
export OPENAI_API_KEY='<AI-MOP API key>'
python3 web_app.py
```

Windows PowerShell:

```powershell
git clone https://github.com/tenelol/netkeiba-objective-summary.git
cd netkeiba-objective-summary
$env:OPENAI_API_KEY = '<AI-MOP API key>'
python web_app.py
```

ブラウザで `http://127.0.0.1:8765` を開き、netkeiba の掲示板 URL を貼って「要約する」を押します。

`OPENAI_API_KEY` を設定せずに起動した場合は、画面の API キー欄に一時入力して使えます。入力したキーは保存しません。

## CLIで使う

```bash
cd /Users/tener/project/netkeiba-objective-summary
export OPENAI_API_KEY='<AI-MOP API key>'
python3 netkeiba_objective_summary.py 'https://db.netkeiba.com/?pid=horse_board&id=2022105076'
```

デフォルトの API ベース URL は `https://api.openai.iniad.org/api/v1`、モデルは `INIAD_OPENAI_MODEL` または `OPENAI_MODEL` があればそれを使い、なければ `gpt-5.4` です。

```bash
INIAD_OPENAI_MODEL=gpt-4.1 \
python3 netkeiba_objective_summary.py \
  --pages 2 \
  --max-comments 80 \
  --sort like \
  'https://db.netkeiba.com/?pid=horse_board&id=2022105076'
```

JSON で受け取りたい場合:

```bash
python3 netkeiba_objective_summary.py --json 'https://db.netkeiba.com/?pid=horse_board&id=2022105076'
```

取得だけ確認したい場合:

```bash
python3 netkeiba_objective_summary.py \
  --dump-comments comments.json \
  'https://db.netkeiba.com/?pid=horse_board&id=2022105076'
```

保存済みコメントから再実行:

```bash
python3 netkeiba_objective_summary.py --comments-json comments.json
```

## 要約の方針

- 採用: 日付、レース名、馬場、枠順、騎手、調教、馬体、出走予定、過去成績など、観察可能な根拠がある投稿。
- 採用しやすい: 複数コメントで共通している情報。
- 除外または別枠: 馬券推奨、順位予想、願望、煽り、感情的評価、根拠のない断言、誹謗中傷。
- 各要約項目には根拠 comment id を残します。

掲示板投稿は一次情報とは限らないため、出力は「掲示板上で確認できる客観寄りの言及」として扱います。馬券購入判断を自動化する用途にはしないでください。

## netkeiba へのアクセス

この CLI は明示された公開 URL だけを取得し、ログイン回避や非公開情報取得は行いません。複数ページを読む場合は `--delay` で間隔を空けます。

## テスト

```bash
python3 -m unittest discover -s tests
```
