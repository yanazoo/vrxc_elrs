# RotorHazard VRx Control for the ExpressLRS Backpack

> **Language / 言語:**  [English](#english) | [日本語](#日本語)

---

<a name="english"></a>

## English

A [RotorHazard](https://github.com/RotorHazard/RotorHazard) plugin that integrates the [ExpressLRS Backpack](https://www.expresslrs.org/hardware/backpack/backpack-firmware/) to deliver race OSD messages directly to pilots' goggles.

This is a fork of [VRxC_ELRS](https://github.com/i-am-grub/VRxC_ELRS) by [Bryce "GRUBBY" Gruber](https://github.com/i-am-grub), enhanced with:

- **Japanese UI** — full Japanese localization
- **XIAO ESP32-S3 WiFi bridge support** — works with [yanazoo/elrs-netpack](https://github.com/yanazoo/elrs-netpack) over WiFi (no Waveshare Ethernet board required)
- **Auto-reconnect** — automatically restores the connection when it drops
- **OSD column position settings** — individually configure the horizontal position of each OSD element
- **OSD deduplication** — skips redundant transmissions to reduce RF load
- **Multi-byte character safety** — prevents crashes when event/heat names contain Japanese or other CJK characters

### Features

- [x] Send OSD messages to pilots using [HDZero goggles](https://www.hdzero.com/)
- [x] Start/stop races from the race director's transmitter
- [x] Configurable message positions (row and column per element)
- [x] Auto-reconnect on connection loss
- [ ] Pilot `ready` status from transmitter *(planned)*

---

### Compatible Hardware

| Connection Type | Hardware |
|---|---|
| **ONBOARD** | [NuclearHazard](https://www.etsy.com/listing/1428199972) v7+ (built-in ESP32) |
| **USB** | ESP32 / ESP8266 DevKit flashed with ELRS backpack firmware |
| **SOCKET** (WiFi) | [yanazoo/elrs-netpack](https://github.com/yanazoo/elrs-netpack) — dual-MCU WiFi-to-ESP-NOW bridge |

> **SOCKET mode** uses the [yanazoo/elrs-netpack](https://github.com/yanazoo/elrs-netpack) firmware.
> The bridge consists of a **XIAO ESP32-S3** (WiFi / TCP) and an **ESP32 Wrover-E** (ESP-NOW to goggles) connected via UART.
> For hardware wiring and firmware flashing instructions, see the **[elrs-netpack README](https://github.com/yanazoo/elrs-netpack)**.

---

### Installation

#### One-line installer (NuclearHazard & Raspberry Pi)

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/yanazoo/vrxc_elrs/master/tools/install.sh)
```

The script locates your RotorHazard installation itself and restarts the
service, so it works regardless of the username or directory layout
(NuclearHazard 4.4 renamed the user from `NuclearHazard` to `nuclear`, for
example). It stages and validates the files before replacing anything, so a
failed download leaves your working install untouched.

Useful options:

```bash
# See where it would install, without changing anything
bash <(curl -fsSL .../install.sh) --dry-run

# Install a specific release instead of master
bash <(curl -fsSL .../install.sh) --ref=v1.1.4

# Install somewhere specific (if auto-detection picks the wrong place)
bash <(curl -fsSL .../install.sh) --dir=/home/nuclear/rh-data/plugins
```

#### Manual installation

The plugin directory differs between images, so find yours first:

```bash
# NuclearHazard images keep plugins in rh-data (survives RotorHazard updates)
ls -d /home/*/rh-data/plugins

# Other installs use custom_plugins under the server directory
ls -d /home/*/RotorHazard/src/server/custom_plugins

# Not sure where RotorHazard itself lives?
systemctl show rotorhazard -p WorkingDirectory
```

Then copy the plugin into that directory:

```bash
PLUGIN_DIR=/home/nuclear/rh-data/plugins    # replace with the path you found
mkdir -p "$PLUGIN_DIR"
git clone https://github.com/yanazoo/vrxc_elrs.git /tmp/vrxc_elrs_tmp
cp -r /tmp/vrxc_elrs_tmp/custom_plugins/vrxc_elrs "$PLUGIN_DIR"/
rm -rf /tmp/vrxc_elrs_tmp
sudo systemctl restart rotorhazard
```

Confirm it loaded — the ELRS panels should appear under Settings:

```bash
journalctl -u rotorhazard -n 100 --no-pager | grep -i elrs
```

#### Updating

Run the one-line installer again. It replaces the plugin and keeps the
previous version under `.vrxc_elrs-backup/` in case you need to roll back.

---

### Configuration

#### Pilot settings

| Field | Description |
|---|---|
| **ELRS BP Bind Phrase** | The pilot's backpack bind phrase. If empty, the pilot's callsign is used. |
| **Enable ELRS OSD** | Checkbox to enable OSD for this pilot. |

> Both fields must be set for a pilot to receive OSD messages.

#### General settings (`ELRS Backpack General Settings`)

| Field | Description |
|---|---|
| Backpack Connection Type | `ONBOARD` / `USB` / `SOCKET` |
| ELRS Netpack Address | Hostname or IP of the XIAO bridge (SOCKET mode only) |
| Auto Reconnect | Automatically reconnect when the connection drops |
| Reconnect Interval | Seconds between reconnect attempts (minimum 3 s) |
| Start Race from Transmitter | Allow race director to start race via TX switch |
| Stop Race from Transmitter | Allow race director to stop race via TX switch |
| Autosave on stop | Auto-save race when stopped from transmitter |

#### OSD settings (`ELRS Backpack OSD Settings`)

Each OSD element has a **row** and a **column** setting.

| Column value | Behaviour |
|---|---|
| `-1` | Auto-center (default) |
| `0–49` | Fixed column from left |

Full list of OSD elements:

| Element | Default row |
|---|---|
| Event Name | 0 |
| Class Name | 1 |
| Heat Name | 2 |
| Announcement | 3 |
| Race Status (stage / start / stop) | 5 |
| Current Lap / Position | 0 |
| Lap / Gap Results | 15 |
| Post-race Results | 13 (uses 2 rows) |

---

### Differences from the original VRxC_ELRS

| Feature | Original | This fork |
|---|---|---|
| UI language | English | English + **Japanese** |
| WiFi bridge (XIAO) | Not supported | **SOCKET mode** |
| Auto-reconnect | Manual only | **Automatic** |
| OSD column position | Fixed center | **Per-element setting** |
| OSD deduplication | None | **Yes** |
| Multi-byte char safety | Crashes | **Silently skipped** |

---

### Credits

- Original plugin: [VRxC_ELRS](https://github.com/i-am-grub/VRxC_ELRS) by [Bryce "GRUBBY" Gruber](https://github.com/i-am-grub) — GPL-3.0
- WiFi bridge firmware: [yanazoo/elrs-netpack](https://github.com/yanazoo/elrs-netpack), forked from [i-am-grub/elrs-netpack](https://github.com/i-am-grub/elrs-netpack)
- [ExpressLRS](https://www.expresslrs.org/) project
- [RotorHazard](https://github.com/RotorHazard/RotorHazard) project

---

---

<a name="日本語"></a>

## 日本語

[RotorHazard](https://github.com/RotorHazard/RotorHazard) タイミングシステム向けプラグインです。[ExpressLRS バックパック](https://www.expresslrs.org/hardware/backpack/backpack-firmware/)を通じて、パイロットのゴーグルへレース情報を OSD として直接表示します。

このリポジトリは [Bryce "GRUBBY" Gruber](https://github.com/i-am-grub) 氏の [VRxC_ELRS](https://github.com/i-am-grub/VRxC_ELRS) のフォークに以下の機能を追加したものです：

- **日本語 UI** — インターフェース全体を日本語化
- **XIAO ESP32-S3 WiFi ブリッジ対応** — [yanazoo/elrs-netpack](https://github.com/yanazoo/elrs-netpack) を使い WiFi 経由で接続（Waveshare Ethernet ボード不要）
- **自動再接続** — 接続が切れた場合に自動的に再接続
- **OSD 列位置設定** — 各 OSD 表示要素の横位置を個別に設定可能
- **OSD 重複排除** — 同一内容の再送信をスキップし RF 負荷を軽減
- **マルチバイト文字対応** — イベント名・ヒート名に日本語を使用してもクラッシュしない

### 機能

- [x] HDZero ゴーグルへのレース OSD 送信
- [x] レースディレクターの送信機からレース開始・停止
- [x] OSD 各要素の行・列位置設定
- [x] 接続断時の自動再接続
- [ ] 送信機からパイロット `ready` 状態送信（予定）

---

### 対応ハードウェア

| 接続タイプ | ハードウェア |
|---|---|
| **ONBOARD** | [NuclearHazard](https://www.etsy.com/listing/1428199972) v7 以降（内蔵 ESP32） |
| **USB** | ELRS バックパックファームウェアを書き込んだ ESP32 / ESP8266 開発ボード |
| **SOCKET**（WiFi） | [yanazoo/elrs-netpack](https://github.com/yanazoo/elrs-netpack) — デュアル MCU WiFi→ESP-NOW ブリッジ |

> **SOCKET モード**は [yanazoo/elrs-netpack](https://github.com/yanazoo/elrs-netpack) ファームウェアを使用します。
> **XIAO ESP32-S3**（WiFi / TCP 担当）と **ESP32 Wrover-E**（ゴーグルへの ESP-NOW 担当）を UART 接続したデュアル MCU 構成です。
> ハードウェアの配線やファームウェアの書き込み手順は **[elrs-netpack の README](https://github.com/yanazoo/elrs-netpack)** を参照してください。

---

### インストール

#### ワンライン インストーラー（NuclearHazard・Raspberry Pi 共通）

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/yanazoo/vrxc_elrs/master/tools/install.sh)
```

RotorHazard 本体の場所をスクリプト自身が探してファイルを配置し、サービスを再起動します。インストール先をハードコードしていないため、**ユーザー名やディレクトリ構成が違っても動作します**（NuclearHazard 4.4 でユーザー名が `NuclearHazard` → `nuclear` に変わった場合など）。

ファイルは一時領域に取得して検証してから入れ替えるので、**ダウンロードが途中で失敗しても稼働中のプラグインは壊れません**。

主なオプション:

```bash
# どこに入るかだけ確認（何も変更しない）
bash <(curl -fsSL .../install.sh) --dry-run

# master ではなく特定のリリースを入れる
bash <(curl -fsSL .../install.sh) --ref=v1.1.4

# 自動検出が外れた場合に場所を明示する
bash <(curl -fsSL .../install.sh) --dir=/home/nuclear/rh-data/plugins
```

#### 手動インストール

プラグインの置き場所はイメージによって違うため、まず自分の環境を確認します。

```bash
# NuclearHazard 系は rh-data 配下（本体更新で消えない）
ls -d /home/*/rh-data/plugins

# それ以外は server ディレクトリ配下の custom_plugins
ls -d /home/*/RotorHazard/src/server/custom_plugins

# RotorHazard 本体の場所が分からない場合
systemctl show rotorhazard -p WorkingDirectory
```

見つかったディレクトリにコピーします。

```bash
PLUGIN_DIR=/home/nuclear/rh-data/plugins    # 上で確認したパスに置き換える
mkdir -p "$PLUGIN_DIR"
git clone https://github.com/yanazoo/vrxc_elrs.git /tmp/vrxc_elrs_tmp
cp -r /tmp/vrxc_elrs_tmp/custom_plugins/vrxc_elrs "$PLUGIN_DIR"/
rm -rf /tmp/vrxc_elrs_tmp
sudo systemctl restart rotorhazard
```

読み込まれたかの確認（「設定」画面に ELRS のパネルが出れば成功です）:

```bash
journalctl -u rotorhazard -n 100 --no-pager | grep -i elrs
```

#### アップデート

同じワンライン インストーラーを再実行するだけです。旧版は `.vrxc_elrs-backup/` に直近3世代まで退避されるので、問題があれば戻せます。

---

### 設定

#### パイロット設定

| 項目 | 説明 |
|---|---|
| **ELRS BP バインドフレーズ** | パイロット個人のバックパック用バインドフレーズ。未入力の場合はコールサインを使用 |
| **ELRS OSD を有効にする** | このパイロットへの OSD 送信を有効にするチェックボックス |

> OSD を受信するにはどちらも設定が必要です。

#### 一般設定（ELRS バックパック 一般設定）

| 項目 | 説明 |
|---|---|
| バックパック接続タイプ | `ONBOARD` / `USB` / `SOCKET` から選択 |
| ELRS Netpack アドレス | XIAO ブリッジのホスト名または IP（SOCKET モード時のみ） |
| 自動再接続 | 接続断時に自動で再接続を試みる |
| 再接続間隔（秒） | 再接続を試みる間隔（最小 3 秒） |
| 送信機からレースを開始 | レースディレクターが TX スイッチでレース開始できる |
| 送信機からレースを停止 | レースディレクターが TX スイッチでレース停止できる |
| 停止時に自動保存 | 送信機から停止した際にレースを自動保存 |

#### OSD 設定（ELRS バックパック OSD 設定）

各 OSD 要素に **行（Row）** と **列（Column）** を設定できます。

| 列の設定値 | 動作 |
|---|---|
| `-1` | 自動センタリング（デフォルト） |
| `0〜49` | 左端からの列番号で手動指定 |

OSD 表示要素一覧：

| 要素 | デフォルト行 |
|---|---|
| イベント名 | 0 |
| クラス名 | 1 |
| ヒート名 | 2 |
| アナウンス | 3 |
| レースステータス（ステージ・スタート・停止） | 5 |
| 現在のラップ / 順位 | 0 |
| ラップ / ギャップタイム | 15 |
| レース後の結果 | 13（2 行使用） |

---

### オリジナルとの主な違い

| 機能 | オリジナル | このフォーク |
|---|---|---|
| UI 言語 | 英語のみ | 英語 + **日本語** |
| WiFi ブリッジ（XIAO） | 非対応 | **SOCKET モード対応** |
| 自動再接続 | 手動のみ | **自動** |
| OSD 列位置設定 | センター固定 | **要素ごとに設定可能** |
| OSD 重複排除 | なし | **あり** |
| マルチバイト文字 | クラッシュ | **安全にスキップ** |

---

### クレジット・参考

- オリジナルプラグイン：[VRxC_ELRS](https://github.com/i-am-grub/VRxC_ELRS) by [Bryce "GRUBBY" Gruber](https://github.com/i-am-grub) — GPL-3.0 ライセンス
- WiFi ブリッジファームウェア：[yanazoo/elrs-netpack](https://github.com/yanazoo/elrs-netpack)（[i-am-grub/elrs-netpack](https://github.com/i-am-grub/elrs-netpack) のフォーク）
- [ExpressLRS](https://www.expresslrs.org/) プロジェクト
- [RotorHazard](https://github.com/RotorHazard/RotorHazard) プロジェクト
