# KPI ゴールデンセット・計測スクリプト 設計書

**日付**: 2026-05-03
**対象ファイル**: `scripts/measure_kpi.py`（新規）, `tests/golden/java/`（新規）, `tests/test_measure_kpi.py`（新規）

---

## 背景・動機

`docs/product-requirements.md` §成功指標(KPI) では以下が定義されている。

- **網羅率**: 既知のテストケース（直接参照・間接参照・getter経由の各パターンを含むサンプル Java ファイル群）で期待TSVの全行が出力に含まれること
- **分類精度**: 7種の使用タイプへの自動分類が一致率 90% 以上（450/500件以上）

しかしこの KPI を継続計測する仕組みは現状なく、コード変更（性能改善・機能追加・防御的修正）が網羅率/精度を維持できているかを定量的に確認する手段がない。直近の `binary/oversize` 修正（commits a478b3d, 3fb15fa）のような防御的変更でも、効果と副作用を数値で示せない状態にある。

本タスクは、F-first（土台づくり）の方針で KPI 計測の基盤を整備する。これが整うと、後続の B（既存言語の深堀り）/ E（性能改善）の改造を「網羅率を落とさず変えられた」と保証しながら進められる。

---

## 要件

1. **Java 先行**: 全パイプライン段階（直接 → 間接 → getter/setter）を通る Java を最初の対象とする
2. **合成最小例**: 使用タイプごとに最小限の Java サンプルを手書きで用意する
3. **独立スクリプト**: pytest 統合や CI ゲートではなく、`python scripts/measure_kpi.py` で任意に実行する
4. **既存資産無変更**: `grep_helper/`・`analyze*.py` は原則そのまま使う
5. **将来言語拡張可能**: `--lang` 引数を持つ汎用構造にしておく（実装は Java のみ）

---

## アーキテクチャ

### ディレクトリ配置

```
tests/golden/                    # ゴールデンセットのルート（pytestには載せない、データ専用）
  java/
    src/                         # 合成 Java ソース（最小例の集合）
      basic/
        Constants.java           # 定数定義パターン
        Service.java             # 条件判定 + 間接参照シナリオ
        Validator.java           # return文 + メソッド引数
        Entity.java              # privateフィールド + getter/setter定義
        Handler.java             # getter経由参照
        ...                      # 各使用タイプ10件以上が出るように分散
    inputs/
      777.grep                   # `grep -rn "777" src/` 相当（手書き）
      CODE.grep                  # 別文言の grep 結果（追跡シナリオ用）
    expected/
      777.tsv                    # 期待TSV（手書き、UTF-8 BOM付き）
      CODE.tsv
    README.md                    # サンプル設計の意図メモ
scripts/
  measure_kpi.py                 # 計測スクリプト
output/
  kpi/                           # レポート出力先（gitignore）
```

### データフロー

```
tests/golden/java/inputs/*.grep
       ↓
[scripts/measure_kpi.py]
       ↓ analyze.py を in-process 呼び出し
       ↓ （--source-dir tests/golden/java/src）
       ↓
actual TSV（一時領域に出力）
       ↓
expected TSV と突合
       ↓
output/kpi/java-<timestamp>.md（詳細レポート）+ stdout サマリ
```

**設計判断**:

- **`tests/golden/` 配下に置く**: pytest テストではなくデータ fixture という位置付け。`tests/test_measure_kpi.py` から参照するためにテスト資産の近くに置く。
- **in-process 呼び出しを優先**: `grep_helper.cli` / `grep_helper.pipeline` をそのまま import して呼ぶ。サブプロセス起動オーバーヘッドを避け、ランタイム例外をその場で捕捉できる。フォールバック: 既存 API で困難なら `subprocess.run` 経由。

### サンプル設計の方針（要件 §成功指標との対応）

| 要件 | 設計の対応 |
|---|---|
| 網羅率：直接・間接・getter経由の各パターン | `777.grep` で全段階を発火させる（`Constants.java` 直接 → `Service.java` 間接 → `Handler.java` getter経由） |
| 分類精度：使用タイプ各10件以上、計500件以上 | 7使用タイプ × 10件 = 70件 を `777.grep` 内に作る。`CODE.grep` 等の別文言で件数を増やし、合計500件以上を達成 |
| 50ファイル目安 | `src/` 配下を機能別に20〜30ファイル。**ファイル数は従、件数（使用タイプ別10件以上）が主** という解釈で実装する |

---

## 計測スクリプト詳細

### CLI インターフェース

```bash
python scripts/measure_kpi.py [--lang java] [--samples-dir tests/golden] [--output-dir output/kpi] [--quiet]
```

| オプション | デフォルト | 説明 |
|---|---|---|
| `--lang` | `java` | 計測対象言語。当面 `java` のみだが、将来 `c` / `kotlin` などで拡張する前提 |
| `--samples-dir` | `tests/golden` | ゴールデンセットのルート |
| `--output-dir` | `output/kpi` | レポート出力先（自動作成） |
| `--quiet` | off | stdout サマリを抑制（詳細レポートは常に出る） |

