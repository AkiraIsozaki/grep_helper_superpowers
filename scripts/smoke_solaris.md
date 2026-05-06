# Solaris 10 + Python 3.7 スモーク手順

`grep_helper` を Solaris 10 + Python 3.7.17 (cc 自前ビルド + venv 構成) で動かす際の確認手順。
spec: `docs/superpowers/specs/2026-05-06-perf-and-solaris-compat-design.md`

## 0. 前提パッケージ（OpenCSW から導入）

Solaris 10 同梱の Studio cc は Python 3.7 setup.py の前提から外れるため OpenCSW の gcc を使う。

```sh
$ /opt/csw/bin/pkgutil -y -i gcc4core gcc4g++ libssl_dev zlib_dev libffi_dev \
                              gnumake coreutils
```

## 1. Python 3.7.17 ビルド

`--with-openssl` を渡さないと `ssl` モジュールが無効化され `pip install` の TLS 接続が失敗する。

```sh
$ tar xzf Python-3.7.17.tgz && cd Python-3.7.17
$ CC=/opt/csw/bin/gcc \
  CFLAGS="-I/opt/csw/include" \
  LDFLAGS="-L/opt/csw/lib -R/opt/csw/lib" \
  ./configure --prefix=$HOME/py37 --enable-shared \
              --with-openssl=/opt/csw \
              --with-system-ffi
$ gmake -j4 && gmake install
```

## 2. venv 作成

```sh
$ $HOME/py37/bin/python3 -m venv $HOME/grep_helper_venv
$ source $HOME/grep_helper_venv/bin/activate
$ pip install --upgrade pip   # SSL が通れば成功
```

## 3. 依存インストール

cp312 wheel は Solaris で使えないため source build。

```sh
$ pip install --no-binary=:all: chardet javalang
# pyahocorasick の C 拡張は Solaris 10 の libc で通らない場合がある。
# 失敗しても run-time には grep_helper/_aho_corasick.py の pure Python
# フォールバックがあるので、|| true で無視して構わない。
$ pip install --no-binary=:all: pyahocorasick || true
```

## 4. ulimit 引き上げ

`--workers >= 2` を使う場合、`ProcessPoolExecutor` × `mmap` 同時オープン数で
Solaris 10 デフォルトの `nofiles(soft)=256` に当たる現実性がある。

```sh
$ ulimit -n 1024     # ユーザ shell の soft limit
# それ以上必要なら hard limit (デフォルト 65536) まで上げられる:
$ ulimit -n 4096
# zone 内で hard limit が 256 のままに見える場合は projmod / /etc/system の
#   set rlim_fd_cur = 4096
# で root 側調整が必要。
```

## 5. スモーク実行

```sh
$ python analyze_all.py --source-dir <path> \
    --input-dir input --output-dir output --no-mmap
```

## 6. 既知の制約・確認ポイント

- **NFS + mmap**: Solaris + NFS では `--no-mmap` または `GREP_HELPER_NO_MMAP=1` を推奨。
  NFS の stat キャッシュ古値で `mmap` 後に EOF を超えるエラーが出る事例あり。
- **zone CPU**: 実機の zone 内では `os.cpu_count()` が物理 CPU 数を返し `psrinfo` の
  制限を無視するので、`--workers` は明示指定する。
- **シンボリックリンクループ**: `/proc` 参照や NFS 自己参照を踏むと Python 3.7 の
  `pathlib.rglob` は `RecursionError` を出す。`--source-dir` に怪しいリンクが
  無いことを事前に確認すること。
- **shebang**: `analyze_*.py` は直接 `python analyze_all.py` で起動するため
  shebang は気にしなくてよい。直接実行したい場合は venv の `python3` が PATH
  に通っていることを確認。
