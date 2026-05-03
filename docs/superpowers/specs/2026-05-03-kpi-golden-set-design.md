# KPI ゴールデンセット・計測スクリプト 設計書

**日付**: 2026-05-03
**対象ファイル**:

- `scripts/measure_kpi.py`（新規）
- `tests/golden/<lang>/`（新規, 全12言語）
- `tests/test_measure_kpi.py`（新規）
- `grep_helper/pipeline.py`（in-process エントリ追加）
- `pyproject.toml` または `pytest.ini`（pytest 収集除外）
- `.gitignore`（出力先除外）

---

## 背景・動機

`docs/product-requirements.md` §成功指標(KPI) では以下が定義されている。

- **網羅率**: 既知のテストケース（直接参照・間接参照・getter経由の各パターンを含むサンプル Java ファイル群）で期待TSVの全行が出力に含まれること
- **分類精度**: 7種の使用タイプへの自動分類が一致率 90% 以上（450/500件以上）

しかしこの KPI を継続計測する仕組みは現状なく、コード変更（性能改善・機能追加・防御的修正）が網羅率/精度を維持できているかを定量的に確認する手段がない。直近の binary/oversize 修正（commits a478b3d, 3fb15fa）のような防御的変更でも、効果と副作用を数値で示せない状態にある。

本タスクは、F-first（土台づくり）の方針で KPI 計測の基盤を整備する。これが整うと、後続の B（既存言語の深堀り）/ E（性能改善）の改造を「網羅率を落とさず変えられた」と保証しながら進められる。

---

## ロードマップ上の位置付け

**このタスクは F-first（土台づくり）であり、それ自体がゴールではない。** B（既存言語の深堀り）と E（性能改善）を安全に進めるための前提条件として位置付ける。

### F が整った後に進める方向

#### B: 既存言語の深堀り

- 直接参照のみの言語（Python / TypeScript / Perl / PL/SQL）に間接追跡を追加する
- Java 以外も AST 化を検討する（Kotlin / C# / Groovy など）
- データフロー一歩手前の追跡（定数→定数の連鎖、メソッド戻り値経由）
- Java 慣用句の追加対応（Lombok `@Getter` / record / Builder パターンなど）

#### E: 性能・スケール

- 第1段階（grep 行分類）の並列化（現状は第2段階以降のみ並列）
- 増分処理（前回からの差分 grep 行のみ追跡）
- AST キャッシュのディスク永続化
- 60GB 級ソースでのプロファイリングして真のボトルネック特定

### F-first を起点に選んだ理由

B も E も実装を変えると false negative / false positive を生みやすく、現状その変化を定量化できない。本タスクで KPI 計測を整えると、B/E の各改造で「網羅率を落とさず変えられた」を保証しながら進められる。

### 想定する後続タスクの順序

```
[今回] F: KPI ゴールデンセット + 計測スクリプト
       Java 深堀り（500件超）+ 他11言語スモーク（各6〜11件）
   ↓
[次] 他言語のサンプル件数を Java 同水準まで厚くする
   ↓
[並行 / 後続] B: 直接参照のみ言語への間接追跡追加 ← KPI で精度監視
[並行 / 後続] E: 第1段階並列化 / 増分処理        ← KPI で網羅率維持を検証
```

各タスクは独立した spec / 実装計画で扱う。本 spec はあくまで F の初版（Java 深堀り + 他言語スモーク）に閉じる。

---

## 要件

1. **Java 深堀り**: 全パイプライン段階（直接 → 間接 → getter/setter）を通る Java を最も厚いカバレッジで揃える（要件 §成功指標 を満たす規模）
2. **他11言語のスモークセット**: C / Pro\*C / SQL / Shell / Kotlin / PL/SQL / TypeScript・JS / Python / Perl / C#・VB.NET / Groovy の各言語について、使用タイプを最低1件ずつカバーする最小限のゴールデンセット
3. **合成最小例**: 使用タイプごとに最小限のサンプルを手書きで用意する
4. **独立スクリプト**: pytest 統合や CI ゲートではなく、`python scripts/measure_kpi.py` で任意に実行する
5. **既存資産無変更が原則**: `analyze*.py` 群はそのまま使う。`grep_helper.pipeline` への in-process エントリ追加は許容する（理由は §in-process 呼び出しの実装方針 参照）

---

## アーキテクチャ

### ディレクトリ配置

