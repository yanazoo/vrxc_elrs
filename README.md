# RotorHazard VRx Control for the ExpressLRS Backpack

これは以下の機能を持つ RotorHazard タイミングシステム向けのプラグインです：
- [X] 対応機器（[HDZero ゴーグル](https://www.youtube.com/watch?v=VXwaUoA16jc) など）を使用するパイロットへ OSD メッセージを送信
- [X] レース管理者が[送信機からレースを開始](https://github.com/i-am-grub/VRxC_ELRS?tab=readme-ov-file#control-the-race-from-the-race-directors-transmitter)できる機能
- [ ] パイロットの `ready` ステータスを送信機から送信

プラグインの現在のロードマップは[こちら](https://github.com/i-am-grub/VRxC_ELRS/issues/5)を参照してください。

## どのように動作するか？

このプラグインは、シリアルポートを通じて ExpressLRS タイマーバックパックを実行している外部デバイスまたはチップを制御するために構築されています。これにより、タイミングシステムは ELRS バックパックが内蔵された他のデバイスと通信できるようになり、パイロットの送信機から状態メッセージを受信したり、OSD 情報をパイロットのゴーグルに直接表示するメッセージを送信したりすることができます。

## パイロット向け：セットアップに必要なこと

現在、ELRS バックパックから OSD レースメッセージを受信できる唯一のデバイスは HDZero ゴーグルです。これらのゴーグルには ExpressLRS バックパック用の内蔵 ESP32 チップが搭載されています。
[ExpressLRS Configurator](https://github.com/ExpressLRS/ExpressLRS-Configurator/releases) または [ExpressLRS Web Flasher](https://expresslrs.github.io/web-flasher/) を使用して、ゴーグルのビデオレシーバーバックパックを最新バージョンに更新してください。初回インストールは[このガイド](https://www.expresslrs.org/hardware/backpack/hdzero-goggles/)に従ってください。インストールやゴーグルファームウェアのアップグレードについてサポートが必要な場合は、[ExpressLRS Discord](https://discord.gg/expresslrs) の `help-and-support` チャンネルで質問してください。

> [!IMPORTANT]
> バックパックのバインドフレーズを必ず覚えておいてください：タイマーのバックパックはこれを使用して、タイマーから HDZero ゴーグルへ OSD メッセージを送信します。
> レースで OSD 情報を受信したい場合は、レースディレクターにバインドフレーズを提供する必要があります。

> [!NOTE]
> バックパックのバインドフレーズは、ExpressLRS 無線プロトコルで使用するバインドフレーズと同じでも異なっていても構いません。
> 同じバインドフレーズを設定しても、バックパックが無線プロトコルに干渉することはありません。

## レースディレクター向けセットアップ手順

### タイマーバックパックのインストール

以下は RotorHazard タイマーバックパックに対応している既知のデバイスの一覧です。タイマーバックパックの通信範囲を改善するために、外部 WIFI アンテナを接続できるチップの使用を推奨します。

| ELRS デバイス           | 対応ハードウェア                                                                                                   |
| --------------------- | --------------------------------------------------------------------------------------------------------------------- |
| EP82 モジュール（DIY）     | [ESP8266 NodeMCU](https://a.co/d/9vgX3Tx)                                                                             |
| EP32 モジュール（DIY）     | [ESP32-DevKitC](https://a.co/d/62OGBgG)                                                                               |
| EP32C3 モジュール（DIY）   | [ESP32-C3-DevKitM-1U](https://www.digikey.com/en/products/detail/espressif-systems/ESP32-C3-DEVKITM-1U/15198974)      |
| EP32S3 モジュール（DIY）   | [ESP32-S3-DevKitC-1U](https://www.digikey.com/en/products/detail/espressif-systems/ESP32-S3-DEVKITC-1U-N8R8/16162636) |
| NuclearHazard         | [NuclearHazard Board](https://www.etsy.com/listing/1428199972/nuclearhazard-core-kit-case-and-rx-sold) v7 以降    |
| [ELRS-Netpack](https://github.com/i-am-grub/elrs-netpack)（DIY） | [Waveshare ESP32-S3 Ethernet](https://www.waveshare.com/esp32-s3-eth.htm)   |

> [!TIP]
> 同様のチップセットを持つ他の開発ボードが表のターゲットでサポートされる場合がありますが、動作は保証されません。
> 例えば、Seeed Studio XIAO ESP32C3/S3 ボードは上記ターゲットでは動作しませんが、
> バックパックファームウェアのビルドに [ExpressLRS Toolchain](https://www.expresslrs.org/software/toolchain-install/) を使用する場合、
> platformio の設定を変更して XIAO ボード向けの互換ファームウェアをビルドすることができます。

> [!NOTE]
> 通常の ExpressLRS レシーバーにバックパックファームウェアを書き込んでタイマーバックパックとして使用することは可能ですが、推奨しません。
> 主な理由は、ELRS バックパックが ESP32/ESP82 の WIFI ハードウェアを使用する ESPNow をベースにしているためです。
> レシーバーは通常、WIFI 経由でウェブ UI に接続するための小型セラミックアンテナが別途搭載されていますが、このアンテナは
> 無線プロトコル用のアンテナとは異なります。セラミックアンテナは、外部 WIFI アンテナを接続した ESP32 開発キットと比較してパフォーマンスが劣る可能性があります。

#### ESP32/ESP82 開発キットへの書き込み

ファームウェアのビルドと書き込みには、[ExpressLRS Configurator](https://github.com/ExpressLRS/ExpressLRS-Configurator/releases) または [ExpressLRS Web Flasher](https://expresslrs.github.io/web-flasher/) を使用してください。

1. USB でデバイスをコンピューターに接続します。

> Windows がデバイスを認識しない場合は、ドライバーのインストールまたは更新が必要な場合があります。
> Espressif 製ボードは通常、[CP210x](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers) または
> [FTDI](https://ftdichip.com/drivers/vcp-drivers/) USB シリアル変換チップを使用しています。

2. バックパックファームウェアモードを選択します。
    - Configurator を使用する場合、左側メニューの `Backpack` を選択します。
    - Web Flasher を使用する場合、Backpack Firmware セクションの `Race Timer` を選択します。
3. 1.5.0（またはそれ以降）のリリースを選択します。
4. RotorHazard デバイスカテゴリを選択します。
5. デバイスのターゲットを選択します。
6. UART 書き込み方法を選択します。
7. バックパックのバインドフレーズを入力します（ディレクターの送信機からのレース制御用）。
8. デバイスの COM ポートを選択します。
9. ファームウェアをビルドして書き込みます。

#### NuclearHazard ハードウェアへの書き込み

ファームウェアのビルドには、[ExpressLRS Configurator](https://github.com/ExpressLRS/ExpressLRS-Configurator/release) または [ExpressLRS Web Flasher](https://expresslrs.github.io/web-flasher/) を使用してください。

1. バックパックファームウェアセクションを選択します。
   - Configurator を使用する場合、左側メニューの `Backpack` を選択します。
   - Web Flasher を使用する場合、Backpack Firmware セクションの `Race Timer` を選択します。
2. 1.5.0（またはそれ以降）のリリースを選択します。
3. RotorHazard デバイスカテゴリを選択します。
4. デバイスとして NuclearHazard を選択します。
5. 方法を選択します。
    - Configurator を使用する場合、`WIFI` を選択します。
    - Web Flasher を使用する場合、`Local Download` を選択します。
6. バックパックのバインドフレーズを入力します（ディレクターの送信機からのレース制御用）。
7. ファームウェアをビルドします。
8. [このガイド](https://nuclearquads.com/instructions/vrxc)に従って、オンボード ESP32 に書き込みます。バックパックのバイナリファイルをダウンロードする代わりに、Configurator でビルドしたファイルを使用してください。

#### ELRS Netpack への書き込み

1. コミュニティプラグインリストから [netpack-installer](https://github.com/i-am-grub/netpack-installer) プラグインをダウンロードします。
2. 必要な ESP32 開発キットをタイマーに接続します。
3. `Settings` ページの `ELRS Netpack Firmware` パネルで、接続されたデバイスのシリアルポートを選択し、
`Flash Netpack Firmware` ボタンを押します。

### RotorHazard プラグインのインストール

1. タイマーに RotorHazard v4.1.0 以降がインストールされていることを確認します。
2. プラグインの[最新リリース](https://github.com/i-am-grub/VRxC_ELRS/releases)の指示に従って、インストールを完了してください。

### レースディレクターの送信機からレースを制御する

送信機のバックパック内で設定した `DVR Rec` スイッチの位置をトラッキングすることで、レースディレクターの送信機からレースを制御する機能があります。現在は、送信機と VRx バックパックで使用されるプロセスと同様に、レースタイマーのバックパックをレースディレクターのバックパックバインドフレーズにバインドすることで機能します。

現在はレースの開始と停止のみサポートされています。この機能を設定しても、他のユーザーが OSD メッセージを受信できなくなることはありません。

> [!IMPORTANT]
> この機能を使用するには、レースディレクターの送信機に ELRS バックパックがセットアップされている必要があります。以下の手順を完了する前に、必ずセットアップを確認してください。

1. ELRS バックパックで `DVR Rec` スイッチをセットアップします。
    1. 送信機で ExpressLRS Lua スクリプト（v3 推奨）を開きます。
    2. バックパック設定を開きます。
    3. `DVR Rec` の AUX チャンネルを設定します。

> [!NOTE]
> これによって、このスイッチで DVR 録画を開始する機能が失われることはありません。レースタイマーのバックパックが監視する状態にすぎません。

2. レースタイマーバックパックを送信機にバインドします。タイマーのバックパックにレースディレクターのバックパックバインドフレーズを含むファームウェアを書き込んだ場合、このステップはスキップできます。
    1. ESP32 を接続した状態で RotorHazard サーバーを起動します。
    2. `ELRS Backpack General Settings` パネルに移動します。
    3. `Start Backpack Bind` ボタンをクリックします。
    4. 送信機の ExpressLRS Lua スクリプトで `Bind` をクリックします。

バックパックが正常にバインドされたかテストするには、RotorHazard の `Race` ページに移動し、`DVR Rec` スイッチでレースを開始します。
[Start Race from Transmitter](https://github.com/i-am-grub/VRxC_ELRS?tab=readme-ov-file#start-race-from-transmitter--checkbox)
または [Stop Race from Transmitter](https://github.com/i-am-grub/VRxC_ELRS?tab=readme-ov-file#stop-race-from-transmitter--checkbox)
を `ELRS Backpack General Settings` で有効にする必要があります。

> [!TIP]
> バックパックを新しい送信機にバインドし直す必要がある場合は、最新リリースのファームウェアで ESP32 を再書き込みしてから再バインドするのが最も簡単です。

# 追加ハードウェアに関する注意事項

## 3D プリントケース

一部のユーザーは、外付け `ESP32-DevKitC-1U` ボード用として [Printables](https://www.printables.com/model/762529-esp32-wroom-32u-casing) で公開されている以下の 3D プリント可能なケースを使用することを好んでいます。

![Case](docs/3DPrint/wirex-1.webp)

## WIFI シグナルブースター

ExpressLRS バックパックの品質と信頼性は、HDZero ゴーグルがタイマーからバックパックメッセージを受信する能力に大きく依存しています。ゴーグルのバックパック用アンテナは内部にあり、パイロットの無線プロトコルによる 2.4 GHz 帯の追加 RF 干渉が発生する可能性があるため、WIFI シグナルブースターがバックパックの信頼性向上に役立つ場合があります。

個人的なセットアップ：
- [ESP32-DevKitC](https://a.co/d/62OGBgG)
- [U.FL to RP-SMA ケーブル](https://a.co/d/7n99T9o)
- [800mW ペン双方向ブースターモジュール](https://www.data-alliance.net/800mw-bi-directional-booster-module-w-rp-sma-female-connectors/)
- [RaspberryPi からブースターに電源供給するための USB 電源ケーブル](https://a.co/d/9iAPV57)
- RP-SMA 接続対応の高ゲイン 2.4 GHz WIFI アンテナ

> [!NOTE]
> ESP32 は通常、シグナルブースターなしで 100 ミリワット未満の最大出力設定です。

## USB 延長ケーブル

[一部のグループ](https://youtu.be/FZvmfyvRiPE?si=LXu0zXUpDj9NsnUN&t=201)では、長い USB ケーブルや USB 延長ケーブルを使用して ESP32 をパイロットに近づけることで良い結果を得ています。

> [!NOTE]
> RotorHazard 開発チームは、シリアル over HTTPS 接続を設定する機能の実装を検討しています。これにより、タイマーバックパックをタイマーではなく、レースディレクターのコンピューターに直接接続できるようになります。

# 設定

## パイロット設定

![Pilot Settings](docs/pilot_atts.png)

### ELRS BP バインドフレーズ : TEXT

パイロット個人のバックパック用バインドフレーズ。バインドフレーズが設定されていない場合、代わりにパイロットのコールサインがバインドフレーズとして使用されます。

### Enable ELRS OSD : CHECKBOX

パイロットの ELRS OSD をオン/オフにします。

## ELRS バックパック一般設定

![General Settings](docs/general_settings.png)

### Start Race from Transmitter : CHECKBOX

レースディレクターが送信機からレースを開始できるようにします。バックパックのバインドについては[こちら](https://github.com/i-am-grub/VRxC_ELRS#control-the-race-from-the-race-directors-transmitter)を参照してください。

### Stop Race from Transmitter : CHECKBOX

レースディレクターが送信機からレースを停止できるようにします。バックパックのバインドについては[こちら](https://github.com/i-am-grub/VRxC_ELRS#control-the-race-from-the-race-directors-transmitter)を参照してください。

### Autosave on stop : CHECKBOX

送信機から停止した際にレースを自動保存します。

### Backpack Rescan : BUTTON

タイマーにシリアルデバイスをスキャンしてバックパックデバイスを探させます。タイマーがまだバックパックデバイスに接続されていない場合のみ動作します。

### Start Backpack Bind : BUTTON

タイマーのバックパックをレースディレクターの送信機とのペアリング用バインドモードにします。

> [!TIP]
> このプロセスが正常に完了すると、タイマーのバックパックは送信機からレースディレクターのバインドフレーズを引き継ぎます。

### Test Bound Backpack's OSD : BUTTON

一致するバインドフレーズを持つ HDZero ゴーグルに OSD メッセージを表示します。タイマーのバックパックが送信機のバインドフレーズを正常に引き継いだかテストするために使用します。

### Start Backpack WIFI : BUTTON

バックパックの WIFI モードを開始します。無線ファームウェア更新に使用します。

> [!TIP]
> バックパックのウェブユーザーインターフェースに接続するには、バックパックがウェブユーザーインターフェースにアクセスするデバイスと同じネットワークに接続するよう設定するか、バックパックが作成したワイヤレスネットワークにデバイスを接続してください。デバイスのブラウザで `http://elrs_timer.local` を開いてウェブユーザーインターフェースに接続します。

## ELRS バックパック OSD 設定

![OSD Settings](docs/osd_settings.png)

> [!NOTE]
> このプロジェクトの目標として、このセクションのすべての OSD 設定を、最終的には ExpressLRS VRx バックパックのウェブユーザーインターフェースを通じてパイロットが個別に設定できるようにすることを目指しています。
> 現在の実装は、VRx バックパックでの個別パイロット設定に向けた進捗が十分に完了するまでの暫定的な回避策です。

### Show Heat Name : CHECKBOX

レースのアクティブ時にヒート名をパイロットに表示します。

### Show Round Number : CHECKBOX

レースのアクティブ時にラウンド番号をパイロットに表示します。`Show Heat Name` も有効にする必要があります。

### Show Class Name : CHECKBOX

レースのアクティブ時にクラス名をパイロットに表示します。

### Show Event Name : CHECKBOX

レースのアクティブ時にイベント名をパイロットに表示します。

### Show Current Position and Lap : CHECKBOX

- オン：複数のパイロットがレース中の場合、現在の順位と現在のラップを表示します。
- オフ：現在のラップのみを表示します。

### Show Gap Time : CHECKBOX

- オン：レースで互換性のある勝利条件を使用している場合、次のパイロットまでのギャップタイムを表示します。
- オフ：ラップ結果時間を表示します。

### Show Post-Race Results : CHECKBOX

パイロットがレースを終了した際に結果を表示します。着陸時に Betaflight の `Post Flight Results` によって結果が上書きされないよう、パイロットにはこの設定をオフにすることを推奨します。

### Race Stage Message : TEXT

タイマーがレースをステージング中にパイロットに表示されるメッセージ。

### Race Start Message : TEXT

レースが開始された直後にパイロットに表示されるメッセージ。

### Pilot Done Message : TEXT

パイロットがレースを終了した際にパイロットに表示されるメッセージ。

### Race Finish Message : TEXT

制限時間が来た際にパイロットに表示されるメッセージ。

### Race Stop Message : TEXT

レースが停止された際にパイロットに表示されるメッセージ。

### Race Leader Message : TEXT

`Show Gap Time` が有効でパイロットがレースをリードしている場合にパイロットに表示されるメッセージ。

### Start Message Uptime : INT

`Race Start Message` がパイロットに表示される時間の長さ。

### Finish Message Uptime : INT

`Pilot Done Message` と `Race Finish Message` がパイロットに表示される時間の長さ。

### Lap Result Uptime : INT

ラップ完了後にパイロットのラップまたはギャップタイムが表示される時間の長さ。

### Announcement Uptime : INT

パイロットへのアナウンスを表示する時間の長さ（例：レースがスケジュールされたとき）。

### Heat Name Row : INT

レースのステージング時にヒート名を表示する行。

### Class Name Row : INT

レースのステージング時にクラス名を表示する行。

### Event Name Row : INT

レースのステージング時にイベント名を表示する行。

### Announcement Row : INT

レースがスケジュールされた際などのアナウンスを表示する行。この行は `Show Race Name on Stage` でも使用されます。

### Race Status Row : INT

レースステータスメッセージを表示する行。

### Current Lap/Position Row : INT

現在のラップと順位を表示する行。

### Lap/Gap Results Row : INT

ラップまたはギャップタイムを表示する行。

### Results Rows : INT

パイロットのレース後の統計を表示し始める行。入力した行とその次の行も使用されます。
