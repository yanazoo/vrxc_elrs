#!/bin/bash
# vrxc_elrs インストール / アップデートスクリプト
#
# 使い方:
#   bash <(curl -fsSL https://raw.githubusercontent.com/yanazoo/vrxc_elrs/master/tools/install.sh)
#
# オプション（環境変数でも指定可）:
#   --dir=PATH    インストール先を明示指定        (VRXC_PLUGIN_DIR)
#   --ref=REF     取得するブランチ / タグ         (VRXC_REF, 既定: master)
#   --dry-run     何もせず検出結果だけ表示        (VRXC_DRY_RUN=1)
#   --no-restart  RotorHazard を再起動しない      (VRXC_NO_RESTART=1)
#
# 設計方針:
#   インストール先をハードコードせず、RotorHazard 本体の場所から導出する。
#   ユーザー名やディレクトリ構成が変わっても（NuclearHazard 4.4 で
#   NuclearHazard → nuclear に変更された等）動作する。

set -uo pipefail

OWNER_REPO="yanazoo/vrxc_elrs"
PLUGIN_SUBPATH="custom_plugins/vrxc_elrs"
PLUGIN_NAME="vrxc_elrs"

REF="${VRXC_REF:-master}"
DEST="${VRXC_PLUGIN_DIR:-}"
DRY_RUN="${VRXC_DRY_RUN:-0}"
NO_RESTART="${VRXC_NO_RESTART:-0}"

usage() {
    cat <<'EOF'
vrxc_elrs インストーラー

使い方:
  bash <(curl -fsSL https://raw.githubusercontent.com/yanazoo/vrxc_elrs/master/tools/install.sh)

オプション（環境変数でも指定可）:
  --dir=PATH     インストール先を明示指定       (VRXC_PLUGIN_DIR)
  --ref=REF      取得するブランチ / タグ        (VRXC_REF, 既定: master)
  --dry-run      何もせず検出結果だけ表示       (VRXC_DRY_RUN=1)
  --no-restart   RotorHazard を再起動しない     (VRXC_NO_RESTART=1)
  -h, --help     この使い方を表示

インストール先はハードコードせず RotorHazard 本体の場所から導出するため、
ユーザー名やディレクトリ構成が違っても動作します。
EOF
}

for arg in "$@"; do
    case "$arg" in
        --dir=*)     DEST="${arg#*=}" ;;
        --ref=*)     REF="${arg#*=}" ;;
        --dry-run)   DRY_RUN=1 ;;
        --no-restart) NO_RESTART=1 ;;
        -h|--help)   usage; exit 0 ;;
        *) echo "不明なオプション: $arg（--help で使い方を表示）" >&2; exit 2 ;;
    esac
done

RAW="https://raw.githubusercontent.com/$OWNER_REPO/$REF/$PLUGIN_SUBPATH"
TREE_API="https://api.github.com/repos/$OWNER_REPO/git/trees/$REF?recursive=1"

TMP=""
cleanup() { [ -n "$TMP" ] && rm -rf "$TMP"; }
trap cleanup EXIT