```
tests/golden/                    # KPI 計測用ゴールデンセットのルート（pytest 収集対象外）
  java/
    src/                         # Java 深堀り (~70サンプルファイル相当)
    inputs/                      # 手書き grep 結果
    expected/                    # 手書き 期待TSV
    README.md                    # サンプル設計ノート
  c/                             # C スモーク
    src/, inputs/, expected/, README.md
  proc/                          # Pro*C スモーク
    src/, inputs/, expected/, README.md
  sql/                           # Oracle SQL スモーク
  sh/                            # Shell スモーク（モジュール名 sh に合わせる）
  kotlin/                        # Kotlin スモーク
  plsql/                         # PL/SQL スモーク
  ts/                            # TypeScript/JS スモーク
  python/                        # Python スモーク
  perl/                          # Perl スモーク
  dotnet/                        # C#/VB.NET スモーク
  groovy/                        # Groovy スモーク
scripts/
  measure_kpi.py                 # 計測スクリプト
output/
  kpi/                           # gitignore（レポート出力先）
```

#### 既存 `tests/fixtures/` との役割分担

リポジトリには既に `tests/fixtures/` が存在し、pytest 単体テスト用の小さな fixture が置かれている。本 spec の `tests/golden/` とは目的が異なる。

| パス | 用途 | 読まれるタイミング |
|---|---|---|
| `tests/fixtures/` | pytest 単体テスト用の固定 fixture ファイル群（小さな入力例） | 各 `test_*.py` から path/glob で参照 |
| `tests/golden/<lang>/` | KPI 計測専用の網羅サンプル（言語別） | `scripts/measure_kpi.py` および E2E テスト1本のみ参照 |

ファイル命名が偶発的に被る可能性があるため、**両者を相互参照しない**こと（同名ファイルがあっても別物として扱う）。

#### inputs/expected ペアリング規約

`tests/golden/<lang>/inputs/<stem>.grep` と `tests/golden/<lang>/expected/<stem>.tsv` は **拡張子を除いた basename が一致するペア**として扱う。例:

- `inputs/777.grep` ↔ `expected/777.tsv`
- `inputs/CODE.grep` ↔ `expected/CODE.tsv`

§計測スクリプト詳細 の内部処理フロー手順2 における「対応の検証」とは、この basename ペアリングのことを指す。

#### pytest 収集対象から外す

`tests/golden/<lang>/src/` に入る `.java` / `.kt` / `.py` 等のソースは、ファイル名が `test_*.py` になることはないため pytest のデフォルト収集ルールでは拾われない。ただし将来 `conftest.py` を誤配置するリスクがあるため、`pyproject.toml`（または `pytest.ini`）に以下を追加する：

```ini
[tool.pytest.ini_options]
norecursedirs = ["tests/golden", ...既存値]
```

### データフロー

```
tests/golden/<lang>/inputs/*.grep
       ↓
[scripts/measure_kpi.py --lang <lang>]
       ↓ importlib で grep_helper.languages.<lang> をロード
       ↓ grep_helper.pipeline.run_full_pipeline() を in-process で起動
       ↓
actual TSV（一時領域に出力）
       ↓
expected TSV と突合
       ↓
output/kpi/<lang>-<YYYYMMDD-HHMMSS>.md（詳細レポート）+ stdout サマリ
```

### サンプル設計の方針

#### Java 深堀り（要件 §成功指標 との対応）

| 要件 | 設計の対応 |
|---|---|
| 網羅率：直接・間接・getter経由・setter経由の各パターン | `777.grep` で全段階を発火させる（`Constants.java` 直接 → `Service.java` 間接 → `Handler.java` getter経由 → `Setter*.java` setter経由） |
| 分類精度：使用タイプ各10件以上、計500件以上 | 7使用タイプ × 10件 = 70件 を `777.grep` 内に作る。`CODE.grep` 等の別文言で件数を増やし、合計500件以上を達成 |
| 「テスト用Javaソース50ファイル」 | **要件「50ファイル」は件数を分散させる目安と解釈**する。実装上は使用タイプ別件数しきい値（各10件以上）を主、ファイル数を従として扱う。20〜30ファイル相当に収める。`tests/golden/java/README.md` にこの解釈を明記する |

#### 他11言語のスモーク要件

各言語は以下の最小カバレッジを満たす：