**終了コード**:

- `0`: 計測完了（KPI 結果がしきい値割れでも fail しない＝CIゲートしない方針）
- `2`: spec 不整合（`inputs/` と `expected/` の対応不一致）または予期しない例外

### 内部処理フロー

1. `samples-dir/<lang>/` を確認し、`inputs/` と `expected/` の対応を検証する
   - `inputs/` にあるが `expected/` にない → エラー（spec 不整合）として `2` で終了
   - `expected/` にあるが `inputs/` にない → 同上
2. `tempfile.TemporaryDirectory()` で actual TSV の出力先を作成する
3. `grep_helper` のパイプラインを in-process で起動する
   - `source_dir = samples-dir/<lang>/src`
   - `input_dir = samples-dir/<lang>/inputs`
   - `output_dir = <tmp>`
4. `inputs/` 内の各 `.grep` ごとに、actual と expected を突合してメトリクスを算出する
5. メトリクスを集計してレポートを書き出す

### モジュール責務分割

スクリプトは1ファイルだが、内部関数で責務を分ける（テスト容易性のため）。

| 関数 | 責務 |
|---|---|
| `load_expected_tsv(path) -> list[Record]` | 期待TSVをパースして `GrepRecord` 互換のレコードに変換 |
| `load_actual_tsv(path) -> list[Record]` | 同上（既存 `grep_helper.tsv_output` のスキーマと整合） |
| `compare(expected, actual) -> ComparisonResult` | 2つのレコード集合から KPI と diff を算出 |
| `format_summary(result) -> str` | stdout 用のサマリ |
| `format_detail_report(result) -> str` | Markdown 詳細レポート |
| `run(args) -> int` | CLI のメイン処理（上記を組み合わせる） |

### 比較ロジック

```python
@dataclass
class ComparisonResult:
    expected_total: int
    matched_rows: int                       # (file, line) 一致
    classified_correctly: int               # matched 内で (参照種別, 使用タイプ) も一致
    coverage_rate: float                    # = matched_rows / expected_total
    classification_accuracy: float          # = classified_correctly / matched_rows
    missing_rows: list[Record]              # 取りこぼし（expected ∋ but actual ∌）
    false_positives: list[Record]           # 余計な行（actual ∋ but expected ∌）
    misclassified: list[tuple[Record, Record]]  # (file, line) 一致で分類不一致
    detail_diffs: list[tuple[Record, Record]]   # 参照元列のみの差分
```

**メトリクス定義**:

- マッチング基準キー = `(ファイルパス, 行番号)` のタプル
- **網羅率** = `matched_rows / expected_total`（行の有無のみ）
- **分類精度** = `classified_correctly / matched_rows`（一致行のうち、`(参照種別, 使用タイプ)` も一致した割合）
- **false positive 件数** = `len(false_positives)`（記録のみ、KPIに算入しない）
- **詳細列差分**（参照元変数名・参照元ファイル・参照元行番号）は `detail_diffs` に記録するだけで、KPI には影響させない

**同一 (file, line) に複数行が来た場合**: `(file, line, 参照種別)` で2次キーを取る。実装は1次キーから始め、サンプル運用で衝突したら2次キー化する。

**ゼロ除算エッジケース**:

- `expected_total = 0`（期待TSVが空）: `coverage_rate = 1.0`(*), `classification_accuracy = 1.0`(*) として返し、レポートに「期待行が空のため 100% 扱い」と注記する
- `matched_rows = 0`（全件取りこぼし）: `coverage_rate = 0.0`, `classification_accuracy = 0.0` として返す（分類精度は計算不能だが 0% 扱いで明示）
- (*) 期待TSVが空という状態は通常ゴールデンセットの設定ミスなので、サマリで警告も出す

### in-process 呼び出しの実装方針

`grep_helper/cli.py` および `grep_helper/pipeline.py` の構造を確認し、CLI のエントリではなくパイプライン関数を直呼びするのが望ましい。具体的なエントリ点（`run_pipeline()` 等の名前）は writing-plans フェーズで実装計画を作るときに確定させる。

**フォールバック**: in-process 呼び出しが現状 API では困難な場合、`subprocess.run([sys.executable, "analyze.py", ...])` で代替する。差分は計測時間が grep ファイルあたり数百 ms 増える程度で、初版としては許容する。

---

## 出力フォーマット

### stdout サマリ（`--quiet` で抑制可能）

```
=== KPI 計測結果 (java) ===
対象grepファイル: 2件 (777.grep, CODE.grep)

[777.grep]
  網羅率       : 78/80   (97.5%)   取りこぼし2件
  分類精度     : 75/78   (96.2%)   誤分類3件
  false positive: 5件 (KPI算入なし)
  詳細列差分   : 2件 (参照元列のみ)

[CODE.grep]
  網羅率       : 420/420 (100.0%)
  分類精度     : 415/420 (98.8%)
  ...

=== 合計 ===
  網羅率       : 498/500 (99.6%)
  分類精度     : 490/498 (98.4%)
  false positive: 12件

詳細レポート: output/kpi/java-2026-05-03-1530.md
```

