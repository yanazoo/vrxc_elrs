import logging

import RHAPI
from eventmanager import Evt
from RHUI import UIField, UIFieldSelectOption, UIFieldType

from .connections import ConnectionTypeEnum
from .elrs_backpack import ELRSBackpack

logger = logging.getLogger(__name__)


def initialize(rhapi: RHAPI.RHAPI):

    controller = ELRSBackpack("elrs", "ELRS", rhapi)

    rhapi.events.on(Evt.VRX_INITIALIZE, controller.register_handlers)
    rhapi.events.on(Evt.PILOT_ALTER, controller.pilot_alter)
    rhapi.events.on(
        Evt.STARTUP, controller.start_recieve_loop, name="start_recieve_loop"
    )
    rhapi.events.on(Evt.STARTUP, controller.start_connection, name="start_connection")

    #
    # Setup UI
    #

    elrs_bindphrase = UIField(
        name="comm_elrs", label="ELRS BP バインドフレーズ", field_type=UIFieldType.TEXT
    )
    rhapi.fields.register_pilot_attribute(elrs_bindphrase)

    active = UIField("elrs_active", "ELRS OSD を有効にする", field_type=UIFieldType.CHECKBOX)
    rhapi.fields.register_pilot_attribute(active)

    rhapi.ui.register_panel(
        "elrs_settings", "ELRS バックパック 一般設定", "settings", order=0
    )

    rhapi.ui.register_panel(
        "elrs_vrxc", "ELRS バックパック OSD 設定", "settings", order=0
    )

    #
    # チェックボックス
    #

    _race_start = UIField(
        "_race_start",
        "送信機からレースを開始",
        desc="レースディレクターが送信機からレースを開始できます",
        field_type=UIFieldType.CHECKBOX,
    )
    rhapi.fields.register_option(_race_start, "elrs_settings")

    _race_stop = UIField(
        "_race_stop",
        "送信機からレースを停止",
        desc="レースディレクターが送信機からレースを停止できます",
        field_type=UIFieldType.CHECKBOX,
    )
    rhapi.fields.register_option(_race_stop, "elrs_settings")

    _autosave_on_stop = UIField(
        "_autosave_on_stop",
        "停止時に自動保存",
        desc="送信機から停止した際にレースを自動保存します",
        field_type=UIFieldType.CHECKBOX,
        value="0",
    )
    rhapi.fields.register_option(_autosave_on_stop, "elrs_settings")

    _socket_ip = UIField(
        "_socket_ip",
        "ELRS Netpack アドレス",
        desc="ELRS Netpack のホスト名または IP アドレス",
        value="elrs-netpack.local",
        field_type=UIFieldType.TEXT,
    )
    rhapi.fields.register_option(_socket_ip, "elrs_settings")

    conn_opts = [UIFieldSelectOption(value=None, label="")]
    for type_ in ConnectionTypeEnum:
        race_selection = UIFieldSelectOption(value=type_.id_, label=type_.name)
        conn_opts.append(race_selection)

    _conn_opt = UIField(
        "_conn_opt",
        "バックパック接続タイプ",
        desc="バックパックの接続タイプを選択します",
        field_type=UIFieldType.SELECT,
        options=conn_opts,
    )
    rhapi.fields.register_option(_conn_opt, "elrs_settings")

    _auto_reconnect = UIField(
        "_auto_reconnect",
        "自動再接続",
        desc="バックパックが切れたときに自動的に再接続を試みます",
        field_type=UIFieldType.CHECKBOX,
        value="1",
    )
    rhapi.fields.register_option(_auto_reconnect, "elrs_settings")

    _reconnect_interval = UIField(
        "_reconnect_interval",
        "再接続間隔（秒）",
        desc="自動再接続を試みる間隔（3秒以上）",
        field_type=UIFieldType.BASIC_INT,
        value=10,
    )
    rhapi.fields.register_option(_reconnect_interval, "elrs_settings")

    _heat_name = UIField(
        "_heat_name",
        "ヒート名を表示",
        desc="スタート時にヒート名を表示します",
        field_type=UIFieldType.CHECKBOX,
    )
    rhapi.fields.register_option(_heat_name, "elrs_vrxc")

    _round_num = UIField(
        "_round_num",
        "ラウンド番号を表示",
        desc="スタート時にラウンド番号を表示します",
        field_type=UIFieldType.CHECKBOX,
    )
    rhapi.fields.register_option(_round_num, "elrs_vrxc")

    _class_name = UIField(
        "_class_name",
        "クラス名を表示",
        desc="スタート時にクラス名を表示します",
        field_type=UIFieldType.CHECKBOX,
    )
    rhapi.fields.register_option(_class_name, "elrs_vrxc")

    _event_name = UIField(
        "_event_name",
        "イベント名を表示",
        desc="スタート時にイベント名を表示します",
        field_type=UIFieldType.CHECKBOX,
    )
    rhapi.fields.register_option(_event_name, "elrs_vrxc")

    _position_mode = UIField(
        "_position_mode",
        "現在の順位とラップを表示",
        desc="オフ時は現在のラップのみ表示",
        field_type=UIFieldType.CHECKBOX,
    )
    rhapi.fields.register_option(_position_mode, "elrs_vrxc")

    _gap_mode = UIField(
        "_gap_mode",
        "ギャップタイムを表示",
        desc="オフ時はラップタイムを表示",
        field_type=UIFieldType.CHECKBOX,
    )
    rhapi.fields.register_option(_gap_mode, "elrs_vrxc")

    _results_mode = UIField(
        "_results_mode",
        "レース後の結果を表示",
        desc="レース終了時にパイロットの結果を表示します",
        field_type=UIFieldType.CHECKBOX,
    )
    rhapi.fields.register_option(_results_mode, "elrs_vrxc")

    #
    # テキストフィールド
    #

    _racestage_message = UIField(
        "_racestage_message",
        "ステージングメッセージ",
        desc="小文字はシンボルとして使用されます",
        field_type=UIFieldType.TEXT,
        value="w ARM NOW x",
    )
    rhapi.fields.register_option(_racestage_message, "elrs_vrxc")

    _racestart_message = UIField(
        "_racestart_message",
        "レーススタートメッセージ",
        desc="小文字はシンボルとして使用されます",
        field_type=UIFieldType.TEXT,
        value="w   GO!   x",
    )
    rhapi.fields.register_option(_racestart_message, "elrs_vrxc")

    _pilotdone_message = UIField(
        "_pilotdone_message",
        "パイロット完了メッセージ",
        desc="小文字はシンボルとして使用されます",
        field_type=UIFieldType.TEXT,
        value="w FINISHED! x",
    )
    rhapi.fields.register_option(_pilotdone_message, "elrs_vrxc")

    _racefinish_message = UIField(
        "_racefinish_message",
        "レース終了メッセージ",
        desc="小文字はシンボルとして使用されます",
        field_type=UIFieldType.TEXT,
        value="w FINISH LAP! x",
    )
    rhapi.fields.register_option(_racefinish_message, "elrs_vrxc")

    _racestop_message = UIField(
        "_racestop_message",
        "レース停止メッセージ",
        desc="小文字はシンボルとして使用されます",
        field_type=UIFieldType.TEXT,
        value="w  LAND NOW!  x",
    )
    rhapi.fields.register_option(_racestop_message, "elrs_vrxc")

    _leader_message = UIField(
        "_leader_message",
        "レースリーダーメッセージ",
        desc="小文字はシンボルとして使用されます",
        field_type=UIFieldType.TEXT,
        value="RACE LEADER",
    )
    rhapi.fields.register_option(_leader_message, "elrs_vrxc")

    #
    # 数値フィールド
    #

    _osd_lap_delay = UIField(
        "_osd_lap_delay",
        "ラップ後 OSD 送信遅延",
        desc="デカ秒（×0.1秒）。ラップ検出直後の OSD 送信を遅らせてノイズ干渉を軽減",
        field_type=UIFieldType.BASIC_INT,
        value=3,
    )
    rhapi.fields.register_option(_osd_lap_delay, "elrs_vrxc")

    _racestart_uptime = UIField(
        "_racestart_uptime",
        "スタートメッセージ表示時間",
        desc="デカ秒（×0.1秒）",
        field_type=UIFieldType.BASIC_INT,
        value=5,
    )
    rhapi.fields.register_option(_racestart_uptime, "elrs_vrxc")

    _finish_uptime = UIField(
        "_finish_uptime",
        "終了メッセージ表示時間",
        desc="デカ秒（×0.1秒）",
        field_type=UIFieldType.BASIC_INT,
        value=20,
    )
    rhapi.fields.register_option(_finish_uptime, "elrs_vrxc")

    _results_uptime = UIField(
        "_results_uptime",
        "ラップ結果表示時間",
        desc="デカ秒（×0.1秒）",
        field_type=UIFieldType.BASIC_INT,
        value=40,
    )
    rhapi.fields.register_option(_results_uptime, "elrs_vrxc")

    _announcement_uptime = UIField(
        "_announcement_uptime",
        "アナウンス表示時間",
        desc="デカ秒（×0.1秒）",
        field_type=UIFieldType.BASIC_INT,
        value=50,
    )
    rhapi.fields.register_option(_announcement_uptime, "elrs_vrxc")

    _heatname_row = UIField(
        "_heatname_row",
        "ヒート名の行",
        desc="0〜17 の行を指定",
        field_type=UIFieldType.BASIC_INT,
        value=2,
    )
    rhapi.fields.register_option(_heatname_row, "elrs_vrxc")

    _classname_row = UIField(
        "_classname_row",
        "クラス名の行",
        desc="0〜17 の行を指定",
        field_type=UIFieldType.BASIC_INT,
        value=1,
    )
    rhapi.fields.register_option(_classname_row, "elrs_vrxc")

    _eventname_row = UIField(
        "_eventname_row",
        "イベント名の行",
        desc="0〜17 の行を指定",
        field_type=UIFieldType.BASIC_INT,
        value=0,
    )
    rhapi.fields.register_option(_eventname_row, "elrs_vrxc")

    _announcement_row = UIField(
        "_announcement_row",
        "アナウンスの行",
        desc="0〜17 の行を指定",
        field_type=UIFieldType.BASIC_INT,
        value=3,
    )
    rhapi.fields.register_option(_announcement_row, "elrs_vrxc")

    _status_row = UIField(
        "_status_row",
        "レースステータスの行",
        desc="0〜17 の行を指定",
        field_type=UIFieldType.BASIC_INT,
        value=5,
    )
    rhapi.fields.register_option(_status_row, "elrs_vrxc")

    _currentlap_row = UIField(
        "_currentlap_row",
        "現在のラップ/順位の行",
        desc="0〜17 の行を指定",
        field_type=UIFieldType.BASIC_INT,
        value=0,
    )
    rhapi.fields.register_option(_currentlap_row, "elrs_vrxc")

    _lapresults_row = UIField(
        "_lapresults_row",
        "ラップ/ギャップ結果の行",
        desc="0〜17 の行を指定",
        field_type=UIFieldType.BASIC_INT,
        value=15,
    )
    rhapi.fields.register_option(_lapresults_row, "elrs_vrxc")

    _results_row = UIField(
        "_results_row",
        "結果の行",
        desc="0〜16 の行を指定（2行使用）",
        field_type=UIFieldType.BASIC_INT,
        value=13,
    )
    rhapi.fields.register_option(_results_row, "elrs_vrxc")

    #
    # 列位置（-1 = 自動センタリング、0〜49 = 手動指定）
    #

    _heatname_col = UIField(
        "_heatname_col",
        "ヒート名の列",
        desc="-1=自動センタリング、0〜49=手動指定",
        field_type=UIFieldType.BASIC_INT,
        value=-1,
    )
    rhapi.fields.register_option(_heatname_col, "elrs_vrxc")

    _classname_col = UIField(
        "_classname_col",
        "クラス名の列",
        desc="-1=自動センタリング、0〜49=手動指定",
        field_type=UIFieldType.BASIC_INT,
        value=-1,
    )
    rhapi.fields.register_option(_classname_col, "elrs_vrxc")

    _eventname_col = UIField(
        "_eventname_col",
        "イベント名の列",
        desc="-1=自動センタリング、0〜49=手動指定",
        field_type=UIFieldType.BASIC_INT,
        value=-1,
    )
    rhapi.fields.register_option(_eventname_col, "elrs_vrxc")

    _announcement_col = UIField(
        "_announcement_col",
        "アナウンスの列",
        desc="-1=自動センタリング、0〜49=手動指定",
        field_type=UIFieldType.BASIC_INT,
        value=-1,
    )
    rhapi.fields.register_option(_announcement_col, "elrs_vrxc")

    _status_col = UIField(
        "_status_col",
        "レースステータスの列",
        desc="-1=自動センタリング、0〜49=手動指定",
        field_type=UIFieldType.BASIC_INT,
        value=-1,
    )
    rhapi.fields.register_option(_status_col, "elrs_vrxc")

    _currentlap_col = UIField(
        "_currentlap_col",
        "現在のラップ/順位の列",
        desc="-1=自動センタリング、0〜49=手動指定",
        field_type=UIFieldType.BASIC_INT,
        value=-1,
    )
    rhapi.fields.register_option(_currentlap_col, "elrs_vrxc")

    _lapresults_col = UIField(
        "_lapresults_col",
        "ラップ/ギャップ結果の列",
        desc="-1=自動センタリング、0〜49=手動指定",
        field_type=UIFieldType.BASIC_INT,
        value=-1,
    )
    rhapi.fields.register_option(_lapresults_col, "elrs_vrxc")

    _results_col = UIField(
        "_results_col",
        "結果の列",
        desc="-1=自動センタリング、0〜49=手動指定",
        field_type=UIFieldType.BASIC_INT,
        value=-1,
    )
    rhapi.fields.register_option(_results_col, "elrs_vrxc")

    #
    # ボタン
    #

    rhapi.ui.register_quickbutton(
        "elrs_settings",
        "bp_connect",
        "バックパック接続",
        controller.start_connection,
    )
    rhapi.ui.register_quickbutton(
        "elrs_settings",
        "bp_disconnect",
        "バックパック切断",
        controller.disconnect,
    )
    rhapi.ui.register_quickbutton(
        "elrs_settings", "enable_bind", "バックパックバインド開始", controller.activate_bind
    )

    rhapi.ui.register_quickbutton(
        "elrs_settings",
        "test_osd",
        "バインド済みバックパックの OSD テスト",
        controller.test_bind_osd,
    )
    rhapi.ui.register_quickbutton(
        "elrs_settings", "enable_wifi", "バックパック WiFi 起動", controller.activate_wifi
    )
