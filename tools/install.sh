#!/bin/bash
# vrxc_elrs インストール / アップデートスクリプト
# 使い方:
#   bash <(curl -fsSL https://raw.githubusercontent.com/yanazoo/vrxc_elrs/master/tools/install.sh)

REPO="https://raw.githubusercontent.com/yanazoo/vrxc_elrs/master/custom_plugins/vrxc_elrs"

echo "=== vrxc_elrs インストーラー ==="
echo ""

# ステップ1: インストール先
echo "[1/3] インストール先を確認..."
if [ -d "/home/NuclearHazard/rh-data/plugins" ]; then
    DIR="/home/NuclearHazard/rh-data/plugins/vrxc_elrs"
elif [ -d "/home/pi/RotorHazard/src/server/custom_plugins" ]; then
    DIR="/home/pi/RotorHazard/src/server/custom_plugins/vrxc_elrs"
elif [ -d "$HOME/RotorHazard/src/server/custom_plugins" ]; then
    DIR="$HOME/RotorHazard/src/server/custom_plugins/vrxc_elrs"
else
    echo "エラー: インストール先が見つかりません"
    echo "以下のいずれかが存在するか確認してください:"
    echo "  /home/NuclearHazard/rh-data/plugins"
    echo "  /home/pi/RotorHazard/src/server/custom_plugins"
    exit 1
fi
echo "  → $DIR"
mkdir -p "$DIR/locale"

# ステップ2: ダウンロード
echo "[2/3] ファイルをダウンロード..."
for f in __init__.py elrs_backpack.py connections.py msp.py manifest.json; do
    echo "  → $f"
    wget -q --timeout=15 -O "$DIR/$f" "$REPO/$f" || { echo "ダウンロード失敗: $f"; exit 1; }
done
echo "  → locale/ja.json"
wget -q --timeout=15 -O "$DIR/locale/ja.json" "$REPO/locale/ja.json" || { echo "ダウンロード失敗: ja.json"; exit 1; }

# ステップ3: 再起動
echo "[3/3] RotorHazard を再起動..."
if systemctl is-active --quiet rotorhazard 2>/dev/null; then
    sudo systemctl restart rotorhazard </dev/tty && echo "  → 完了" || echo "  → 失敗（手動: sudo systemctl restart rotorhazard）"
else
    echo "  → サービスが見つかりません"
    echo "  手動で再起動してください: sudo systemctl restart rotorhazard"
fi

echo ""
echo "=== インストール完了: $DIR ==="
