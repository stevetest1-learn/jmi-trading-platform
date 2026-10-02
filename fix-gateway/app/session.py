import asyncio
import datetime as dt
from collections.abc import Awaitable, Callable

import simplefix

from app.config import settings

MessageHandler = Callable[["FixSession", simplefix.FixMessage], Awaitable[None]]


class FixSession:
    """Hand-rolled FIX session layer: Logon/Logout, sequence numbers,
    Heartbeat/TestRequest keepalive. simplefix only builds/parses messages
    -- everything session-level here is ours to get right.

    TEMPLATE LIMITATION: sequence-number gap detection is logged but not
    acted on (no ResendRequest handling). A production FIX engine needs
    that; this one doesn't pretend to be certified. See README.md.
    """

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, on_message: MessageHandler) -> None:
        self.reader = reader
        self.writer = writer
        self.on_message = on_message
        self.parser = simplefix.FixParser()

        self.sender_comp_id: str | None = None  # the counterparty's identity, learned at Logon
        self.our_comp_id: str = settings.sender_comp_id
        self.next_outgoing_seq = 1
        self.next_expected_incoming_seq = 1
        self.logged_on = False

        self._heartbeat_task: asyncio.Task | None = None
        self._last_received = dt.datetime.now(dt.UTC)

    def new_message(self, msg_type: str) -> simplefix.FixMessage:
        msg = simplefix.FixMessage()
        msg.append_pair(8, settings.fix_version, header=True)
        msg.append_pair(35, msg_type, header=True)
        msg.append_pair(49, self.our_comp_id, header=True)
        msg.append_pair(56, self.sender_comp_id or "UNKNOWN", header=True)
        msg.append_pair(34, self.next_outgoing_seq, header=True)
        msg.append_utc_timestamp(52, header=True)
        self.next_outgoing_seq += 1
        return msg

    async def send(self, msg: simplefix.FixMessage) -> None:
        self.writer.write(msg.encode())
        await self.writer.drain()

    async def run(self) -> None:
        try:
            await self._read_loop()
        finally:
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
            self.writer.close()

    async def _read_loop(self) -> None:
        while True:
            data = await self.reader.read(4096)
            if not data:
                break
            self.parser.append_buffer(data)
            while True:
                msg = self.parser.get_message()
                if msg is None:
                    break
                await self._handle(msg)

    async def _handle(self, msg: simplefix.FixMessage) -> None:
        self._last_received = dt.datetime.now(dt.UTC)
        incoming_seq = msg.get(34)
        if incoming_seq is not None:
            seq = int(incoming_seq)
            if seq != self.next_expected_incoming_seq:
                # TODO(template): a real session would send a ResendRequest
                # (35=2) here instead of just logging and pressing on.
                pass
            self.next_expected_incoming_seq = seq + 1

        msg_type = msg.get(35).decode()

        if msg_type == "A":  # Logon
            self.sender_comp_id = msg.get(49).decode()
            self.logged_on = True
            ack = self.new_message("A")
            ack.append_pair(98, 0)  # EncryptMethod: none
            ack.append_pair(108, settings.heartbeat_interval)
            await self.send(ack)
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            return

        if not self.logged_on:
            return  # ignore application messages before Logon

        if msg_type == "0":  # Heartbeat
            return
        if msg_type == "1":  # TestRequest -> answer with a Heartbeat echoing TestReqID
            hb = self.new_message("0")
            test_req_id = msg.get(112)
            if test_req_id:
                hb.append_pair(112, test_req_id)
            await self.send(hb)
            return
        if msg_type == "5":  # Logout
            await self.send(self.new_message("5"))
            self.logged_on = False
            return

        await self.on_message(self, msg)

    async def _heartbeat_loop(self) -> None:
        try:
            while self.logged_on:
                await asyncio.sleep(settings.heartbeat_interval)
                idle = (dt.datetime.now(dt.UTC) - self._last_received).total_seconds()
                if idle >= settings.heartbeat_interval:
                    await self.send(self.new_message("0"))
        except asyncio.CancelledError:
            pass
