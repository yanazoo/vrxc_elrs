# XIAO ESP32-S3 × elrs-netpack セットアップ引き継ぎ

## 目的

Seeed Studio **XIAO ESP32-S3**（外部アンテナモデル）を使って、
RotorHazard タイマーから **WiFi 経由で MSP パケットを受信し、
ESPNow でパイロットの HDZero ゴーグルに OSD を送信する**デバイスを作る。

---

## ベースリポジトリ

| 項目 | 内容 |
|------|------|
| fork 元 | https://github.com/i-am-grub/elrs-netpack |
| 作業 fork | https://github.com/yanazoo/elrs-netpack |
| 作業ブランチ | `feature/wifi-ethernet-selection` |

---

## システム構成

```
[RotorHazard (Raspberry Pi)]
         ↓ TCP port 8080 (WiFi LAN)
    XIAO ESP32-S3
         ↓ ESPNow (2.4GHz)
   HDZero ゴーグル（パイロット）
```

### 内部アーキテクチャ（デュアルコア）

```
Core 0: runESPNOWServer()  → ESPNow ↔ ゴーグル
Core 1: run_tcp_server()   → TCP socket ↔ RotorHazard
              ↕ リングバッファ
```

**ビルドシステム:** ESP-IDF v5.4.1（Arduino / PlatformIO ではない）

---

## 必要な変更（3ファイル）

Waveshare 用の Ethernet 接続に加え、WiFi 接続を選択できるように変更する。

### ファイル 1：`components/tcp_server/Kconfig.projbuild`

ファイル全体を以下に置き換える：

```
menu "TCP Socket Server options"
    config TCP_SERVER_PORT
        int "TCP server listening port"
        default 8080
        help
            Set TCP server listening port.

    choice TCP_CONNECTION_TYPE
        prompt "Network connection type"
        default TCP_USE_ETHERNET
        help
            Select the network interface for the TCP server.
            - Ethernet: Waveshare ESP32-S3 Ethernet board (W5500)
            - WiFi: XIAO ESP32-S3 or any WiFi-only ESP32-S3 board

        config TCP_USE_ETHERNET
            bool "Ethernet (W5500 / Waveshare ESP32-S3)"

        config TCP_USE_WIFI
            bool "WiFi Station (XIAO ESP32-S3 etc.)"
    endchoice

    if TCP_USE_WIFI
        config TCP_WIFI_SSID
            string "WiFi SSID"
            default "myssid"
            help
                SSID of the WiFi access point to connect to.

        config TCP_WIFI_PASSWORD
            string "WiFi Password"
            default ""
            help
                Password for the WiFi access point.
    endif

endmenu
```

---

### ファイル 2：`components/espnow_server/espnow_server.cpp`

242〜250行目（WiFi 初期化部分）を以下に置き換える：

```cpp
    // Start WiFi for ESPNOW
#ifdef CONFIG_TCP_USE_WIFI
    // WiFi mode: create STA netif before wifi_init so tcp_server can get the handle
    esp_netif_create_default_wifi_sta();
#endif

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));

    ESP_ERROR_CHECK(esp_wifi_start());

#ifdef CONFIG_TCP_USE_WIFI
    // WiFi mode: connect to AP; channel follows the AP automatically
    wifi_config_t sta_config = {};
    strncpy((char *)sta_config.sta.ssid, CONFIG_TCP_WIFI_SSID, sizeof(sta_config.sta.ssid));
    strncpy((char *)sta_config.sta.password, CONFIG_TCP_WIFI_PASSWORD, sizeof(sta_config.sta.password));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &sta_config));
    ESP_ERROR_CHECK(esp_wifi_connect());
#else
    // Ethernet mode: fix ESPNow channel (no AP to follow)
    ESP_ERROR_CHECK(esp_wifi_set_channel(CONFIG_ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE));
#endif

    ESP_ERROR_CHECK(esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_11B | WIFI_PROTOCOL_11G | WIFI_PROTOCOL_11N | WIFI_PROTOCOL_LR));
```

---

### ファイル 3：`components/tcp_server/tcp_server.cpp`

#### 変更箇所 A：includes（上部の eth 関連3行を #ifdef で囲む）

```cpp
#ifdef CONFIG_TCP_USE_ETHERNET
#include "esp_eth.h"
#include "ethernet_init.h"
#include "dhcpserver/dhcpserver_options.h"
#endif
```

#### 変更箇所 B：`initialize_mdns` と `got_ip_event_handler`

