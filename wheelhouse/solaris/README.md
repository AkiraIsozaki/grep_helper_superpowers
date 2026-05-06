# Solaris 10 + Python 3.7 用 オフライン install アーカイブ

`grep_helper` を Solaris 10 + Python 3.7.17 環境に**ネットワーク無し**で
セットアップするための source distribution（sdist）一式。

リポジトリ親 `wheelhouse/` は dev container（Linux x86_64 + Python 3.12）用の
バイナリ wheel を含むが、Solaris 10 + cp37 の wheel は配布されていないため
ここでは**全て sdist**で持ち、現地 build する。

## 同梱物

| パッケージ | バージョン | 形式 | 備考 |
|---|---|---|---|
| `chardet` | 5.2.0 | sdist | pure Python。Python 3.7 + で動作 |
| `javalang` | 0.13.0 | sdist | pure Python。`six` に依存 |
| `six` | 1.17.0 | sdist | `javalang` の依存 |
| `pyahocorasick` | 2.0.0 | sdist | C 拡張。Solaris 10 で build 失敗する場合は skip 可（`grep_helper/_aho_corasick.py` の pure Python 実装に自動フォールバック） |

`pyahocorasick` は 2.3.0 が最新だが Python 3.7 サポートを打ち切っているため、
3.7 で build 可能な最終版 **2.0.0** を採用。`requirements.txt` の制約
`pyahocorasick>=2.0.0,<3.0.0` を満たす。

## 使い方（Solaris 10 実機）

`scripts/smoke_solaris.md` の手順 0–2 で gcc / OpenSSL 込みの Python 3.7
を build し venv を作った後、依存をオフライン install する:

```sh
$ source $HOME/grep_helper_venv/bin/activate
$ pip install --no-index --find-links /path/to/wheelhouse/solaris/ \
              chardet javalang
# pyahocorasick は build 失敗しても pure Python フォールバックがあるので || true:
$ pip install --no-index --find-links /path/to/wheelhouse/solaris/ \
              pyahocorasick || true
```

`--no-index` で PyPI を見に行かない、`--find-links <dir>` でローカル sdist
を解決する。`six` は `javalang` の依存として自動解決される。

## なぜ sdist か

Solaris 10 + Python 3.7 用の binary wheel は PyPI に存在しない。
sdist は現地 `gcc` で build するため、OpenCSW gcc + libssl/libffi/zlib が
入っていれば動く（`scripts/smoke_solaris.md` 手順 0 を参照）。

## 更新方法（dev container 上で再取得）

```sh
$ cd wheelhouse/solaris
$ rm -f *.tar.gz
$ python -m pip download --no-binary=:all: --python-version 3.7 \
      --no-deps --dest . \
      chardet==5.2.0 javalang==0.13.0 six==1.17.0 \
      "pyahocorasick>=2.0.0,<3.0.0"
```
