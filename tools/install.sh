#!/bin/bash
# vrxc_elrs インストール / アップデートスクリプト
# 使い方:
#   curl -fsSL https://raw.githubusercontent.com/yanazoo/vrxc_elrs/master/tools/install.sh | bash
#   wget -qO- https://raw.githubusercontent.com/yanazoo/vrxc_elrs/master/tools/install.sh | bash

set -e

REPO_RAW="https://raw.githubusercontent.com/yanazoo/vrxc_elrs/master/custom_plugins/vrxc_elrs"
PLUGIN_NAME="vrxc_elrs"
FILES="__init__.py elrs_backpack.py connections.py msp.py manifest.json"

# -------------------------------------------------------
# インストール先の自動検出
# -------------------------------------------------------
detect_install_path() {
    local candidates=(
        "/home/NuclearHazard/rh-data/plugins"
        "/home/pi/RotorHazard/src/server/custom_plugins"
        "/home/ubuntu/RotorHazard/src/server/custom_plugins"
        "$HOME/RotorHazard/src/server/custom_plugins"
    )

    for path in "${candidates[@]}"; do
        if [ -d "$path" ]; then
            echo "$path"
            return
        fi
    done

    # RotorHazard のプロセスから検出
    local rh_path
    rh_path=$(find /home -name "RHRace.py" 2>/dev/null | head -1)
    if [ -n "$rh_path" ]; then
        local server_dir
        server_dir=$(dirname "$rh_path")
        # custom_plugins または rh-data/plugins を探す
        if [ -d "$server_dir/custom_plugins" ]; then
            echo "$server_dir/custom_plugins"
            return
        fi
    fi

    echo ""
}

# -------------------------------------------------------
# RotorHazard サービス名の検出
# -------------------------------------------------------
detect_service() {
    for svc in rotorhazard rhserver; do
        if systemctl list-units --type=service 2>/dev/null | grep -q "$svc"; then
            echo "$svc"
            return
        fi
    done
    echo ""
}

# -------------------------------------------------------
# メイン処理
# -------------------------------------------------------
echo "================================================"
echo "  vrxc_elrs (yanazoo fork) インストーラー"
echo "================================================"
echo ""

# インストール先の検出
INSTALL_BASE=$(detect_install_path)

if [ -z "$INSTALL_BASE" ]; then
    echo "エラー: RotorHazard のプラグインフォルダーが見つかりません。"
    echo "手動でパスを指定してください:"
    echo "  PLUGIN_DIR=/path/to/plugins bash <(curl -fsSL ...)"
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

DL_CMD=""
if command -v curl &>/dev/null; then
    DL_CMD="curl -fsSL"
elif command -v wget &>/dev/null; then
    DL_CMD="wget -qO-"
else
    echo "エラー: curl または wget が必要です。"
    exit 1
fi

for file in $FILES; do
    echo "  → $file"
    if command -v curl &>/dev/null; then
        curl -fsSL "$REPO_RAW/$file" -o "$PLUGIN_DIR/$file"
    else
        wget -qO "$PLUGIN_DIR/$file" "$REPO_RAW/$file"
    fi
done

# locale/ja.json
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
SERVICE=$(detect_service)

if [ -n "$SERVICE" ]; then
    echo "RotorHazard を再起動中... ($SERVICE)"
    sudo systemctl restart "$SERVICE"
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