パラメータ名 `eth_netif` を `netif` に全置換。
`got_ip_event_handler` のログ部分に以下を追加：

```cpp
#ifdef CONFIG_TCP_USE_ETHERNET
    ESP_LOGI(TAG, "Ethernet Got IP Address");
#else
    ESP_LOGI(TAG, "WiFi Got IP Address");
#endif
```

#### 変更箇所 C：`run_tcp_server()` のネットワーク初期化部分（150〜187行目）

```cpp
#ifdef CONFIG_TCP_USE_ETHERNET
    uint8_t eth_port_cnt = 0;
    esp_eth_handle_t *eth_handles;
    ESP_ERROR_CHECK(ethernet_init_all(&eth_handles, &eth_port_cnt));

    char if_key_str[10];
    char if_desc_str[10];
    esp_netif_config_t cfg;
    esp_netif_inherent_config_t eth_netif_cfg;

    if (eth_port_cnt == 1)
        eth_netif_cfg = *(ESP_NETIF_BASE_DEFAULT_ETH);
    else
        eth_netif_cfg = (esp_netif_inherent_config_t)ESP_NETIF_INHERENT_DEFAULT_ETH();

    cfg = (esp_netif_config_t){
        .base = &eth_netif_cfg,
        .stack = ESP_NETIF_NETSTACK_DEFAULT_ETH};
    sprintf(if_key_str, "ETH_%d", 0);
    sprintf(if_desc_str, "eth%d", 0);
    eth_netif_cfg.if_key = if_key_str;
    eth_netif_cfg.if_desc = if_desc_str;
    eth_netif_cfg.route_prio -= 0 * 5;
    esp_netif_t *netif = esp_netif_new(&cfg);

    ESP_ERROR_CHECK(esp_netif_attach(netif, esp_eth_new_netif_glue(eth_handles[0])));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_ETH_GOT_IP, got_ip_event_handler, netif));
    for (int i = 0; i < eth_port_cnt; i++)
        ESP_ERROR_CHECK(esp_eth_start(eth_handles[i]));

#else // CONFIG_TCP_USE_WIFI
    // WiFi netif は espnow_server で作成済み。ハンドルを取得してイベント登録のみ行う
    esp_netif_t *netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, got_ip_event_handler, netif));

#endif // CONFIG_TCP_USE_ETHERNET
```

---

## ビルド・書き込み手順

### 1. VS Code 環境セットアップ

```
1. VS Code に "ESP-IDF" 拡張（Espressif 公式）をインストール
2. コマンドパレット → ESP-IDF: Configure ESP-IDF Extension
   → EXPRESS → バージョン: v5.4.1 → ターゲット: esp32s3
3. yanazoo/elrs-netpack を VS Code で開く
```

### 2. 上記3ファイルを編集して保存

### 3. ターゲット設定

```
コマンドパレット → ESP-IDF: Set Espressif Device Target → esp32s3
```

### 4. menuconfig で WiFi を選択

```
コマンドパレット → ESP-IDF: SDK Configuration Editor
→ TCP Socket Server options
  → Network connection type → WiFi Station (XIAO ESP32-S3 etc.)
  → WiFi SSID: あなたのSSID
  → WiFi Password: あなたのパスワード
```

### 5. ビルド

```
VS Code 下部ステータスバーの 🔨 ボタン
```

### 6. XIAO に書き込み

```
XIAO を USB-C で PC に接続
VS Code 下部ステータスバーの ⚡ ボタン
```

**書き込めない場合（ブートローダーモード）:**
```
① BOOT ボタンを押したまま
② RESET ボタンを押して離す
③ BOOT ボタンを離す
```

---

## RotorHazard 側の設定（書き込み完了後）

RotorHazard の設定画面で：

```
ELRS バックパック 一般設定
  バックパック接続タイプ → SOCKET
  ELRS Netpack アドレス  → elrs-netpack.local
                           （または XIAO の IP アドレス: 例 192.168.1.xx）
```

---

## 注意事項

| 項目 | 内容 |
|------|------|
| Flash サイズ | XIAO ESP32-S3 は 8MB。sdkconfig の `CONFIG_ESPTOOLPY_FLASHSIZE` が `2MB` の場合は `8MB` に変更 |
| ESPNow チャンネル | WiFi AP（ルーター）のチャンネルに自動追従するため固定不要 |
| W5500 ドライバ | WiFi モードでも Ethernet ドライバがビルドに含まれるが動作に影響なし（不要なら menuconfig で無効化可） |
| mDNS | IP 取得後に `elrs-netpack.local` でアクセス可能になる |
