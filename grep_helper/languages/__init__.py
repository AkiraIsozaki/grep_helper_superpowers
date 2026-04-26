"""言語ハンドラレジストリ。

各言語モジュールの ``EXTENSIONS`` / ``SHEBANGS`` を集約し、
``EXT_TO_HANDLER`` / ``SHEBANG_TO_HANDLER`` マップと
``detect_handler(filepath, src_dir) -> ModuleType`` を提供する（Phase 7 で実装）。
"""