### 詳細レポート（Markdown）

`output/kpi/java-<YYYY-MM-DD-HHMM>.md` に書き出す。Markdown を選ぶ理由: GitHub / VS Code でそのままレンダリングできる／差分管理しやすい／後で HTML 変換も容易（要件 F-08 への布石）。タイムスタンプ付きファイル名により実行履歴が残る。

レポートの章構成:

```markdown
# KPI 計測レポート (java) — 2026-05-03 15:30

## サマリ
（stdout と同じ内容を表として）

## 取りこぼし行（網羅率を下げている要因）
| grepファイル | 期待ファイルパス | 期待行番号 | 期待コード行 | 期待使用タイプ |

## 誤分類行（分類精度を下げている要因）
| grepファイル | ファイル | 行 | 期待 | 実際 | 差分カラム |

## false positive（参考、KPI算入なし）
| grepファイル | actual ファイル | 行 | 実際の使用タイプ |

## 詳細列のみの差分（参照元〜列）
（KPIには影響しないが念のため記録）
```

---

## 自テスト戦略

`tests/test_measure_kpi.py` で計測スクリプト本体を単体テストする。プロジェクトのテスト方針（`feedback_test_style.md`: 古典学派・ブラックボックス起点・WHATを検証）と TDD stance（`feedback_tdd_stance.md`）に従う。

| テスト対象 | 方針 |
|---|---|
| `compare()` の網羅率計算 | ブラックボックス: 合成 expected/actual レコード列を渡し、`coverage_rate` を検証 |
| `compare()` の分類精度計算 | ブラックボックス: (file,line) 一致+不一致+部分一致のミックスケース |
| `compare()` の FP 検出 | ブラックボックス: actual のみに存在する行が `false_positives` に入る |
| `load_expected_tsv()` / `load_actual_tsv()` | ブラックボックス: UTF-8 BOM・タブ区切り・空行・想定外カラム数の入力 |
| `format_summary()` / `format_detail_report()` | スナップショット的: 固定 `ComparisonResult` から期待文字列を生成（不安定なら緩める） |
| エンドツーエンド | `tests/golden/java/` の最小サブセットを使い、`run()` を呼んで KPI = 100% / 100% を返すことを検証（ゴールデンセット自体の整合性チェック兼用） |

**ゴールデンセット自体の妥当性**は手動レビューで担保する（合成最小例なので、各サンプルファイルと期待TSV をセットでレビュー可能）。

---

## 実装の依存関係

| 種別 | パス | 内容 |
|---|---|---|
| 新規追加 | `scripts/measure_kpi.py` | 計測スクリプト本体 |
| 新規追加 | `tests/golden/java/src/` | 合成 Java サンプルソース |
| 新規追加 | `tests/golden/java/inputs/` | grep 結果ファイル |
| 新規追加 | `tests/golden/java/expected/` | 期待TSV |
| 新規追加 | `tests/golden/java/README.md` | サンプル設計ノート |
| 新規追加 | `tests/test_measure_kpi.py` | 計測スクリプトの単体/E2Eテスト |
| 変更 | `output/.gitignore`（または新規 `output/kpi/.gitignore`） | `kpi/` を除外 |
| 変更 | `README.md` | KPI 計測の使い方を1セクション追記 |
| 任意変更 | `grep_helper/pipeline.py` | in-process 呼び出し用の薄いエントリ追加（writing-plans で要否確定） |

---

## スコープ外（明示）

- **他言語のゴールデンセット**: C / Kotlin / SQL / その他は別タスク。Java で「サンプル設計テンプレート」を確立してから水平展開する
- **pytest 統合 / CI ゲート**: 独立スクリプト方式に決定済み。要件 §スコープ外の「CI/CD への組み込み」とも整合
- **HTMLレポート（要件 F-08）**: 初版は Markdown 出力で代替。HTML 化は将来
- **性能ベンチマーク**: KPI は精度のみ。処理速度は別軸
- **複数回実行のトレンドグラフ化**: 1回実行 = 1レポート。比較は git diff 等で

---

## 成功条件

1. `python scripts/measure_kpi.py --lang java` を実行すると、Java ゴールデンセットに対する網羅率・分類精度・FP 件数が stdout に表示される
2. `output/kpi/java-<timestamp>.md` に詳細レポートが書き出される
3. 初版のゴールデンセットでは網羅率 100%・分類精度 90% 以上を達成する（要件 §成功指標）
4. `tests/test_measure_kpi.py` が pytest で全件 pass する
5. ゴールデンセット自体は使用タイプ7種を各10件以上カバーし、直接参照・間接参照・getter/setter 経由の各シナリオを少なくとも1件ずつ含む
