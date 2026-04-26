"""grep-helper パッケージ。

各言語アナライザの共通インフラとディスパッチャーを提供する。

ハンドラ契約（module = handler、duck typing）:
- 必須: ``EXTENSIONS: tuple[str, ...]``
- 必須: ``classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str``
- 任意: ``batch_track_indirect(direct_records, src_dir, encoding, *, workers=1) -> list[GrepRecord]``
- 任意: ``SHEBANGS: tuple[str, ...]``  (拡張子のないシバン判定用)
"""
