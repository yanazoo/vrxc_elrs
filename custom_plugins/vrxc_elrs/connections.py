    def connect(self, ip_addr: str) -> bool:
        """
        Establishes the socket connection

        :param ip_addr: The IP address to connect to
        """
        self._socket.settimeout(5)
        packet = MSPPacket()
        packet.set_function(MSPTypes.MSP_ELRS_GET_BACKPACK_VERSION)

        try:
            self._socket.connect((ip_addr, SOCKET_PORT))
            self._socket.sendall(packet.get_packet())
            data = self._socket.recv(128)
            for packet in MSPPacket.packets_from_bytes(data):
                if (
                    packet.type_ == MSPPacketType.RESPONSE
                    and packet.function == MSPTypes.MSP_ELRS_GET_BACKPACK_VERSION
                ):
                    self._connected = True
                    break
            else:
                self._socket.close()
                return False

        except OSError:
            self._socket.close()
            return False

        self._socket.settimeout(None)
        self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        # --- TCP keepalive: idle中の死んだ/ハーフオープン接続を検知する ---
        # これが無いと、バックパックが再起動/WiFi断でFINを送れずに消えた場合、
        # recv() が永久にブロックして _connected が True のまま残り、
        # 再接続ループが発火しない。5秒idleで開始→2秒間隔→3回失敗で切断扱い。
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        try:
            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 5)
            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 2)
            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
        except (AttributeError, OSError):
            pass  # プラットフォームによっては未対応
        # -----------------------------------------------------------------

        self._send_greenlet = gevent.spawn(self._send)
        self._recieve_greenlet = gevent.spawn(self._recieve)

        return True