| 言語 | モジュール名 | 使用タイプ数 | 直接参照 | 間接参照 | getter/setter | 想定総件数 |
|---|---|---|---|---|---|---|
| C | `c` | 6 | 各1件 | #define×1, 変数×1 | — | 約8件 |
| Pro\*C | `proc` | 7 | 各1件 | #define×1, 変数×1 | — | 約9件 |
| Oracle SQL | `sql` | 7 | 各1件 | 同一ファイル内×1 | — | 約8件 |
| Shell | `sh` | 6 | 各1件 | 同一ファイル内×1 | — | 約7件 |
| Kotlin | `kotlin` | 7 | 各1件 | const val×1 | — | 約8件 |
| PL/SQL | `plsql` | 7 | 各1件 | — | — | 約7件 |
| TypeScript / JS | `ts` | 7 | 各1件 | — | — | 約7件 |
| Python | `python` | 6 | 各1件 | — | — | 約6件 |
| Perl | `perl` | 6 | 各1件 | — | — | 約6件 |
| C# / VB.NET | `dotnet` | 7 | 各1件 | const×1, static readonly×1 | — | 約9件 |
| Groovy | `groovy` | 7 | 各1件 | static final×1, フィールド×1 | getter×1, setter×1 | 約11件 |

合計 ~86 件のスモークサンプル。Java 500件超 + スモーク ~86件 = 全体 ~586件 のゴールデンセット。

各言語の使用タイプは `docs/tool-overview.md §4-2` および `docs/product-requirements.md F-02` を正とする。

---

## 計測スクリプト詳細

### CLI インターフェース

```bash
python scripts/measure_kpi.py --lang <name> [--samples-dir tests/golden] [--output-dir output/kpi] [--quiet]
```

| オプション | デフォルト | 説明 |
|---|---|---|
| `--lang` | （必須） | 計測対象言語。`java` / `c` / `proc` / `sql` / `sh` / `kotlin` / `plsql` / `ts` / `python` / `perl` / `dotnet` / `groovy` のいずれか、または `all` で全12言語を順次実行 |
| `--samples-dir` | `tests/golden` | ゴールデンセットのルート |
| `--output-dir` | `output/kpi` | レポート出力先（自動作成） |
| `--quiet` | off | stdout サマリを抑制（詳細レポートは常に出る） |

### 終了コード

`docs/product-requirements.md` §終了コード の規約に合わせる：

- `0`: 計測完了（KPI 結果が要件しきい値割れでも `0` を返す。CIゲートしない方針 = §出力フォーマット で WARN 表示する）
- `1`: 入力エラー（spec 不整合: `inputs/` と `expected/` の対応不一致、対象言語ディレクトリが存在しない、`--lang` の値が未対応 等）
- `2`: 実行時例外（予期しない例外）

### 内部処理フロー

1. `--lang all` の場合は12言語ぶん順次ループ。各言語の処理は以下：
2. `samples-dir/<lang>/` を確認、`inputs/` と `expected/` の対応を検証
   - `inputs/` にあるが `expected/` にない、またはその逆 → exit code `1`
3. handler モジュールをロード:
   ```python
   handler = importlib.import_module(f"grep_helper.languages.{args.lang}")
   ```
4. `tempfile.TemporaryDirectory()` で actual TSV の出力先を作成
5. `grep_helper.pipeline.run_full_pipeline()`（新規追加、§in-process 呼び出しの実装方針 参照）を in-process で起動：
   - `source_dir = samples_dir/<lang>/src`
   - `input_dir = samples_dir/<lang>/inputs`
   - `output_dir = <tmp>`
   - `handler = <ロード済みモジュール>`
   - `workers = 1`
6. `inputs/` 内の各 `.grep` ごとに actual と expected を突合してメトリクスを算出
7. メトリクスを集計してレポートを書き出し

### in-process 呼び出しの実装方針

現状の `grep_helper/cli.py` の `run(handler)` は `argparse.parse_args()` 内部で `sys.argv` を読むため、in-process から source/input/output ディレクトリを切り替えて呼ぶには新しいエントリ関数の追加が**ほぼ確実に必要**。

**本 spec は (a) を採用する前提でフローを記述している**（上記 §内部処理フロー の手順5）。writing-plans フェーズでは (a) の API シグネチャを最終確定する：

