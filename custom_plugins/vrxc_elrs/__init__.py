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

    _show_bestlap = UIField(
        "_show_bestlap",
        "ベストラップを常に表示",
        desc="ラップ記録のたびに自己ベストを専用行に表示します",
        field_type=UIFieldType.CHECKBOX,
    )
    rhapi.fields.register_option(_show_bestlap, "elrs_vrxc")

    _position_mode = UIField(
        "_position_mode",
        "現在の順位とラップを表示",
        desc="オフ時は現在のラップのみ表示",
        field_type=UIFieldType.CHECKBOX,
    )
    rhapi.fields.register_option(_position_mode, "elrs_vrxc")

    _show_totaltime = UIField(
        "_show_totaltime",
        "トータルタイムを常に表示",
        desc="ラップのたびにトータルタイムを専用行に更新表示します",
        field_type=UIFieldType.CHECKBOX,
    )
    rhapi.fields.register_option(_show_totaltime, "elrs_vrxc")

    _show_raceclock = UIField(
        "_show_raceclock",
        "レースクロックを表示",
        desc="レース中、経過時間を全パイロットのOSDに毎秒表示します",
        field_type=UIFieldType.CHECKBOX,
    )
    rhapi.fields.register_option(_show_raceclock, "elrs_vrxc")

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
        value="ARM NOW",
    )
    rhapi.fields.register_option(_racestage_message, "elrs_vrxc")

    _racestart_message = UIField(
        "_racestart_message",
        "レーススタートメッセージ",
        desc="小文字はシンボルとして使用されます",
        field_type=UIFieldType.TEXT,
        value="GO!",
    )
    rhapi.fields.register_option(_racestart_message, "elrs_vrxc")

    _pilotdone_message = UIField(
        "_pilotdone_message",
        "パイロット完了メッセージ",
        desc="小文字はシンボルとして使用されます",
        field_type=UIFieldType.TEXT,
        value="FINISHED!",
    )
    rhapi.fields.register_option(_pilotdone_message, "elrs_vrxc")

    _racefinish_message = UIField(
        "_racefinish_message",
        "レース終了メッセージ",
        desc="小文字はシンボルとして使用されます",
        field_type=UIFieldType.TEXT,
        value="FINISH LAP!",
    )
    rhapi.fields.register_option(_racefinish_message, "elrs_vrxc")

    _racestop_message = UIField(
        "_racestop_message",
        "レース停止メッセージ",
        desc="小文字はシンボルとして使用されます",
        field_type=UIFieldType.TEXT,
        value="LAND NOW!",
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

    #
    # 行・列位置（「行,列」形式。例: "5,-1"　列が負の値=自動センタリング）
    #

    _heatname_pos = UIField("_heatname_pos", "ヒート名の位置 (行,列)", desc="例: 2,-1　列が負=自動センタリング", field_type=UIFieldType.TEXT, value="2,-1")
    rhapi.fields.register_option(_heatname_pos, "elrs_vrxc")

    _classname_pos = UIField("_classname_pos", "クラス名の位置 (行,列)", desc="例: 1,-1　列が負=自動センタリング", field_type=UIFieldType.TEXT, value="1,-1")
    rhapi.fields.register_option(_classname_pos, "elrs_vrxc")

    _eventname_pos = UIField("_eventname_pos", "イベント名の位置 (行,列)", desc="例: 0,-1　列が負=自動センタリング", field_type=UIFieldType.TEXT, value="0,-1")
    rhapi.fields.register_option(_eventname_pos, "elrs_vrxc")

    _bestlap_pos = UIField("_bestlap_pos", "ベストラップの位置 (行,列)", desc="例: 1,-1　列が負=自動センタリング", field_type=UIFieldType.TEXT, value="1,-1")
    rhapi.fields.register_option(_bestlap_pos, "elrs_vrxc")

    _announcement_pos = UIField("_announcement_pos", "アナウンスの位置 (行,列)", desc="例: 3,-1　列が負=自動センタリング", field_type=UIFieldType.TEXT, value="3,-1")
    rhapi.fields.register_option(_announcement_pos, "elrs_vrxc")

    _status_pos = UIField("_status_pos", "レースステータスの位置 (行,列)", desc="例: 5,-1　列が負=自動センタリング", field_type=UIFieldType.TEXT, value="5,-1")
    rhapi.fields.register_option(_status_pos, "elrs_vrxc")

    _currentlap_pos = UIField("_currentlap_pos", "現在のラップ/順位の位置 (行,列)", desc="例: 0,-1　列が負=自動センタリング", field_type=UIFieldType.TEXT, value="0,-1")
    rhapi.fields.register_option(_currentlap_pos, "elrs_vrxc")

    _totaltime_pos = UIField("_totaltime_pos", "トータルタイムの位置 (行,列)", desc="例: 2,-1　列が負=自動センタリング", field_type=UIFieldType.TEXT, value="2,-1")
    rhapi.fields.register_option(_totaltime_pos, "elrs_vrxc")

    _lapresults_pos = UIField("_lapresults_pos", "ラップタイムの位置 (行,列)", desc="例: 15,-1　列が負=自動センタリング", field_type=UIFieldType.TEXT, value="15,-1")
    rhapi.fields.register_option(_lapresults_pos, "elrs_vrxc")

    _results_pos = UIField("_results_pos", "結果の位置 (行,列)  ※2行使用", desc="例: 13,-1　列が負=自動センタリング", field_type=UIFieldType.TEXT, value="13,-1")
    rhapi.fields.register_option(_results_pos, "elrs_vrxc")

    _raceclock_pos = UIField("_raceclock_pos", "レースクロックの位置 (行,列)", desc="例: 17,-1　列が負=自動センタリング", field_type=UIFieldType.TEXT, value="17,-1")
    rhapi.fields.register_option(_raceclock_pos, "elrs_vrxc")

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
