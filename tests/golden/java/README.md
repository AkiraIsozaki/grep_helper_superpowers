# Java ゴールデンセット

## 役割
このディレクトリは Java の KPI 計測用ゴールデンセット。区分: **深堀り**（要件 §成功指標 を満たす規模）。

## 状態
- 本番規模: 各使用タイプ ≥10件、合計 500件超（actual 515 件）
- 直接参照 + 間接参照（定数経由 / フィールド経由 / ローカル変数経由） + getter経由 + setter経由 をすべてカバー
- AST ベース分類が全 21 ファイルで稼働（フォールバック 0 件）

## 使用タイプ × サンプルファイル マトリクス
| 使用タイプ | 件数 | 主な配置先 |
|---|---|---|
| 定数定義 | 39 | Constants.java, Status.java, Demo.java, BigConstants.java |
| アノテーション | 63 | Annotated.java, BigAnnotated.java |
| 条件判定 | 69 | Service.java, BigService.java, Handler.java, Demo.java |
| 変数代入 | 70 | Setter.java, BigSetter.java, Mutator.java, Handler.java, Entity.java |
| return文 | 70 | Validator.java, Returner.java, BigValidator.java, Demo.java |
| メソッド引数 | 136 | Caller.java, BigCaller.java, MoreCallers.java, Demo.java |
| その他 | 68 | Comments.java, BigComments.java（コメント中の "777"） |
| 合計 | 515 | 21 ファイル |

## 参照種別シナリオ
| シナリオ | 件数 | 配置 |
|---|---|---|
| 直接 | 436 | 全サンプルファイル |
| 間接（定数経由 / フィールド経由 / ローカル変数経由） | 73 | Constants.CODE → Service / Demo, Entity.type フィールド, Handler/Mutator のローカル変数 |
| 間接（getter経由） | 3 | Entity.getType() → Handler |
| 間接（setter経由） | 3 | Entity.setType(value) → Mutator |

## grep ファイル一覧
| ファイル | 文言 | 役割 |
|---|---|---|
| 777.grep | 777 | 主要キーワード。直接参照と間接参照（定数 / フィールド / ローカル変数 / getter / setter）をすべてカバー |
| CODE.grep | CODE | 定数名そのものを検索したケース。Constants.CODE 経由の間接参照も含む |

## ファイル一覧（src/ 配下、21 ファイル）

bootstrap（Task 14 由来）:
- Demo.java — 各使用タイプ 1 件ずつの最小サンプル

定数定義 / 間接参照（定数経由）:
- Constants.java — `static final String CODE = "777"` 等を 12 件定義
- Status.java — 別クラスの定数定義 3 件
- BigConstants.java — `C01`〜`C20` の追加定数 20 件

条件判定:
- Service.java — `if (x.equals("777"))` / `Constants.CODE` 経由 等 12 件
- BigService.java — 50 メソッドの条件判定

return文:
- Validator.java — `return "777"` 12 件
- Returner.java — 簡潔な `return` 5 件
- BigValidator.java — 50 メソッドの return

変数代入:
- Setter.java — ローカル変数代入 12 件
- BigSetter.java — 50 メソッドのローカル変数代入

メソッド引数:
- Caller.java — `System.out.println("777")` 等 12 件
- BigCaller.java — 50 メソッドの引数渡し
- MoreCallers.java — `new StringBuilder("777")` 等 ClassCreator 5 件

アノテーション:
- Annotated.java — `@Tag("777")` 12 件
- BigAnnotated.java — 50 メソッドのアノテーション

その他（コメント中の "777"）:
- Comments.java — `// 777 のコメント` 12 件
- BigComments.java — 50 行のコメント + inline コメント

getter / setter シナリオ:
- Entity.java — `private String type = "777"` フィールド + getter/setter
- Handler.java — `entity.getType()` 経由（getter シナリオ）
- Mutator.java — `entity.setType(value)` 経由（setter シナリオ）

## 期待TSV 手書きルール
共通 spec を参照: `docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md` §期待TSV の手書きルール

本ディレクトリの expected TSV は **ツール出力（`analyze.py`）を採用ベース**に置いている。
これは「bootstrap」「現状を保つ」サンプル的位置づけで、後続の改造で差分が生じたら検出するベースライン。

expected TSV は `analyze.py` の出力をそのまま保存している（dedup なし）。
同じ行に複数の参照種別が出る場合（例: 直接 + 間接（setter経由））、各行をそのまま記録する。
KPI 計測の compare() は spec §出力フォーマット 比較ロジック に従い
`(ファイルパス, 行番号, 参照種別)` を2次キーとしてマッチングするため、
重複行があってもデデュープせずに突合できる。

## サンプル追加手順
1. `src/` に新パターンの Java を追加
2. `cd tests/golden/java/src && grep -rn "<文言>" . | sed 's|^\./||' > ../inputs/<文言>.grep`
3. `python analyze.py --source-dir tests/golden/java/src --input-dir tests/golden/java/inputs --output-dir /tmp/out`
4. 出力された TSV をそのまま expected/ にコピー（dedup 不要）
5. `python scripts/measure_kpi.py --lang java` で網羅率 100% / 分類精度 100% / 警告ゼロ を確認

## 50ファイル目安の独自解釈
要件 §成功指標 「テスト用Javaソース50ファイル」は、件数を分散させる目安として解釈する。
実装上は使用タイプ別件数しきい値（各10件以上）と総件数（500件以上）を主、ファイル数を従として扱う。
本セットは 21 ファイルで 515 件を確保している。