- **(a) 採用**: `grep_helper/pipeline.py` に `run_full_pipeline(source_dir, input_dir, output_dir, handler, workers=1)` を追加する。既存 `process_grep_file` + 間接追跡 + getter/setter 追跡の3段階を1関数に集約し、KPI スクリプトと CLI の両方から再利用できる構造にする。`cli.run()` も内部でこの関数を呼ぶようにリファクタすると重複も避けられる
- **(b) 代替案**: `grep_helper/cli.py` の `run()` を引数化（`run(handler, args=None)` で `args` 省略時のみ `parse_args()` を呼ぶ）。writing-plans で (a) が困難と判明したときのバックアッププラン

(a) の方が API 表面を限定でき、KPI スクリプトとの結合が薄くなるため採用。

**フォールバック**: どちらも実装が困難な場合、`subprocess.run([sys.executable, "analyze.py", ...])` で代替する。差分は計測時間が grep ファイルあたり数百 ms 増える程度で、初版としては許容する。

### モジュール責務分割

スクリプトは1ファイル `scripts/measure_kpi.py` に書くが、内部関数で責務を分ける（テスト容易性のため）。

| 関数 | 責務 |
|---|---|
| `load_expected_tsv(path) -> list[Record]` | 期待TSVをパースして `GrepRecord` 互換のレコードに変換 |
| `load_actual_tsv(path) -> list[Record]` | 同上（既存 `grep_helper.tsv_output` のスキーマと整合） |
| `compare(expected, actual) -> ComparisonResult` | 2つのレコード集合から KPI と diff を算出 |
| `assert_coverage_distribution(expected, lang_spec) -> list[Warning]` | ゴールデンセット自体の分布チェック（後述） |
| `format_summary(result, thresholds) -> str` | stdout 用のサマリ。WARN/OK ラベル付き |
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
    missing_rows: list[Record]              # 取りこぼし
    false_positives: list[Record]           # 余計な行
    misclassified: list[tuple[Record, Record]]  # (file, line)一致で分類不一致
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

### ゴールデンセット自体の分布チェック

`assert_coverage_distribution(expected, lang_spec) -> list[Warning]` でゴールデンセットの設計ミス（使用タイプの取りこぼし、シナリオの抜け）を検出する。

**入力**:

- `expected`: 期待TSV からロードしたレコード列
- `lang_spec`: 言語ごとの期待カバレッジ（`{"usage_types": [...], "min_per_type": 1, "indirect_required": True, ...}`）

**出力**: 警告メッセージ列。空なら OK。

**例（Java）**:

```python
JAVA_SPEC = {
    "usage_types": ["アノテーション", "定数定義", "変数代入", "条件判定",
                    "return文", "メソッド引数", "その他"],
    "min_per_type": 10,                    # Java 深堀りは10件しきい値
    "reference_kinds_required": ["直接", "間接", "間接（getter経由）", "間接（setter経由）"],
}
```

**例（C のスモーク）**:

```python
C_SPEC = {
    "usage_types": ["#define定数定義", "条件判定", "return文",
                    "変数代入", "関数引数", "その他"],
    "min_per_type": 1,
    "reference_kinds_required": ["直接", "間接"],
}
```

各言語の `lang_spec` は `scripts/measure_kpi.py` 内に定数として持つ（外部 YAML 等は使わず、hard-coded で十分。言語数が12と限定的なため）。

### 期待TSV の手書きルール

期待TSV を手書きで作成する際は以下のルールに従う：

1. **エンコーディング**: UTF-8 BOM 付き（`grep_helper.tsv_output` が `utf-8-sig` で書くのと整合）
2. **区切り**: タブ文字（スペースではない）
3. **行終端**: LF または CRLF どちらでも可（Python の `csv.reader` は両対応）
4. **ヘッダ行**: 必須。`grep_helper.tsv_output._TSV_HEADERS` と完全一致すること（9列）
5. **カラム数**: 9列（文言・参照種別・使用タイプ・ファイルパス・行番号・コード行・参照元変数名・参照元ファイル・参照元行番号）
6. **行番号の型**: 文字列として比較する。`load_*_tsv` は str のまま保持し、`compare()` でも str 同士で比較する
7. **間接参照行**: 「参照元変数名・参照元ファイル・参照元行番号」3列を埋める。直接参照行ではこれら3列は空文字
8. **コード行のクォート**: 内部にタブ・改行・ダブルクォートを含む場合は `csv` 規約（QUOTE_MINIMAL）に従う

