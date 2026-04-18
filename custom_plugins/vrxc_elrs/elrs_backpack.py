import hashlib
import logging

import gevent
import gevent.lock
import gevent.socket as socket
import util.RH_GPIO as RH_GPIO
from gevent.queue import Queue
from RHRace import RaceStatus, WinCondition
from VRxControl import VRxController

from .connections import BackpackConnection, ConnectionTypeEnum
from .msp import MSPPacket, MSPPacketType, MSPTypes

logger = logging.getLogger(__name__)


class CancelError(BaseException): ...


class ELRSBackpack(VRxController):
    _connection: BackpackConnection | None = None
    _reconnect_greenlet: gevent.Greenlet | None = None

    def __init__(self, name, label, rhapi):
        super().__init__(name, label)
        self._rhapi = rhapi
        self._send_queue = Queue()
        self._recieve_queue = Queue(maxsize=100)
        self._queue_lock = gevent.lock.RLock()
        self._manual_disconnect = True
        self._last_sent_osd: dict[int, dict[str, str]] = {}

    @property
    def _backpack_connected(self) -> bool:
        if self._connection is None:
            return False

        return self._connection.connected

    def register_handlers(self, args) -> None:
        """
        Registers handlers in the RotorHazard system
        """
        args["register_fn"](self)

    def start_race(self):
        """
        Start the race
        """
        if self._rhapi.db.option("_race_start") == "1":
            start_race_args = {"start_time_s": 10}
            if self._rhapi.race.status == RaceStatus.READY:
                self._rhapi.race.stage(start_race_args)

    def stop_race(self):
        """
        Stop the race
        """
        if self._rhapi.db.option("_race_stop") == "1":
            status = self._rhapi.race.status
            if status in (RaceStatus.STAGING, RaceStatus.RACING):
                if self._rhapi.db.option("_autosave_on_stop") == "1":
                    self._rhapi.race.save()
                else:
                    self._rhapi.race.stop()

    #
    # Connection handling
    #

    def start_recieve_loop(self, *_):
        """
        Start the msp packet processing loop
        """
        gevent.spawn(self.recieve_loop)
        logger.info("Backpack recieve greenlet started.")

    def start_connection(self, *_) -> None:
        """
        Starts the connection loop (user-initiated)
        """
        self._manual_disconnect = False
        self._attempt_connect(notify=True)
        self._start_reconnect_monitor()

    def _attempt_connect(self, notify: bool = True) -> bool:
        """
        Attempt to establish a backpack connection.

        :param notify: Whether to show UI messages (False during auto-reconnect)
        :return: True on successful connection
        """
        if self._backpack_connected:
            if notify:
                message = "バックパックはすでに接続されています"
                self._rhapi.ui.message_notify(self._rhapi.language.__(message))
            return True

        id_ = self._rhapi.db.option("_conn_opt", None, as_int=True)
        for con in ConnectionTypeEnum:
            if id_ == con.id_:
                break
        else:
            if notify:
                message = "接続タイプが指定されていません"
                self._rhapi.ui.message_notify(self._rhapi.language.__(message))
            return False

        if con == ConnectionTypeEnum.USB:
            return self._establish_connection(con.type_, notify=notify)

        elif con == ConnectionTypeEnum.ONBOARD:
            if RH_GPIO.is_real_hw_GPIO():
                logger.info("Turning on GPIO pins for NuclearHazard boards")
                RH_GPIO.setmode(RH_GPIO.BCM)
                RH_GPIO.setup(16, RH_GPIO.OUT, initial=RH_GPIO.HIGH)
                gevent.sleep(0.5)
                RH_GPIO.setup(11, RH_GPIO.OUT, initial=RH_GPIO.HIGH)
                gevent.sleep(0.5)
                RH_GPIO.output(11, RH_GPIO.LOW)
                gevent.sleep()
                RH_GPIO.output(11, RH_GPIO.HIGH)
                return self._establish_connection(con.type_, notify=notify)
            else:
                if notify:
                    message = "Raspberry Pi 上で動作していません"
                    self._rhapi.ui.message_notify(self._rhapi.language.__(message))
                return False

        elif con == ConnectionTypeEnum.SOCKET:
            addr = self._rhapi.db.option("_socket_ip", None)
            if addr is None:
                if notify:
                    message = "ソケットの IP アドレスが指定されていません"
                    self._rhapi.ui.message_notify(self._rhapi.language.__(message))
                return False
            try:
                ip_addr = socket.gethostbyname(addr)
            except socket.gaierror:
                if notify:
                    message = "デバイスのソケットへの接続に失敗しました"
                    self._rhapi.ui.message_notify(self._rhapi.language.__(message))
                return False
            return self._establish_connection(
                con.type_, ip_addr=ip_addr, notify=notify
            )

        return False

    def _establish_connection(
        self,
        connection_type: type[BackpackConnection],
        notify: bool = True,
        **kwargs,
    ) -> bool:
        """
        Setup the backpack connection

        :param connection_type: The type of connection to use
        :param notify: Whether to show UI messages
        :return: True on successful connection
        """
        # Clear data in send queue
        while not self._send_queue.empty():
            self._send_queue.get()

        # Clear OSD dedupe state so reconnect re-sends current info
        self._last_sent_osd.clear()

        self._connection = connection_type(self._send_queue, self._recieve_queue)
        if not self._connection.connect(**kwargs):
            if notify:
                message = "バックパック接続の確立に失敗しました"
                self._rhapi.ui.message_notify(self._rhapi.language.__(message))
            return False

        message = "バックパックへの接続に成功しました"
        if notify:
            self._rhapi.ui.message_notify(self._rhapi.language.__(message))
        else:
            logger.info(message)
            self._rhapi.ui.message_notify(
                self._rhapi.language.__("バックパックへ自動再接続しました")
            )

        self.version_request()
        return True

    def _start_reconnect_monitor(self) -> None:
        """
        Start the auto-reconnect monitor greenlet if not already running
        """
        if self._reconnect_greenlet is None or self._reconnect_greenlet.dead:
            self._reconnect_greenlet = gevent.spawn(self._reconnect_loop)
            logger.info("Auto-reconnect monitor started")

    def _reconnect_loop(self) -> None:
        """
        Monitor the connection and reconnect automatically if it drops
        """
        while True:
            try:
                interval = int(self._rhapi.db.option("_reconnect_interval") or 10)
            except (TypeError, ValueError):
                interval = 10
            gevent.sleep(max(interval, 3))

            if self._manual_disconnect:
                continue
            if self._rhapi.db.option("_auto_reconnect") != "1":
                continue
            if self._backpack_connected:
                continue

            logger.info("バックパック接続が切れました。再接続を試行します...")
            try:
                self._attempt_connect(notify=False)
            except Exception:
                logger.exception("再接続中にエラーが発生しました")

    def recieve_loop(self) -> None:
        """
        Handles recieving data from the backpack
        """
        try:
            while True:
                packet: MSPPacket = self._recieve_queue.get()

                function_ = packet.function

                if packet.type_ == MSPPacketType.RESPONSE:
                    if function_ == MSPTypes.MSP_ELRS_GET_BACKPACK_VERSION:
                        version = bytes(i for i in packet.payload if i != 0).decode(
                            "utf-8"
                        )
                        message = f"バックパックファームウェアバージョン: {version}"
                        logger.info(message)
                        self._rhapi.ui.message_notify(self._rhapi.language.__(message))

                if packet.type_ == MSPPacketType.COMMAND:
                    if function_ == MSPTypes.MSP_ELRS_BACKPACK_SET_RECORDING_STATE:
                        itr = packet.iterate_payload()
                        if (val := next(itr)) == 0x00:
                            self.stop_race()
                        elif val == 0x01:
                            self.start_race()

        except KeyboardInterrupt:
            logger.error("Stopping blackpack connector greenlet")

    def disconnect(self, *_) -> None:
        """
        Disconnect the connection loop (user-initiated)
        """
        self._manual_disconnect = True

        if self._reconnect_greenlet is not None:
            self._reconnect_greenlet.kill()
            self._reconnect_greenlet = None

        if not self._backpack_connected:
            message = "バックパックが接続されていません"
            self._rhapi.ui.message_notify(self._rhapi.language.__(message))
            return

        assert self._connection is not None
        self._connection.disconnect()

        message = "バックパックが切断されました"
        self._rhapi.ui.message_notify(self._rhapi.language.__(message))

    #
    # Packet creation
    #

    def hash_phrase(self, bindphrase: str) -> bytes:
        """
        Hashes a string into a UID

        :param bindphrase: The string to hash
        :return: The hashed phrase
        """

        hash_ = bytearray(
            x
            for x in hashlib.md5(
                (f'-DMY_BINDING_PHRASE="{bindphrase}"').encode()
            ).digest()[0:6]
        )
        if (hash_[0] % 2) == 1:
            hash_[0] -= 0x01

        return hash_

    def get_pilot_uid(self, pilot_id: int) -> bytes:
        """
        Get the uid for a pilot. If a bindphrase is not
        saved as an attribute, the pilot callsign is used
        to generate the uid.

        :param pilot_id: The pilot id
        :return: The pilot uid
        """
        assert pilot_id > 0, "Can not generate backpack uid for invalid pilot"
        bindphrase = self._rhapi.db.pilot_attribute_value(pilot_id, "comm_elrs")
        if bindphrase:
            uid = self.hash_phrase(bindphrase)
        else:
            pilot = self._rhapi.db.pilot_by_id(pilot_id)
            assert pilot is not None, "Pilot not in database"
            uid = self.hash_phrase(pilot.callsign)

        return uid

    def center_osd(self, len_: int) -> int:
        """
        Provides the column value needed to
        center a string of the provided length
        on the HDZero Goggles screen

        :param len_: The length of the string
        :return:
        """
        offset = len_ // 2
        col = 50 // 2 - offset
        return max(col, 0)

    def _get_col(self, text: str, col_option: str) -> int:
        """
        Returns the column position for OSD text.
        If the option value is negative, auto-centers the text.

        :param text: The text to display
        :param col_option: The option key for the column setting
        :return: Column position (0-49)
        """
        try:
            col = int(self._rhapi.db.option(col_option))
        except (TypeError, ValueError):
            col = -1
        if col < 0:
            return self.center_osd(len(text))
        return col

    def send_msp(self, msp: MSPPacket) -> None:
        """
        Sends a MSP packet to the backpack connection
        if it is active

        :param msp: _description_
        """
        if self._backpack_connected:
            self._send_queue.put(msp)

    def set_send_uid(self, address: bytes) -> None:
        """
        Sends the packet to set the address for the
        recipient of future packets

        :param address: Address to set
        """
        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_SET_SEND_UID)
        payload = bytearray()
        payload.append(0x01)
        payload += address
        packet.set_payload(payload)
        self.send_msp(packet)

    def reset_send_uid(self) -> None:
        """
        Sends the packet to reset the packet recipient
        to the system default
        """
        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_SET_SEND_UID)
        payload = bytearray()
        payload.append(0x00)
        packet.set_payload(payload)
        self.send_msp(packet)

    def send_clear_osd(self) -> None:
        """
        Sends the packet to clear the goggle's osd
        """
        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_SET_OSD)
        payload = bytearray()
        payload.append(0x02)
        packet.set_payload(payload)
        self.send_msp(packet)

    def send_osd_text(self, row: int, col: int, text: str) -> None:
        """
        Sends a packet that provides text data to the
        recipient. This does not display the text to the
        recipient until `send_display_osd` is called

        :param row: The row to display the text on
        :param col: The column to place the start of the
        :param message: _description_
        """
        payload = bytearray((0x03, row, col, 0))
        for index, char in enumerate(text):
            if index >= 50:
                break

            payload.append(ord(char))

        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_SET_OSD)
        packet.set_payload(payload)
        self.send_msp(packet)

    def send_display_osd(self) -> None:
        """
        Sends a packet that informs the recipient
        to display any provided text
        """
        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_SET_OSD)
        payload = bytearray((0x04,))
        packet.set_payload(payload)
        self.send_msp(packet)

    def send_clear_osd_row(self, row: int) -> None:
        """
        Sends a packet that clears the text data
        in a specific row. This does not remove
        the text until `send_display_osd` is called.

        :param row: The row to remove text from
        """
        payload = bytearray((0x03, row, 0, 0))
        for _ in range(50):
            payload.append(0)

        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_SET_OSD)
        packet.set_payload(payload)
        self.send_msp(packet)

    def version_request(self):
        """
        Sends the packet requesting the version of the
        backpack hardware
        """
        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_GET_BACKPACK_VERSION)
        self.send_msp(packet)

    def activate_bind(self, *_) -> None:
        """
        Sends a packet to put the connected device in
        bind mode
        """
        message = "バックパックのバインドモードを起動中..."
        self._rhapi.ui.message_notify(self._rhapi.language.__(message))

        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_BACKPACK_SET_MODE)
        payload = bytearray((ord("B"),))
        packet.set_payload(payload)
        self.send_msp(packet)

    def activate_wifi(self, *_) -> None:
        """
        Sends a packet to put the connected device in
        bind mode
        """
        message = "バックパックの WiFi を起動中..."
        self._rhapi.ui.message_notify(self._rhapi.language.__(message))

        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_BACKPACK_SET_MODE)
        payload = bytearray((ord("W"),))
        packet.set_payload(payload)
        self.send_msp(packet)

    #
    # Field Tests
    #

    def test_bind_osd(self, *_):
        """
        A test for checking the connection of the pilot
        bound to the timer backpack
        """

        def test():
            self._queue_lock.acquire()
            text = "ROTORHAZARD"
            for row in range(18):
                self.send_clear_osd()
                start_col = self.center_osd(len(text))
                self.send_osd_text(row, start_col, text)
                self.send_display_osd()

                gevent.sleep(0.5)

                self.send_clear_osd_row(row)
                self.send_display_osd()

            gevent.sleep(1)
            self.send_clear_osd()
            self.send_display_osd()
            self._queue_lock.release()

        gevent.spawn(test)

    #
    # VRxC Event Triggers
    #

    def pilot_alter(self, args: dict) -> None:
        """
        Logs the uid change of the pilot

        :param args: _description_
        """
        pilot_id = args["pilot_id"]
        uid = self.get_pilot_uid(pilot_id)
        uid_formated = ".".join([str(int.from_bytes((byte,))) for byte in uid])
        logger.info("Pilot %s's UID set to %s", pilot_id, uid_formated)

    def onRaceStage(self, args) -> None:
        """
        _summary_

        :param args: _description_
        """
        if not self._backpack_connected:
            return

        use_heat_name = self._rhapi.db.option("_heat_name") == "1"
        use_round_num = self._rhapi.db.option("_round_num") == "1"
        use_class_name = self._rhapi.db.option("_class_name") == "1"
        use_event_name = self._rhapi.db.option("_event_name") == "1"

        # Pull heat name and rounds
        heat_data = self._rhapi.db.heat_by_id(args["heat_id"])
        if heat_data:
            class_id = heat_data.class_id
            heat_name = heat_data.display_name
            round_num = self._rhapi.db.heat_max_round(args["heat_id"]) + 1
        else:
            class_id = None
            heat_name = None
            round_num = None

        # Check class name
        if class_id:
            raceclass = self._rhapi.db.raceclass_by_id(class_id)
            class_name = raceclass.display_name
        else:
            raceclass = None
            class_name = None

        # Generate heat message
        heat_name_row = self._rhapi.db.option("_heatname_row")
        if all([use_heat_name, use_round_num, heat_name, round_num]):
            round_trans = "ラウンド"
            heat_message = (
                f"x {heat_name.upper()} | {round_trans.upper()} {round_num} w"
            )
            heat_start_col = self._get_col(heat_message, "_heatname_col")
            heat_message_parms = (heat_name_row, heat_start_col, heat_message)
        elif use_heat_name and heat_name:
            heat_message = f"x {heat_name.upper()} w"
            heat_start_col = self._get_col(heat_message, "_heatname_col")
            heat_message_parms = (heat_name_row, heat_start_col, heat_message)
        else:
            heat_message_parms = None

        # Generate class message
        class_name_row = self._rhapi.db.option("_classname_row")
        if use_class_name and class_name:
            class_message = f"x {class_name.upper()} w"
            class_start_col = self._get_col(class_message, "_classname_col")
            class_message_parms = (class_name_row, class_start_col, class_message)

        # Generate event message
        event_name_row = self._rhapi.db.option("_eventname_row")
        event_name = self._rhapi.db.option("eventName")
        if use_event_name and event_name:
            event_name = self._rhapi.db.option("eventName")
            event_message = heat_message = f"x {event_name.upper()} w"
            event_start_col = self._get_col(event_message, "_eventname_col")
            event_message_parms = (event_name_row, event_start_col, event_message)

        _stage_msg = self._rhapi.db.option("_racestage_message")
        start_col = self._get_col(_stage_msg, "_status_col")
        stage_mesage = (
            self._rhapi.db.option("_status_row"),
            start_col,
            self._rhapi.db.option("_racestage_message"),
        )

        # Send stage message to all pilots
        def arm(pilot_id):
            uid = self.get_pilot_uid(pilot_id)
            with self._queue_lock:
                self.set_send_uid(uid)
                self.send_clear_osd()

                # Send messages to backpack
                self.send_osd_text(*stage_mesage)
                if use_heat_name and heat_name:
                    assert heat_message_parms is not None
                    self.send_osd_text(*heat_message_parms)
                if use_class_name and class_name:
                    self.send_osd_text(*class_message_parms)
                if use_event_name and event_name:
                    self.send_osd_text(*event_message_parms)

                self.send_display_osd()
                self.reset_send_uid()

        seat_pilots = self._rhapi.race.pilots
        for seat in seat_pilots:
            if (
                seat_pilots[seat]
                and self._rhapi.db.pilot_attribute_value(
                    seat_pilots[seat], "elrs_active"
                )
                == "1"
            ):
                gevent.spawn(arm, seat_pilots[seat])

    def onRaceStart(self, *_) -> None:
        if not self._backpack_connected:
            return

        def start(pilot_id):
            uid = self.get_pilot_uid(pilot_id)
            start_col = self._get_col(
                self._rhapi.db.option("_racestart_message"), "_status_col"
            )

            self._queue_lock.acquire()
            self.set_send_uid(uid)

            self.send_clear_osd()

            self.send_osd_text(
                self._rhapi.db.option("_status_row"),
                start_col,
                self._rhapi.db.option("_racestart_message"),
            )
            self.send_display_osd()
            self.reset_send_uid()
            self._queue_lock.release()

            gevent.sleep(self._rhapi.db.option("_racestart_uptime") * 1e-1)

            self._queue_lock.acquire()
            self.set_send_uid(uid)
            self.send_clear_osd_row(self._rhapi.db.option("_status_row"))
            self.send_display_osd()
            self.reset_send_uid()
            self._queue_lock.release()

        seat_pilots = self._rhapi.race.pilots
        for seat in seat_pilots:
            if (
                seat_pilots[seat]
                and self._rhapi.db.pilot_attribute_value(
                    seat_pilots[seat], "elrs_active"
                )
                == "1"
            ):
                gevent.spawn(start, seat_pilots[seat])

    def onRaceFinish(self, *_) -> None:
        if not self._backpack_connected:
            return

        def finish(pilot_id):
            uid = self.get_pilot_uid(pilot_id)
            start_col = self._get_col(
                self._rhapi.db.option("_racefinish_message"), "_status_col"
            )

            self._queue_lock.acquire()
            self.set_send_uid(uid)
            self.send_clear_osd_row(self._rhapi.db.option("_status_row"))
            self.send_osd_text(
                self._rhapi.db.option("_status_row"),
                start_col,
                self._rhapi.db.option("_racefinish_message"),
            )
            self.send_display_osd()
            self.reset_send_uid()
            self._queue_lock.release()

            gevent.sleep(self._rhapi.db.option("_finish_uptime") * 1e-1)

            self._queue_lock.acquire()
            self.set_send_uid(uid)
            self.send_clear_osd_row(self._rhapi.db.option("_status_row"))
            self.send_display_osd()
            self.reset_send_uid()
            self._queue_lock.release()

        seat_pilots = self._rhapi.race.pilots
        seats_finished = self._rhapi.race.seats_finished

        for seat in seat_pilots:
            if (
                seat_pilots[seat]
                and self._rhapi.db.pilot_attribute_value(
                    seat_pilots[seat], "elrs_active"
                )
                == "1"
            ):
                if not seats_finished[seat]:
                    gevent.spawn(finish, seat_pilots[seat])

    def onRaceStop(self, *_) -> None:
        if not self._backpack_connected:
            return

        def land(pilot_id):
            uid = self.get_pilot_uid(pilot_id)
            start_col = self._get_col(self._rhapi.db.option("_racestop_message"), "_status_col")

            self._queue_lock.acquire()
            self.set_send_uid(uid)
            self.send_osd_text(
                self._rhapi.db.option("_status_row"),
                start_col,
                self._rhapi.db.option("_racestop_message"),
            )
            self.send_display_osd()
            self.reset_send_uid()
            self._queue_lock.release()

        seat_pilots = self._rhapi.race.pilots
        seats_finished = self._rhapi.race.seats_finished

        for seat in seat_pilots:
            if (
                seat_pilots[seat]
                and self._rhapi.db.pilot_attribute_value(
                    seat_pilots[seat], "elrs_active"
                )
                == "1"
            ):
                if not seats_finished[seat]:
                    gevent.spawn(land, seat_pilots[seat])

    def onRaceLapRecorded(self, args: dict) -> None:
        if not self._backpack_connected:
            return

        def update_pos(result):
            pilot_id = result["pilot_id"]

            if self._rhapi.db.option("_position_mode") != "1":
                message = f"LAP: {result['laps'] + 1}"
            else:
                message = f"POSN: {str(result['position']).upper()} | LAP: {result['laps'] + 1}"

            # Skip if OSD for this pilot already shows this exact message
            last = self._last_sent_osd.setdefault(pilot_id, {})
            if last.get("pos") == message:
                return
            last["pos"] = message

            start_col = self._get_col(message, "_currentlap_col")

            uid = self.get_pilot_uid(pilot_id)
            self._queue_lock.acquire()
            self.set_send_uid(uid)
            self.send_clear_osd_row(self._rhapi.db.option("_currentlap_row"))

            self.send_osd_text(
                self._rhapi.db.option("_currentlap_row"), start_col, message
            )
            self.send_display_osd()
            self.reset_send_uid()
            self._queue_lock.release()

        def lap_results(result, gap_info):
            pilot_id = result["pilot_id"]

            message = ""
            if self._rhapi.db.option("_gap_mode") != "1":
                if gap_info.race.win_condition == WinCondition.FASTEST_CONSECUTIVE:
                    formatted_time1 = self._rhapi.utils.format_split_time_to_str(
                        gap_info.current.last_lap_time, "{m}:{s}.{d}"
                    )
                    formatted_time2 = self._rhapi.utils.format_split_time_to_str(
                        gap_info.current.consecutives, "{m}:{s}.{d}"
                    )
                    message = f"x {formatted_time1} | {gap_info.current.consecutives_base}/{formatted_time2} w"
                elif (
                    gap_info.race.win_condition == WinCondition.FASTEST_LAP
                    and gap_info.current.is_best_lap
                ):
                    formatted_time = self._rhapi.utils.format_split_time_to_str(
                        gap_info.current.last_lap_time, "{m}:{s}.{d}"
                    )
                    message = f"x BEST LAP | {formatted_time} w"
                elif gap_info.race.win_condition in (
                    WinCondition.FASTEST_LAP,
                    WinCondition.FIRST_TO_LAP_X,
                ):
                    formatted_time1 = self._rhapi.utils.format_split_time_to_str(
                        gap_info.current.last_lap_time, "{m}:{s}.{d}"
                    )
                    formatted_time2 = self._rhapi.utils.format_split_time_to_str(
                        gap_info.current.total_time_laps, "{m}:{s}.{d}"
                    )
                    message = f"x {formatted_time2} | {formatted_time1} w"
                else:
                    # Lap timer only (MOST_LAPS / NONE) - show single lap time
                    formatted_time = self._rhapi.utils.format_split_time_to_str(
                        gap_info.current.last_lap_time, "{m}:{s}.{d}"
                    )
                    message = f"x {formatted_time} w"

            elif gap_info.race.win_condition == WinCondition.FASTEST_CONSECUTIVE:
                formatted_time1 = self._rhapi.utils.format_split_time_to_str(
                    gap_info.current.last_lap_time, "{m}:{s}.{d}"
                )
                formatted_time2 = self._rhapi.utils.format_split_time_to_str(
                    gap_info.current.consecutives, "{m}:{s}.{d}"
                )
                message = f"x {formatted_time1} | {gap_info.current.consecutives_base}/{formatted_time2} w"

            elif gap_info.race.win_condition == WinCondition.FASTEST_LAP:
                if gap_info.next_rank.diff_time:
                    formatted_time = self._rhapi.utils.format_split_time_to_str(
                        gap_info.next_rank.diff_time, "{m}:{s}.{d}"
                    )
                    formatted_callsign = str.upper(gap_info.next_rank.callsign)
                    message = f"x {formatted_callsign} | +{formatted_time} w"

                elif gap_info.current.is_best_lap and gap_info.current.lap_number:
                    formatted_time = self._rhapi.utils.format_split_time_to_str(
                        gap_info.current.last_lap_time, "{m}:{s}.{d}"
                    )
                    message = f"x {self._rhapi.db.option('_leader_message')} | {formatted_time} w"

                elif gap_info.current.lap_number:
                    formatted_time = self._rhapi.utils.format_split_time_to_str(
                        gap_info.first_rank.diff_time, "{m}:{s}.{d}"
                    )
                    formatted_callsign = str.upper(gap_info.first_rank.callsign)
                    message = f"x {formatted_callsign} | +{formatted_time} w"

            else:
                if gap_info.race.win_condition == WinCondition.FIRST_TO_LAP_X:
                    if gap_info.next_rank.diff_time:
                        formatted_time = self._rhapi.utils.format_split_time_to_str(
                            gap_info.next_rank.diff_time, "{m}:{s}.{d}"
                        )
                        formatted_callsign = str.upper(gap_info.next_rank.callsign)
                        message = f"x {formatted_callsign} | +{formatted_time} w"

                    elif gap_info.current.lap_number:
                        formatted_time = self._rhapi.utils.format_split_time_to_str(
                            gap_info.current.last_lap_time, "{m}:{s}.{d}"
                        )
                        message = f"x {self._rhapi.db.option('_leader_message')} | {formatted_time} w"
                else:
                    # Lap timer only (MOST_LAPS / NONE) - show single lap time
                    if gap_info.current.lap_number:
                        formatted_time = self._rhapi.utils.format_split_time_to_str(
                            gap_info.current.last_lap_time, "{m}:{s}.{d}"
                        )
                        message = f"x {formatted_time} w"

            start_col = self._get_col(message, "_lapresults_col")

            uid = self.get_pilot_uid(pilot_id)
            self._queue_lock.acquire()
            self.set_send_uid(uid)
            self.send_osd_text(
                self._rhapi.db.option("_lapresults_row"), start_col, message
            )
            self.send_display_osd()
            self.reset_send_uid()
            self._queue_lock.release()

            gevent.sleep(self._rhapi.db.option("_results_uptime") * 1e-1)

            self._queue_lock.acquire()
            self.set_send_uid(uid)
            self.send_clear_osd_row(self._rhapi.db.option("_lapresults_row"))
            self.send_display_osd()
            self.reset_send_uid()
            self._queue_lock.release()

        seats_finished = self._rhapi.race.seats_finished
        pilots_completion = {}
        for slot, pilot_id in self._rhapi.race.pilots.items():
            if pilot_id:
                pilots_completion[pilot_id] = seats_finished[slot]

        results = args["results"]["by_race_time"]
        for result in results:
            if (
                self._rhapi.db.pilot_attribute_value(result["pilot_id"], "elrs_active")
                == "1"
            ):
                if not pilots_completion[result["pilot_id"]]:
                    gevent.spawn(update_pos, result)

                    if result["pilot_id"] == args["pilot_id"] and (result["laps"] > 0):
                        gevent.spawn(lap_results, result, args["gap_info"])

    def onLapDelete(self, *_) -> None:
        """
        Update a pilot's OSD when a they have finished
        """
        if not self._backpack_connected:
            return

        def delete(pilot_id):
            uid = self.get_pilot_uid(pilot_id)
            self._queue_lock.acquire()
            self.set_send_uid(uid)
            self.send_clear_osd()
            self.send_display_osd()
            self.reset_send_uid()
            self._queue_lock.release()

        if self._rhapi.db.option("_results_mode") == "1":
            seat_pilots = self._rhapi.race.pilots
            for seat in seat_pilots:
                if (
                    seat_pilots[seat]
                    and self._rhapi.db.pilot_attribute_value(
                        seat_pilots[seat], "elrs_active"
                    )
                    == "1"
                ):
                    gevent.spawn(delete, seat_pilots[seat])

    def onRacePilotDone(self, args: dict) -> None:
        """
        Update a pilot's OSD when a they have finished
        """
        if not self._backpack_connected:
            return

        def done(result, win_condition):
            pilot_id = result["pilot_id"]
            start_col = self._get_col(
                self._rhapi.db.option("_pilotdone_message"), "_status_col"
            )
            results_row1 = self._rhapi.db.option("_results_row")
            results_row2 = results_row1 + 1

            uid = self.get_pilot_uid(pilot_id)
            self._queue_lock.acquire()
            self.set_send_uid(uid)
            self.send_clear_osd_row(self._rhapi.db.option("_currentlap_row"))
            self.send_clear_osd_row(self._rhapi.db.option("_status_row"))
            self.send_osd_text(
                self._rhapi.db.option("_status_row"),
                start_col,
                self._rhapi.db.option("_pilotdone_message"),
            )

            if self._rhapi.db.option("_results_mode") == "1":
                placement_message = f"PLACEMENT: {result['position']}"
                place_col = self._get_col(placement_message, "_results_col")
                self.send_osd_text(results_row1, place_col, placement_message)

                if win_condition == WinCondition.FASTEST_CONSECUTIVE:
                    win_message = f"FASTEST {result['consecutives_base']} CONSEC: {result['consecutives']}"
                elif win_condition == WinCondition.FASTEST_LAP:
                    win_message = f"FASTEST LAP: {result['fastest_lap']}"
                elif win_condition == WinCondition.FIRST_TO_LAP_X:
                    win_message = f"TOTAL TIME: {result['total_time']}"
                else:
                    win_message = f"LAPS COMPLETED: {result['laps']}"

                win_col = self._get_col(win_message, "_results_col")
                self.send_osd_text(results_row2, win_col, win_message)

            self.send_display_osd()
            self.reset_send_uid()
            self._queue_lock.release()

            gevent.sleep(self._rhapi.db.option("_finish_uptime") * 1e-1)

            self._queue_lock.acquire()
            self.set_send_uid(uid)
            self.send_clear_osd_row(self._rhapi.db.option("_status_row"))
            self.send_display_osd()
            self.reset_send_uid()
            self._queue_lock.release()

        results = args["results"]
        leaderboard = results[results["meta"]["primary_leaderboard"]]
        for result in leaderboard:
            if (
                self._rhapi.db.pilot_attribute_value(args["pilot_id"], "elrs_active")
                == "1"
            ) and (result["pilot_id"] == args["pilot_id"]):
                gevent.spawn(done, result, results["meta"]["win_condition"])
                break

    def onLapsClear(self, *_) -> None:
        """
        Removes data from pilot's OSD when laps are removed from the system
        """
        if not self._backpack_connected:
            return

        def clear(pilot_id):
            uid = self.get_pilot_uid(pilot_id)
            self._queue_lock.acquire()
            self.set_send_uid(uid)
            self.send_clear_osd()
            self.send_display_osd()
            self.reset_send_uid()
            self._queue_lock.release()

        seat_pilots = self._rhapi.race.pilots
        for seat in seat_pilots:
            if (
                seat_pilots[seat]
                and self._rhapi.db.pilot_attribute_value(
                    seat_pilots[seat], "elrs_active"
                )
                == "1"
            ):
                gevent.spawn(clear, seat_pilots[seat])

    def onSendMessage(self, args: dict | None = None) -> None:
        """
        Sends custom text to pilots of the active heat
        """
        if not self._backpack_connected:
            return

        if args is None:
            return

        def notify(pilot):
            uid = self.get_pilot_uid(pilot)
            start_col = self._get_col(args["message"], "_announcement_col")
            self._queue_lock.acquire()
            self.set_send_uid(uid)
            self.send_osd_text(
                self._rhapi.db.option("_announcement_row"),
                start_col,
                f"x {str.upper(args['message'])} w",
            )
            self.send_display_osd()
            self.reset_send_uid()
            self._queue_lock.release()

            gevent.sleep(self._rhapi.db.option("_announcement_uptime") * 1e-1)

            self._queue_lock.acquire()
            self.set_send_uid(uid)
            self.send_clear_osd_row(self._rhapi.db.option("_announcement_row"))
            self.send_display_osd()
            self.reset_send_uid()
            self._queue_lock.release()

        seat_pilots = self._rhapi.race.pilots
        for seat in seat_pilots:
            if (
                seat_pilots[seat]
                and self._rhapi.db.pilot_attribute_value(
                    seat_pilots[seat], "elrs_active"
                )
                == "1"
            ):
                gevent.spawn(notify, seat_pilots[seat])