die() { echo "" >&2; echo "エラー: $*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

echo "=== vrxc_elrs インストーラー ==="
echo ""

# ---------------------------------------------------------------------------
# ダウンロード手段
# ---------------------------------------------------------------------------

if have curl; then
    fetch()    { curl -fsSL --max-time 30 "$1"; }
    fetch_to() { curl -fsSL --max-time 30 -o "$1" "$2"; }
elif have wget; then
    fetch()    { wget -qO- --timeout=30 "$1"; }
    fetch_to() { wget -q --timeout=30 -O "$1" "$2"; }
else
    die "curl または wget が必要です"
fi

PY=""
for c in python3 python; do have "$c" && { PY="$c"; break; }; done

# ---------------------------------------------------------------------------
# ステップ1: RotorHazard の場所を特定する
# ---------------------------------------------------------------------------

echo "[1/5] RotorHazard を検出..."

RH_ROOT=""        # 例: /home/nuclear/RotorHazard
SVC_NAME=""
SVC_USER=""

# サービス名を特定（イメージによって名前が違う場合に備える）
for s in rotorhazard RotorHazard nuclearhazard; do
    if systemctl list-unit-files "$s.service" >/dev/null 2>&1 \
       && systemctl cat "$s.service" >/dev/null 2>&1; then
        SVC_NAME="$s"; break
    fi
done

is_rh_root() { [ -f "$1/src/server/server.py" ]; }

# (a) 稼働中サービスの WorkingDirectory から導出するのが最も確実
if [ -n "$SVC_NAME" ]; then
    SVC_USER="$(systemctl show "$SVC_NAME" -p User --value 2>/dev/null)"
    wd="$(systemctl show "$SVC_NAME" -p WorkingDirectory --value 2>/dev/null)"
    if [ -n "$wd" ] && [ -f "$wd/server.py" ]; then
        RH_ROOT="${wd%/src/server}"
        [ "$RH_ROOT" = "$wd" ] && RH_ROOT="$wd"   # 想定外の構成はそのまま使う
        echo "  サービス: $SVC_NAME (WorkingDirectory から検出)"
    fi
fi

# (b) よくある場所を順に確認
if [ -z "$RH_ROOT" ]; then
    for cand in "$HOME/RotorHazard" /home/*/RotorHazard /opt/RotorHazard \
                /srv/RotorHazard /usr/local/RotorHazard; do
        if is_rh_root "$cand"; then RH_ROOT="$cand"; break; fi
    done
fi

# (c) 最後の手段: 深さを限って探索
if [ -z "$RH_ROOT" ]; then
    echo "  一般的な場所に無いため探索中..."
    found="$(find /home /opt /srv /usr/local -maxdepth 6 -type f \
             -path '*/src/server/server.py' 2>/dev/null | head -1)"
    [ -n "$found" ] && RH_ROOT="${found%/src/server/server.py}"
fi

if [ -z "$RH_ROOT" ] && [ -z "$DEST" ]; then
    cat >&2 <<'EOF'

エラー: RotorHazard のインストール先を特定できませんでした

RotorHazard が入っているか確認してください。入っている場合は、
プラグインディレクトリを直接指定してインストールできます:

  bash <(curl -fsSL https://raw.githubusercontent.com/yanazoo/vrxc_elrs/master/tools/install.sh) \
    --dir=/path/to/plugins

場所が分からない場合は、以下の出力を添えてご連絡ください:

  systemctl show rotorhazard -p WorkingDirectory -p User
  ls -d /home/*/RotorHazard /home/*/rh-data 2>/dev/null
EOF
    exit 1
fi

[ -n "$RH_ROOT" ] && echo "  RotorHazard: $RH_ROOT"

# ---------------------------------------------------------------------------
# ステップ2: プラグインの設置先を決める
# ---------------------------------------------------------------------------

echo "[2/5] プラグインの設置先を決定..."

DATA_DIR=""
if [ -n "$RH_ROOT" ]; then
    # NuclearHazard 系は RotorHazard と同階層に rh-data を置く
    parent="$(dirname "$RH_ROOT")"
    for d in "$parent/rh-data" "$RH_ROOT/../rh-data" /home/*/rh-data; do
        [ -d "$d" ] && { DATA_DIR="$(cd "$d" && pwd)"; break; }
    done
fi

PLUGIN_BASE=""
REASON=""
if [ -n "$DEST" ]; then
    PLUGIN_BASE="${DEST%/$PLUGIN_NAME}"
    REASON="明示指定"
elif [ -n "$DATA_DIR" ] && [ -d "$DATA_DIR/plugins" ]; then
    PLUGIN_BASE="$DATA_DIR/plugins"
    REASON="既存の rh-data/plugins"
elif [ -n "$RH_ROOT" ] && [ -d "$RH_ROOT/src/server/custom_plugins" ]; then
    PLUGIN_BASE="$RH_ROOT/src/server/custom_plugins"
    REASON="既存の custom_plugins"
elif [ -n "$DATA_DIR" ]; then
    PLUGIN_BASE="$DATA_DIR/plugins"
    REASON="rh-data 配下に新規作成（本体更新で消えない）"
elif [ -n "$RH_ROOT" ]; then
    PLUGIN_BASE="$RH_ROOT/src/server/custom_plugins"
    REASON="custom_plugins を新規作成"
else
    die "設置先を決定できませんでした"
fi

TARGET="$PLUGIN_BASE/$PLUGIN_NAME"
echo "  → $TARGET"
echo "    （根拠: $REASON）"

# 同じ場所に他のプラグインがあれば、設置先が正しい裏付けになる
if [ -d "$PLUGIN_BASE" ]; then
    others="$(find "$PLUGIN_BASE" -maxdepth 2 -name manifest.json 2>/dev/null \
              | grep -v "/$PLUGIN_NAME/" | wc -l)"
    [ "$others" -gt 0 ] && echo "    （同じ場所に他のプラグイン $others 件を確認）"
fi

# 書き込みに sudo が必要か判定
probe="$PLUGIN_BASE"
while [ -n "$probe" ] && [ ! -e "$probe" ]; do probe="$(dirname "$probe")"; done
NEED_SUDO=0
[ -w "$probe" ] || NEED_SUDO=1
priv() { if [ "$NEED_SUDO" = 1 ]; then sudo "$@"; else "$@"; fi; }
[ "$NEED_SUDO" = 1 ] && echo "    （書き込みに sudo を使用）"

if [ "$DRY_RUN" = 1 ]; then
    echo ""
    echo "=== --dry-run: 検出のみで終了しました ==="
    exit 0
fi

# ---------------------------------------------------------------------------
# ステップ3: 一時ディレクトリへ取得
# ---------------------------------------------------------------------------

echo "[3/5] ファイルを取得 (ref: $REF)..."

TMP="$(mktemp -d)"
STAGE="$TMP/$PLUGIN_NAME"
mkdir -p "$STAGE"

# リポジトリのファイル一覧を API から取得する。
# 将来ファイルが増減しても追随できるようにするため。失敗時は既知の一覧を使う。
FILES=""
if [ -n "$PY" ]; then
    FILES="$(fetch "$TREE_API" 2>/dev/null | "$PY" -I -c '
import json, sys
prefix = "'"$PLUGIN_SUBPATH"'/"
try:
    tree = json.load(sys.stdin).get("tree", [])
except Exception:
    sys.exit(1)
out = [e["path"][len(prefix):] for e in tree
       if e.get("type") == "blob" and e.get("path", "").startswith(prefix)]
if not out:
    sys.exit(1)
print("\n".join(sorted(out)))
' 2>/dev/null)"
fi

if [ -n "$FILES" ]; then
    echo "  ファイル一覧を API から取得: $(printf '%s\n' "$FILES" | wc -l) 件"
else
    echo "  API が使えないため既知の一覧を使用"
    FILES="__init__.py
elrs_backpack.py
connections.py
msp.py
manifest.json
locale/ja.json"
fi

while IFS= read -r f; do
    [ -z "$f" ] && continue
    echo "  → $f"
    mkdir -p "$STAGE/$(dirname "$f")"
    fetch_to "$STAGE/$f" "$RAW/$f" || die "ダウンロード失敗: $f"
done <<< "$FILES"

# ---------------------------------------------------------------------------
# ステップ4: 検証してから設置（壊れたものを本番に置かない）
# ---------------------------------------------------------------------------

echo "[4/5] 検証して設置..."

for must in __init__.py manifest.json; do
    [ -s "$STAGE/$must" ] || die "$must が取得できていません"
done

if [ -n "$PY" ]; then
    "$PY" -I -c '
import json, sys, pathlib
root = pathlib.Path(sys.argv[1])
json.loads((root / "manifest.json").read_text())
for p in root.rglob("*.json"):
    json.loads(p.read_text())
for p in root.rglob("*.py"):
    # 構文検査のみ。py_compile はバイトコードを書き出すので使わない
    compile(p.read_text(), str(p), "exec")
' "$STAGE" || die "取得したファイルの検証に失敗しました（設置していません）"
    echo "  構文・JSON 検証: OK"
    find "$STAGE" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
fi

priv mkdir -p "$PLUGIN_BASE" || die "ディレクトリを作成できません: $PLUGIN_BASE"

# 既存をバックアップしてから入れ替える（まるごと差し替えで古いファイルを残さない）
# 退避先は plugins ディレクトリの外に置く。中に残すと manifest.json を持つ
# ディレクトリが増え、RotorHazard が旧版を二重に読み込んでしまう。
BACKUP=""
BACKUP_BASE="$(dirname "$PLUGIN_BASE")/.${PLUGIN_NAME}-backup"
if [ -d "$TARGET" ]; then
    priv mkdir -p "$BACKUP_BASE" || die "退避先を作成できません: $BACKUP_BASE"
    BACKUP="$BACKUP_BASE/$(date +%Y%m%d%H%M%S)"
    priv mv "$TARGET" "$BACKUP" || die "既存プラグインを退避できません"
    echo "  既存を退避: $BACKUP"
fi

if ! priv cp -r "$STAGE" "$TARGET"; then
    if [ -n "$BACKUP" ]; then
        priv mv "$BACKUP" "$TARGET" && echo "  設置に失敗したため元に戻しました"
    fi
    die "設置に失敗しました"
fi

# 古い退避分は直近3世代だけ残す
if [ -d "$BACKUP_BASE" ]; then
    # shellcheck disable=SC2012
    ls -1dt "$BACKUP_BASE"/*/ 2>/dev/null | tail -n +4 | while IFS= read -r old; do
        priv rm -rf "$old"
    done
fi

# 所有者を設置先に合わせる（sudo で入れた場合に root 所有になるのを防ぐ）
own="$(stat -c '%U:%G' "$PLUGIN_BASE" 2>/dev/null)"
if [ -n "$own" ] && [ "$own" != ":" ]; then
    priv chown -R "$own" "$TARGET" 2>/dev/null \
        && echo "  所有者: $own"
fi

ver="$($PY -I -c '
import json,sys
print(json.load(open(sys.argv[1])).get("version","?"))
' "$TARGET/manifest.json" 2>/dev/null)"
[ -n "$ver" ] && echo "  プラグイン version: $ver"

# ---------------------------------------------------------------------------
# ステップ5: 再起動
# ---------------------------------------------------------------------------

echo "[5/5] RotorHazard を再起動..."

RESTARTED=0
if [ "$NO_RESTART" = 1 ]; then
    echo "  → --no-restart が指定されたのでスキップ"
elif [ -z "$SVC_NAME" ]; then
    echo "  → サービスが見つかりません"
    echo "    手動で再起動してください"
elif sudo systemctl restart "$SVC_NAME" </dev/tty 2>/dev/null; then
    echo "  → 完了"
    RESTARTED=1
else
    echo "  → 失敗（手動: sudo systemctl restart $SVC_NAME）"
fi

echo ""
echo "=== インストール完了 ==="
echo "  設置先: $TARGET"
[ -n "$BACKUP" ] && echo "  旧版: $BACKUP（問題なければ削除可）"

# 設置先を推定した場合、本当に読み込まれたかはログで確認するしかない。
# 再起動できたなら、その確認まで自動でやってしまう。
if [ "$RESTARTED" = 1 ]; then
    echo ""
    echo "読み込みを確認中..."
    sleep 8
    if journalctl -u "$SVC_NAME" --since "1 min ago" --no-pager 2>/dev/null \
         | grep -qi "$PLUGIN_NAME\|elrs"; then
        echo "  → OK: ログにプラグインが現れました"
    else
        cat <<EOF
  → 警告: ログにプラグインが見つかりませんでした

  設置先が RotorHazard の読み込み対象でない可能性があります。
  「設定」画面に ELRS のパネルが出ているか確認してください。
  出ていない場合は、別の場所を指定して再実行してください:
EOF
        if [ -n "$RH_ROOT" ]; then
            alt="$RH_ROOT/src/server/plugins"
            [ "$PLUGIN_BASE" = "$alt" ] && alt="$RH_ROOT/src/server/custom_plugins"
            echo "    bash <(curl -fsSL https://raw.githubusercontent.com/$OWNER_REPO/master/tools/install.sh) --dir=$alt"
        fi
        echo ""
        echo "  ログ確認: journalctl -u $SVC_NAME -n 100 --no-pager | grep -i elrs"
    fi
else
    echo ""
    echo "RotorHazard の「設定」画面に ELRS のパネルが出れば読み込み成功です。"
    if [ -n "$SVC_NAME" ]; then
        echo "ログ確認: journalctl -u $SVC_NAME -n 100 --no-pager | grep -i elrs"
    fi
fi