期待TSV を新規作成しやすくするため、初期サンプルは「ツールの実行結果を一度確認 → 内容を**人間が**レビュー → expected/ にコピー」する半自動方式でもよい。ただし**期待TSVをそのままツール出力で生成すると検証にならない**ため、必ず人間がレビューして「これが正解である」と確認した上で `expected/` に置く。

---

## 出力フォーマット

### stdout サマリ（`--quiet` で抑制可能）

```
=== KPI 計測結果 (java) ===
対象grepファイル: 2件 (777.grep, CODE.grep)

[777.grep]
  網羅率       : 78/80   (97.5%)   [WARN: 100% 未達 / 取りこぼし2件]
  分類精度     : 75/78   (96.2%)   [OK: 90%以上達成]
  false positive: 5件 (KPI算入なし)
  詳細列差分   : 2件 (参照元列のみ)

[CODE.grep]
  網羅率       : 420/420 (100.0%) [OK]
  分類精度     : 415/420 (98.8%)  [OK]
  ...

=== 合計 (java) ===
  網羅率       : 498/500 (99.6%)  [WARN: 100% 未達]
  分類精度     : 490/498 (98.4%)  [OK: 90%以上達成]
  false positive: 12件
  サンプル分布 : 7使用タイプ × ≧10件 → ✅ OK
                直接 / 間接 / getter / setter → ✅ 全カバー

詳細レポート: output/kpi/java-20260503-153045.md
```

要件 §成功指標 のしきい値（網羅率 100% / 分類精度 90%）に対する到達状況を **WARN/OK で表示**するが、**終了コードには反映しない**。CIゲートしない方針と整合。

### 詳細レポート（Markdown）

`output/kpi/<lang>-<YYYYMMDD-HHMMSS>.md` に書き出す。秒精度のため、同一分内の再実行でも上書きされない。Markdown を選ぶ理由: GitHub / VS Code でそのままレンダリングできる／差分管理しやすい／後で HTML 変換も容易（要件 F-08 への布石）。

レポートの章構成:

```markdown
# KPI 計測レポート (java) — 2026-05-03 15:30:45

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

## サンプル分布チェック警告
（assert_coverage_distribution の結果）
```

`--lang all` の場合は言語ごとに別ファイルを出力（`java-...md`、`c-...md`、…12本）し、最後に `_summary-<timestamp>.md` で全言語のサマリを1ファイルにまとめる。

---

## 自テスト戦略

`tests/test_measure_kpi.py` で計測スクリプト本体を単体テストする。プロジェクトのテスト方針（`feedback_test_style.md`: 古典学派・ブラックボックス起点・WHATを検証・**テストメソッド名は日本語**）と TDD stance（`feedback_tdd_stance.md`: TDD 推奨）に従う。

| テスト対象 | 方針 |
|---|---|
| `compare()` の網羅率計算 | ブラックボックス: 合成 expected/actual レコード列を渡し、`coverage_rate` を検証。テスト名例: `test_期待行と実際の行が完全一致するとき網羅率は1_0` |
| `compare()` の分類精度計算 | ブラックボックス: (file,line) 一致+不一致+部分一致のミックスケース |
| `compare()` の FP 検出 | ブラックボックス: actual のみに存在する行が `false_positives` に入る |
| `compare()` のゼロ除算 | `expected_total = 0` で coverage_rate=1.0 / `matched_rows = 0` で 0.0 を返すこと |
| `assert_coverage_distribution()` | ブラックボックス: 使用タイプが満たされている / 不足している場合の警告生成 |
| `load_expected_tsv()` / `load_actual_tsv()` | ブラックボックス: UTF-8 BOM・タブ区切り・空行・想定外カラム数の入力 |
| `format_summary()` / `format_detail_report()` | **完全一致のスナップショットは取らない**。「主要数値（網羅率・分類精度・FP件数）が文字列に含まれる」「WARN/OK ラベルが正しい条件で出る」レベルで検証（`feedback_test_style §5` 変更耐性と整合） |
| エンドツーエンド | `tests/golden/java/` の最小サブセットを使い、`run()` を呼んで KPI = 100% / 100% を返すことを検証（ゴールデンセット自体の整合性チェック兼用）。各言語ぶん最低1つの E2E テストを書く |

**ゴールデンセット自体の妥当性**は手動レビューで担保する（合成最小例なので、各サンプルファイルと期待TSVをセットでレビュー可能）。さらに `assert_coverage_distribution()` で「使用タイプが揃っているか」だけは自動チェックする。

---

## 言語別 README.md の骨子

