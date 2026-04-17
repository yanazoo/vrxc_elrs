#!/bin/bash
# vrxc_elrs インストール / アップデートスクリプト
# 使い方:
#   bash <(curl -fsSL https://raw.githubusercontent.com/yanazoo/vrxc_elrs/master/tools/install.sh)
#   bash <(wget -qO- https://raw.githubusercontent.com/yanazoo/vrxc_elrs/master/tools/install.sh)

set -e

REPO_RAW="https://raw.githubusercontent.com/yanazoo/vrxc_elrs/master/custom_plugins/vrxc_elrs"
PLUGIN_NAME="vrxc_elrs"
FILES="__init__.py elrs_backpack.py connections.py msp.py manifest.json"

echo "================================================"
echo "  vrxc_elrs (yanazoo fork) インストーラー"
echo "================================================"
echo ""

# -------------------------------------------------------
# sudo をターミナルから実行（パイプ経由でも動作）
# -------------------------------------------------------
run_sudo() {
    if [ "$(id -u)" = "0" ]; then
        "$@"
    else
        sudo "$@" </dev/tty
    fi
}

# -------------------------------------------------------
# インストール先の検出（固定パスのみ）
# -------------------------------------------------------
INSTALL_BASE=""

CANDIDATES=(
    "/home/NuclearHazard/rh-data/plugins"
    "/home/pi/RotorHazard/src/server/custom_plugins"
    "/home/ubuntu/RotorHazard/src/server/custom_plugins"
    "$HOME/RotorHazard/src/server/custom_plugins"
)

for path in "${CANDIDATES[@]}"; do
    if [ -d "$path" ]; then
        INSTALL_BASE="$path"
        break
    fi
done

if [ -z "$INSTALL_BASE" ]; then
    echo "エラー: インストール先が見つかりません。"
    echo "以下のいずれかのディレクトリを手動で作成してから再実行してください:"
    for path in "${CANDIDATES[@]}"; do
        echo "  $path"
    done
    exit 1
fi

PLUGIN_DIR="$INSTALL_BASE/$PLUGIN_NAME"
echo "インストール先: $PLUGIN_DIR"
echo ""

# ディレクトリ作成
mkdir -p "$PLUGIN_DIR/locale"

# -------------------------------------------------------
# ファイルのダウンロード
# -------------------------------------------------------
echo "ファイルをダウンロード中..."

for file in $FILES; do
    echo "  → $file"
    if command -v curl &>/dev/null; then
        curl -fsSL "$REPO_RAW/$file" -o "$PLUGIN_DIR/$file"
    else
        wget -qO "$PLUGIN_DIR/$file" "$REPO_RAW/$file"
    fi
done

echo "  → locale/ja.json"
if command -v curl &>/dev/null; then
    curl -fsSL "$REPO_RAW/locale/ja.json" -o "$PLUGIN_DIR/locale/ja.json"
else
    wget -qO "$PLUGIN_DIR/locale/ja.json" "$REPO_RAW/locale/ja.json"
fi

echo ""
echo "ダウンロード完了！"
echo ""

# -------------------------------------------------------
# RotorHazard の再起動
# -------------------------------------------------------
SERVICE=""
for svc in rotorhazard rhserver; do
    if systemctl is-active --quiet "$svc" 2>/dev/null || systemctl is-enabled --quiet "$svc" 2>/dev/null; then
        SERVICE="$svc"
        break
    fi
done

if [ -n "$SERVICE" ]; then
    echo "RotorHazard を再起動中... ($SERVICE)"
    run_sudo systemctl restart "$SERVICE"
    echo "再起動完了！"
else
    echo "注意: RotorHazard サービスが見つかりませんでした。"
    echo "手動で再起動してください: sudo systemctl restart rotorhazard"
fi

echo ""
echo "================================================"
echo "  インストール完了！"
echo "  プラグインフォルダー: $PLUGIN_DIR"
echo "================================================"
