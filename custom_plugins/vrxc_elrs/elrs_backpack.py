import hashlib
import logging
import time

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


class ELRSBackpack(VRxController):
    _connection: BackpackConnection | None = None
    _reconnect_greenlet: gevent.Greenlet | None = None
    _race_clock_greenlet: gevent.Greenlet | None = None
    _race_start_time: float = 0.0

    def __init__(self, name, label, rhapi):
        super().__init__(name, label)
        self._rhapi = rhapi
        self._send_queue = Queue()
        # Unbounded queue: a maxsize cap would block the receive greenlet and
        # stall the entire gevent loop while waiting for space.
        self._recieve_queue = Queue()
        self._queue_lock = gevent.lock.RLock()
        self._manual_disconnect = True
        self._last_sent_osd: dict[int, dict[str, str]] = {}
        self._best_laps: dict[int, int] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _backpack_connected(self) -> bool:
        if self._connection is None:
            return False
        return self._connection.connected

    def _get_rd_uid(self) -> bytes | None:
        """Return the race-director UID derived from the configured bind phrase."""
        phrase = self._rhapi.db.option("_rd_bindphrase")
        return self.hash_phrase(phrase) if phrase else None

    def _active_pilot_ids(self) -> list[int]:
        """Return pilot IDs in the current heat that have ELRS OSD enabled."""
        return [
            pid
            for pid in self._rhapi.race.pilots.values()
            if pid
            and self._rhapi.db.pilot_attribute_value(pid, "elrs_active") == "1"
        ]

    def _broadcast_uids(self, pilot_ids: list[int], include_rd: bool = True) -> list[bytes]:
        """
        Build the list of UIDs to send OSD to.
        Includes active pilots and optionally the race director.
        """
        uids = [self.get_pilot_uid(pid) for pid in pilot_ids]
        if include_rd:
            rd_uid = self._get_rd_uid()
            if rd_uid:
                uids.append(rd_uid)
        return uids

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_handlers(self, args) -> None:
        args["register_fn"](self)

    def start_race(self):
        if self._rhapi.db.option("_race_start") == "1":
            if self._rhapi.race.status == RaceStatus.READY:
                self._rhapi.race.stage({"start_time_s": 10})

    def stop_race(self):
        if self._rhapi.db.option("_race_stop") == "1":
            status = self._rhapi.race.status
            if status in (RaceStatus.STAGING, RaceStatus.RACING):
                if self._rhapi.db.option("_autosave_on_stop") == "1":
                    self._rhapi.race.save()
                else:
                    self._rhapi.race.stop()

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------

    def start_recieve_loop(self, *_):
        gevent.spawn(self.recieve_loop)
        logger.info("Backpack recieve greenlet started.")

    def start_connection(self, *_) -> None:
        self._manual_disconnect = False
        self._attempt_connect(notify=True)
        self._start_reconnect_monitor()

    def _attempt_connect(self, notify: bool = True) -> bool:
        if self._backpack_connected:
            if notify:
                self._rhapi.ui.message_notify(
                    self._rhapi.language.__("バックパックはすでに接続されています")
                )
            return True

        id_ = self._rhapi.db.option("_conn_opt", None, as_int=True)
        for con in ConnectionTypeEnum:
            if id_ == con.id_:
                break
        else:
            if notify:
                self._rhapi.ui.message_notify(
                    self._rhapi.language.__("接続タイプが指定されていません")
                )
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
                    self._rhapi.ui.message_notify(
                        self._rhapi.language.__("Raspberry Pi 上で動作していません")
                    )
                return False

        elif con == ConnectionTypeEnum.SOCKET:
            addr = self._rhapi.db.option("_socket_ip", None)
            if addr is None:
                if notify:
                    self._rhapi.ui.message_notify(
                        self._rhapi.language.__("ソケットの IP アドレスが指定されていません")
                    )
                return False
            try:
                ip_addr = socket.gethostbyname(addr)
            except socket.gaierror:
                if notify:
                    self._rhapi.ui.message_notify(
                        self._rhapi.language.__("デバイスのソケットへの接続に失敗しました")
                    )
                return False
            return self._establish_connection(con.type_, ip_addr=ip_addr, notify=notify)

        return False

    def _establish_connection(
        self,
        connection_type: type[BackpackConnection],
        notify: bool = True,
        **kwargs,
    ) -> bool:
        while not self._send_queue.empty():
            self._send_queue.get()

        self._last_sent_osd.clear()

        self._connection = connection_type(self._send_queue, self._recieve_queue)
        if not self._connection.connect(**kwargs):
            if notify:
                self._rhapi.ui.message_notify(
                    self._rhapi.language.__("バックパック接続の確立に失敗しました")
                )
            return False

        if notify:
            self._rhapi.ui.message_notify(
                self._rhapi.language.__("バックパックへの接続に成功しました")
            )
        else:
            logger.info("バックパックへの接続に成功しました")
            self._rhapi.ui.message_notify(
                self._rhapi.language.__("バックパックへ自動再接続しました")
            )

        self.version_request()
        return True

    def _start_reconnect_monitor(self) -> None:
        if self._reconnect_greenlet is None or self._reconnect_greenlet.dead:
            self._reconnect_greenlet = gevent.spawn(self._reconnect_loop)
            logger.info("Auto-reconnect monitor started")

    def _reconnect_loop(self) -> None:
        while True:
            try:
                interval = int(self._rhapi.db.option("_reconnect_interval") or 3)
            except (TypeError, ValueError):
                interval = 3
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
        try:
            while True:
                packet: MSPPacket = self._recieve_queue.get()

                if packet.type_ == MSPPacketType.RESPONSE:
                    if packet.function == MSPTypes.MSP_ELRS_GET_BACKPACK_VERSION:
                        version = bytes(i for i in packet.payload if i != 0).decode("utf-8")
                        message = f"バックパックファームウェアバージョン: {version}"
                        logger.info(message)
                        self._rhapi.ui.message_notify(self._rhapi.language.__(message))

                if packet.type_ == MSPPacketType.COMMAND:
                    if packet.function == MSPTypes.MSP_ELRS_BACKPACK_SET_RECORDING_STATE:
                        itr = packet.iterate_payload()
                        val = next(itr)
                        switch_type = self._rhapi.db.option("_tx_switch_type") or "toggle"
                        if switch_type == "push":
                            # Push: react only on press (0x01); toggle race state
                            if val == 0x01:
                                status = self._rhapi.race.status
                                if status == RaceStatus.READY:
                                    self.start_race()
                                elif status in (RaceStatus.STAGING, RaceStatus.RACING):
                                    self.stop_race()
                        else:
                            # Toggle: 0x01 = start, 0x00 = stop
                            if val == 0x00:
                                self.stop_race()
                            elif val == 0x01:
                                self.start_race()

        except KeyboardInterrupt:
            logger.error("Stopping backpack connector greenlet")

    def _clear_all_osd(self) -> None:
        """Clear OSD for all active pilots in the current heat."""
        for pid in self._active_pilot_ids():
            try:
                uid = self.get_pilot_uid(pid)
                with self._queue_lock:
                    self.set_send_uid(uid)
                    self.send_clear_osd()
                    self.send_display_osd()
                    self.reset_send_uid()
            except Exception:
                pass

    def disconnect(self, *_) -> None:
        self._manual_disconnect = True

        if self._reconnect_greenlet is not None:
            self._reconnect_greenlet.kill()
            self._reconnect_greenlet = None

        if self._race_clock_greenlet is not None:
            self._race_clock_greenlet.kill()
            self._race_clock_greenlet = None

        if not self._backpack_connected:
            self._rhapi.ui.message_notify(
                self._rhapi.language.__("バックパックが接続されていません")
            )
            return

        self._clear_all_osd()

        assert self._connection is not None
        self._connection.disconnect()

        self._rhapi.ui.message_notify(
            self._rhapi.language.__("バックパックが切断されました")
        )

    # ------------------------------------------------------------------
    # Packet construction
    # ------------------------------------------------------------------

    def hash_phrase(self, bindphrase: str) -> bytes:
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
        assert pilot_id > 0, "Can not generate backpack uid for invalid pilot"
        bindphrase = self._rhapi.db.pilot_attribute_value(pilot_id, "comm_elrs")
        if bindphrase:
            return self.hash_phrase(bindphrase)
        pilot = self._rhapi.db.pilot_by_id(pilot_id)
        assert pilot is not None, "Pilot not in database"
        return self.hash_phrase(pilot.callsign)

    def center_osd(self, len_: int) -> int:
        offset = len_ // 2
        return max(50 // 2 - offset, 0)

    def _format_time(self, ms: int) -> str:
        """Format milliseconds to M:SS.T (tenths of a second)."""
        total_s = ms / 1000
        m = int(total_s // 60)
        s = int(total_s % 60)
        t = int((total_s % 1) * 10)
        return f"{m}:{s:02d}.{t}"

    def _get_pos(self, pos_option: str, text: str = "") -> tuple[int, int]:
        """Parse a 'row,col' option string. Negative col means auto-center."""
        try:
            raw = self._rhapi.db.option(pos_option) or ""
            parts = raw.split(",")
            row = int(parts[0].strip())
            col = int(parts[1].strip()) if len(parts) > 1 else -1
        except (TypeError, ValueError, IndexError):
            row = 0
            col = -1
        if col < 0:
            col = self.center_osd(len(text)) if text else 0
        return row, col

    def send_msp(self, msp: MSPPacket) -> None:
        if self._backpack_connected:
            self._send_queue.put(msp)

    def set_send_uid(self, address: bytes) -> None:
        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_SET_SEND_UID)
        payload = bytearray()
        payload.append(0x01)
        payload += address
        packet.set_payload(payload)
        self.send_msp(packet)

    def reset_send_uid(self) -> None:
        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_SET_SEND_UID)
        payload = bytearray()
        payload.append(0x00)
        packet.set_payload(payload)
        self.send_msp(packet)

    def send_clear_osd(self) -> None:
        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_SET_OSD)
        payload = bytearray()
        payload.append(0x02)
        packet.set_payload(payload)
        self.send_msp(packet)

    def send_osd_text(self, row: int, col: int, text: str) -> None:
        payload = bytearray((0x03, row, col, 0))
        for index, char in enumerate(text):
            if index >= 50:
                break
            char_code = ord(char)
            if char_code > 255:
                continue
            payload.append(char_code)

        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_SET_OSD)
        packet.set_payload(payload)
        self.send_msp(packet)

    def send_display_osd(self) -> None:
        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_SET_OSD)
        payload = bytearray((0x04,))
        packet.set_payload(payload)
        self.send_msp(packet)

    def send_clear_osd_row(self, row: int) -> None:
        payload = bytearray((0x03, row, 0, 0))
        for _ in range(50):
            payload.append(0)

        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_SET_OSD)
        packet.set_payload(payload)
        self.send_msp(packet)

    def version_request(self):
        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_GET_BACKPACK_VERSION)
        self.send_msp(packet)

    def activate_bind(self, *_) -> None:
        self._rhapi.ui.message_notify(
            self._rhapi.language.__("バックパックのバインドモードを起動中...")
        )
        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_BACKPACK_SET_MODE)
        packet.set_payload(bytearray((ord("B"),)))
        self.send_msp(packet)

    def activate_wifi(self, *_) -> None:
        self._rhapi.ui.message_notify(
            self._rhapi.language.__("バックパックの WiFi を起動中...")
        )
        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_BACKPACK_SET_MODE)
        packet.set_payload(bytearray((ord("W"),)))
        self.send_msp(packet)

    # ------------------------------------------------------------------
    # Field test
    # ------------------------------------------------------------------

    def test_bind_osd(self, *_):
        def test():
            text = "ROTORHAZARD"
            start_col = self.center_osd(len(text))
            for row in range(18):
                # Lock is released between sleeps to avoid blocking other events.
                with self._queue_lock:
                    self.send_clear_osd()
                    self.send_osd_text(row, start_col, text)
                    self.send_display_osd()

                gevent.sleep(0.5)

                with self._queue_lock:
                    self.send_clear_osd_row(row)
                    self.send_display_osd()

            gevent.sleep(1)
            with self._queue_lock:
                self.send_clear_osd()
                self.send_display_osd()

        gevent.spawn(test)

    # ------------------------------------------------------------------
    # Pilot attribute logging
    # ------------------------------------------------------------------

    def pilot_alter(self, args: dict) -> None:
        pilot_id = args["pilot_id"]
        uid = self.get_pilot_uid(pilot_id)
        uid_formated = ".".join([str(int.from_bytes((byte,))) for byte in uid])
        logger.info("Pilot %s's UID set to %s", pilot_id, uid_formated)

    # ------------------------------------------------------------------
    # Race clock
    # ------------------------------------------------------------------

    def _race_clock_loop(self) -> None:
        logger.info("Race clock loop started")
        first_tick = True
        while True:
            gevent.sleep(1)
            if not self._backpack_connected:
                continue

            elapsed = int(time.time() - self._race_start_time)
            mm = elapsed // 60
            ss = elapsed % 60
            message = f"{mm:02d}:{ss:02d}"
            clock_row, clock_col = self._get_pos("_raceclock_pos", message)

            uids = self._broadcast_uids(self._active_pilot_ids())
            sent_count = 0
            for uid in uids:
                try:
                    with self._queue_lock:
                        self.set_send_uid(uid)
                        self.send_osd_text(clock_row, clock_col, message)
                        self.send_display_osd()
                        self.reset_send_uid()
                    sent_count += 1
                except Exception:
                    logger.exception("Race clock OSD error")

            if first_tick:
                logger.info(
                    "Race clock first tick: %s, sent to %d recipient(s) at row=%d col=%d",
                    message, sent_count, clock_row, clock_col,
                )
                first_tick = False

    def _stop_race_clock(self) -> None:
        if self._race_clock_greenlet is not None:
            self._race_clock_greenlet.kill()
            self._race_clock_greenlet = None

        if not self._backpack_connected:
            return
        if self._rhapi.db.option("_show_raceclock") != "1":
            return

        clock_row, _ = self._get_pos("_raceclock_pos")
        for pid in self._active_pilot_ids():
            try:
                uid = self.get_pilot_uid(pid)
                with self._queue_lock:
                    self.set_send_uid(uid)
                    self.send_clear_osd_row(clock_row)
                    self.send_display_osd()
                    self.reset_send_uid()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # VRxC event handlers
    # ------------------------------------------------------------------

    def onRaceStage(self, args) -> None:
        if not self._backpack_connected:
            return

        # Clear dedup caches so every pilot sees fresh OSD on each new race.
        self._last_sent_osd.clear()
        self._best_laps.clear()

        use_heat_name = self._rhapi.db.option("_heat_name") == "1"
        use_round_num = self._rhapi.db.option("_round_num") == "1"
        use_class_name = self._rhapi.db.option("_class_name") == "1"
        use_event_name = self._rhapi.db.option("_event_name") == "1"

        heat_data = self._rhapi.db.heat_by_id(args["heat_id"])
        if heat_data:
            class_id = heat_data.class_id
            heat_name = heat_data.display_name
            round_num = self._rhapi.db.heat_max_round(args["heat_id"]) + 1
        else:
            class_id = None
            heat_name = None
            round_num = None

        if class_id:
            raceclass = self._rhapi.db.raceclass_by_id(class_id)
            class_name = raceclass.display_name
        else:
            class_name = None

        # Build optional message parameters
        if all([use_heat_name, use_round_num, heat_name, round_num]):
            heat_message = f"{heat_name.upper()} | ラウンド {round_num}"
            heat_row, heat_col = self._get_pos("_heatname_pos", heat_message)
            heat_message_parms = (heat_row, heat_col, heat_message)
        elif use_heat_name and heat_name:
            heat_message = f"{heat_name.upper()}"
            heat_row, heat_col = self._get_pos("_heatname_pos", heat_message)
            heat_message_parms = (heat_row, heat_col, heat_message)
        else:
            heat_message_parms = None

        if use_class_name and class_name:
            class_message = class_name.upper()
            class_row, class_col = self._get_pos("_classname_pos", class_message)
            class_message_parms = (class_row, class_col, class_message)
        else:
            class_message_parms = None

        event_name = self._rhapi.db.option("eventName")
        if use_event_name and event_name:
            event_message = event_name.upper()
            event_row, event_col = self._get_pos("_eventname_pos", event_message)
            event_message_parms = (event_row, event_col, event_message)
        else:
            event_message_parms = None

        _stage_msg = self._rhapi.db.option("_racestage_message")
        stage_row, stage_col = self._get_pos("_status_pos", _stage_msg)
        stage_mesage = (stage_row, stage_col, _stage_msg)

        def arm(uid):
            with self._queue_lock:
                self.set_send_uid(uid)
                self.send_clear_osd()
                self.send_osd_text(*stage_mesage)
                if heat_message_parms:
                    self.send_osd_text(*heat_message_parms)
                if class_message_parms:
                    self.send_osd_text(*class_message_parms)
                if event_message_parms:
                    self.send_osd_text(*event_message_parms)
                self.send_display_osd()
                self.reset_send_uid()

        for uid in self._broadcast_uids(self._active_pilot_ids()):
            gevent.spawn(arm, uid)

    def onRaceStart(self, *_) -> None:
        if not self._backpack_connected:
            return

        if self._rhapi.db.option("_show_raceclock") == "1":
            self._race_start_time = time.time()
            if self._race_clock_greenlet is None or self._race_clock_greenlet.dead:
                self._race_clock_greenlet = gevent.spawn(self._race_clock_loop)

        msg = self._rhapi.db.option("_racestart_message")
        status_row, start_col = self._get_pos("_status_pos", msg)

        def start(uid):
            with self._queue_lock:
                self.set_send_uid(uid)
                self.send_clear_osd()
                self.send_osd_text(status_row, start_col, msg)
                self.send_display_osd()
                self.reset_send_uid()

            gevent.sleep(self._rhapi.db.option("_racestart_uptime") * 1e-1)

            with self._queue_lock:
                self.set_send_uid(uid)
                self.send_clear_osd_row(status_row)
                self.send_display_osd()
                self.reset_send_uid()

        for uid in self._broadcast_uids(self._active_pilot_ids()):
            gevent.spawn(start, uid)

    def onRaceFinish(self, *_) -> None:
        if not self._backpack_connected:
            return

        msg = self._rhapi.db.option("_racefinish_message")
        status_row, finish_col = self._get_pos("_status_pos", msg)

        seats_finished = self._rhapi.race.seats_finished

        def finish(uid):
            with self._queue_lock:
                self.set_send_uid(uid)
                self.send_clear_osd_row(status_row)
                self.send_osd_text(status_row, finish_col, msg)
                self.send_display_osd()
                self.reset_send_uid()

            gevent.sleep(self._rhapi.db.option("_finish_uptime") * 1e-1)

            with self._queue_lock:
                self.set_send_uid(uid)
                self.send_clear_osd_row(status_row)
                self.send_display_osd()
                self.reset_send_uid()

        seat_pilots = self._rhapi.race.pilots
        for seat, pid in seat_pilots.items():
            if (
                pid
                and self._rhapi.db.pilot_attribute_value(pid, "elrs_active") == "1"
                and not seats_finished[seat]
            ):
                gevent.spawn(finish, self.get_pilot_uid(pid))

    def onRaceStop(self, *_) -> None:
        if not self._backpack_connected:
            return

        self._stop_race_clock()

        msg = self._rhapi.db.option("_racestop_message")
        status_row, stop_col = self._get_pos("_status_pos", msg)

        def land(uid):
            with self._queue_lock:
                self.set_send_uid(uid)
                self.send_osd_text(status_row, stop_col, msg)
                self.send_display_osd()
                self.reset_send_uid()

        seats_finished = self._rhapi.race.seats_finished
        seat_pilots = self._rhapi.race.pilots

        active_unfinished_pids = [
            pid
            for seat, pid in seat_pilots.items()
            if pid
            and self._rhapi.db.pilot_attribute_value(pid, "elrs_active") == "1"
            and not seats_finished[seat]
        ]

        for uid in self._broadcast_uids(active_unfinished_pids):
            gevent.spawn(land, uid)

    def onRaceLapRecorded(self, args: dict) -> None:
        if not self._backpack_connected:
            return

        def update_pos(result):
            pilot_id = result["pilot_id"]

            if self._rhapi.db.option("_position_mode") != "1":
                message = f"LAP: {result['laps'] + 1}"
            else:
                message = f"POSN: {str(result['position']).upper()} | LAP: {result['laps'] + 1}"

            last = self._last_sent_osd.setdefault(pilot_id, {})
            if last.get("pos") == message:
                return
            last["pos"] = message

            currentlap_row, start_col = self._get_pos("_currentlap_pos", message)
            uid = self.get_pilot_uid(pilot_id)
            with self._queue_lock:
                self.set_send_uid(uid)
                self.send_clear_osd_row(currentlap_row)
                self.send_osd_text(currentlap_row, start_col, message)
                self.send_display_osd()
                self.reset_send_uid()

        def lap_results(result, gap_info):
            pilot_id = result["pilot_id"]
            message = self._format_time(gap_info.current.last_lap_time)
            lapresults_row, start_col = self._get_pos("_lapresults_pos", message)

            uid = self.get_pilot_uid(pilot_id)
            with self._queue_lock:
                self.set_send_uid(uid)
                self.send_osd_text(lapresults_row, start_col, message)
                self.send_display_osd()
                self.reset_send_uid()

            gevent.sleep(self._rhapi.db.option("_results_uptime") * 1e-1)

            with self._queue_lock:
                self.set_send_uid(uid)
                self.send_clear_osd_row(lapresults_row)
                self.send_display_osd()
                self.reset_send_uid()

        def show_totaltime(result, gap_info):
            if self._rhapi.db.option("_show_totaltime") != "1":
                return
            pilot_id = result["pilot_id"]
            message = f"TOTAL: {self._format_time(gap_info.current.total_time_laps)}"
            totaltime_row, start_col = self._get_pos("_totaltime_pos", message)
            uid = self.get_pilot_uid(pilot_id)
            with self._queue_lock:
                self.set_send_uid(uid)
                self.send_osd_text(totaltime_row, start_col, message)
                self.send_display_osd()
                self.reset_send_uid()

        def show_bestlap(result, gap_info):
            if self._rhapi.db.option("_show_bestlap") != "1":
                return
            pilot_id = result["pilot_id"]
            current_ms = gap_info.current.last_lap_time
            stored = self._best_laps.get(pilot_id)
            if stored is None or current_ms < stored:
                self._best_laps[pilot_id] = current_ms
            message = f"BEST: {self._format_time(self._best_laps[pilot_id])}"
            bestlap_row, start_col = self._get_pos("_bestlap_pos", message)
            uid = self.get_pilot_uid(pilot_id)
            with self._queue_lock:
                self.set_send_uid(uid)
                self.send_osd_text(bestlap_row, start_col, message)
                self.send_display_osd()
                self.reset_send_uid()

        seats_finished = self._rhapi.race.seats_finished
        pilots_completion = {
            pid: seats_finished[slot]
            for slot, pid in self._rhapi.race.pilots.items()
            if pid
        }

        results = args["results"]["by_race_time"]
        for result in results:
            if (
                self._rhapi.db.pilot_attribute_value(result["pilot_id"], "elrs_active") == "1"
            ):
                if not pilots_completion[result["pilot_id"]]:
                    gevent.spawn(update_pos, result)

                    if result["pilot_id"] == args["pilot_id"] and result["laps"] > 0:
                        gevent.spawn(lap_results, result, args["gap_info"])
                        gevent.spawn(show_bestlap, result, args["gap_info"])
                        gevent.spawn(show_totaltime, result, args["gap_info"])

    def onLapDelete(self, *_) -> None:
        if not self._backpack_connected:
            return

        if self._rhapi.db.option("_results_mode") != "1":
            return

        def delete(uid):
            with self._queue_lock:
                self.set_send_uid(uid)
                self.send_clear_osd()
                self.send_display_osd()
                self.reset_send_uid()

        for pid in self._active_pilot_ids():
            gevent.spawn(delete, self.get_pilot_uid(pid))

    def onRacePilotDone(self, args: dict) -> None:
        if not self._backpack_connected:
            return

        def done(result, win_condition):
            pilot_id = result["pilot_id"]
            done_msg = self._rhapi.db.option("_pilotdone_message")
            status_row, start_col = self._get_pos("_status_pos", done_msg)
            currentlap_row, _ = self._get_pos("_currentlap_pos")
            results_row1, _ = self._get_pos("_results_pos")
            results_row2 = results_row1 + 1

            show_results = self._rhapi.db.option("_results_mode") == "1"
            if show_results:
                placement_message = f"PLACEMENT: {result.get('position', '?')}"
                _, place_col = self._get_pos("_results_pos", placement_message)
                if win_condition == WinCondition.FASTEST_CONSECUTIVE:
                    win_message = f"FASTEST {result.get('consecutives_base','?')} CONSEC: {result.get('consecutives','?')}"
                elif win_condition == WinCondition.FASTEST_LAP:
                    win_message = f"FASTEST LAP: {result.get('fastest_lap','?')}"
                elif win_condition == WinCondition.FIRST_TO_LAP_X:
                    win_message = f"TOTAL TIME: {result.get('total_time','?')}"
                else:
                    win_message = f"LAPS: {result.get('laps','?')}"
                _, win_col = self._get_pos("_results_pos", win_message)

            uid = self.get_pilot_uid(pilot_id)
            with self._queue_lock:
                self.set_send_uid(uid)
                self.send_clear_osd_row(currentlap_row)
                self.send_clear_osd_row(status_row)
                self.send_osd_text(status_row, start_col, done_msg)
                if show_results:
                    self.send_osd_text(results_row1, place_col, placement_message)
                    self.send_osd_text(results_row2, win_col, win_message)
                self.send_display_osd()
                self.reset_send_uid()

            gevent.sleep(self._rhapi.db.option("_finish_uptime") * 1e-1)

            with self._queue_lock:
                self.set_send_uid(uid)
                self.send_clear_osd_row(status_row)
                if show_results:
                    self.send_clear_osd_row(results_row1)
                    self.send_clear_osd_row(results_row2)
                self.send_display_osd()
                self.reset_send_uid()

        results = args.get("results")
        if not results:
            logger.warning("onRacePilotDone: results not in args")
            return

        try:
            primary = results["meta"]["primary_leaderboard"]
            leaderboard = results[primary]
        except (KeyError, TypeError) as e:
            logger.warning("onRacePilotDone: failed to get leaderboard: %s", e)
            return

        pilot_id = args["pilot_id"]
        if self._rhapi.db.pilot_attribute_value(pilot_id, "elrs_active") != "1":
            return

        for result in leaderboard:
            if result["pilot_id"] == pilot_id:
                try:
                    win_condition = results["meta"]["win_condition"]
                except (KeyError, TypeError):
                    win_condition = None
                logger.info("onRacePilotDone: pilot %s pos=%s", pilot_id, result.get("position"))
                gevent.spawn(done, result, win_condition)
                break
        else:
            logger.warning("onRacePilotDone: pilot %s not found in leaderboard", pilot_id)

    def onLapsClear(self, *_) -> None:
        self._best_laps.clear()
        self._last_sent_osd.clear()

        if not self._backpack_connected:
            return

        self._stop_race_clock()

        # LAPS_CLEAR can fire after a new race is already staged (e.g. stop→discard→stage).
        # Skip the OSD wipe so we don't overwrite the ARM NOW message.
        if self._rhapi.race.status in (RaceStatus.STAGING, RaceStatus.RACING):
            return

        def clear(uid):
            with self._queue_lock:
                self.set_send_uid(uid)
                self.send_clear_osd()
                self.send_display_osd()
                self.reset_send_uid()

        for pid in self._active_pilot_ids():
            gevent.spawn(clear, self.get_pilot_uid(pid))

    def onSendMessage(self, args: dict | None = None) -> None:
        if not self._backpack_connected:
            return
        if args is None:
            return

        announce_msg = str.upper(args["message"])
        announce_row, announce_col = self._get_pos("_announcement_pos", announce_msg)

        def notify(uid):
            with self._queue_lock:
                self.set_send_uid(uid)
                self.send_osd_text(announce_row, announce_col, announce_msg)
                self.send_display_osd()
                self.reset_send_uid()

            gevent.sleep(self._rhapi.db.option("_announcement_uptime") * 1e-1)

            with self._queue_lock:
                self.set_send_uid(uid)
                self.send_clear_osd_row(announce_row)
                self.send_display_osd()
                self.reset_send_uid()

        for uid in self._broadcast_uids(self._active_pilot_ids()):
            gevent.spawn(notify, uid)