各 `tests/golden/<lang>/README.md` は以下のテンプレートに従う：

```markdown
# <Language> ゴールデンセット

## 役割
このディレクトリは <Language> の KPI 計測用ゴールデンセット。
区分: <Java は深堀り / 他言語はスモーク>

## 使用タイプ × サンプルファイル マトリクス
| 使用タイプ | サンプルファイル | 該当行 | 件数 |
|---|---|---|---|
| 定数定義 | Constants.java | 10 | 1 |
| 条件判定 | Service.java | 20-30 | 5 |
...

（Java は §50ファイル目安の独自解釈の注記もここに含める）

## grep ファイル一覧
| ファイル | 文言 | 役割 |
|---|---|---|
| 777.grep | 777 | 使用タイプ網羅 |
| CODE.grep | CODE | 件数稼ぎ・間接シナリオ |

## 期待TSV 手書きルール
共通 spec を参照: `docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md` §期待TSV の手書きルール

## サンプル追加手順
1. 該当言語のソースファイルに新パターンを追加
2. `grep -rn "<文言>" src/` で grep ファイルを再生成（または手書き）
3. 期待TSV を手で更新（ツール出力をベースに人間がレビュー）
4. `python scripts/measure_kpi.py --lang <lang>` で 100% を確認
```

---

## 実装の依存関係

| 種別 | パス | 内容 |
|---|---|---|
| 新規追加 | `scripts/measure_kpi.py` | 計測スクリプト本体 |
| 新規追加 | `tests/golden/java/{src,inputs,expected,README.md}` | Java 深堀り |
| 新規追加 | `tests/golden/{c,proc,sql,sh,kotlin,plsql,ts,python,perl,dotnet,groovy}/{src,inputs,expected,README.md}` | 他11言語スモーク |
| 新規追加 | `tests/test_measure_kpi.py` | 計測スクリプトの単体/E2Eテスト |
| 必須変更 | `grep_helper/pipeline.py` | `run_full_pipeline()` を追加（in-process エントリ） |
| 任意変更 | `grep_helper/cli.py` | `run()` を新エントリ経由にリファクタ（重複削減） |
| 変更 | `pyproject.toml` または `pytest.ini` | `norecursedirs` に `tests/golden` を追加 |
| 変更 | `.gitignore` | `output/kpi/` を除外 |
| 変更 | `README.md` | KPI 計測の使い方を1セクション追記 |

---

## スコープ外（明示）

- **言語ごとの件数を Java と同水準まで厚くすること**: 他11言語はスモーク（最小カバレッジ）にとどめる。各言語の件数を Java 並みに厚くするのは後続タスク
- **pytest 統合 / CI ゲート**: 独立スクリプト方式に決定済み。要件 §スコープ外の「CI/CD への組み込み」とも整合
- **HTMLレポート（要件 F-08）**: 初版は Markdown 出力で代替。HTML 化は将来
- **性能ベンチマーク**: KPI は精度のみ。処理速度は別軸
- **複数回実行のトレンドグラフ化**: 1回実行 = 1レポート。比較は git diff 等で
- **既存 `tests/fixtures/` のリストラ**: 本タスクでは `tests/golden/` を新設するだけで、既存 fixtures は無変更

---

## 成功条件

1. `python scripts/measure_kpi.py --lang java` で Java の網羅率・分類精度・FP 件数が stdout に表示される
2. 同様に他11言語（`c` / `proc` / `sql` / `sh` / `kotlin` / `plsql` / `ts` / `python` / `perl` / `dotnet` / `groovy`）でも実行できる
3. `python scripts/measure_kpi.py --lang all` で全12言語を順次実行できる
4. `output/kpi/<lang>-<timestamp>.md` に詳細レポートが書き出される（タイムスタンプ秒精度）
5. **Java**: 網羅率 100%・分類精度 90% 以上を達成（要件 §成功指標）
6. **他11言語**: 各言語のスモークセットで網羅率 100% を達成（少サンプルなので分類精度も 100% を目指す。未達は WARN 表示）
7. `tests/test_measure_kpi.py` が pytest で全件 pass する
8. ゴールデンセット自体は各言語の使用タイプを最低1件カバーし、間接追跡対応言語は間接シナリオを少なくとも1件含む（Java/Groovy は getter・setter も含む）
9. `assert_coverage_distribution()` が全言語のゴールデンセットに対して警告ゼロ
