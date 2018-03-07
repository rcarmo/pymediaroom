import logging

import socket
import socket
import struct
import asyncio
from async_timeout import timeout
from enum import Enum

from .commands import Commands
from .notify import * 
from .error import PyMediaroomError

_LOGGER = logging.getLogger(__name__)

GET_STATE_TIMEOUT = 10 
OPEN_CONTROL_TIMEOUT = 5

class State(Enum):
    OFF = 0
    PLAYING = 1
    STANDBY = 2
    UNKNOWN = -1 

class Remote():
    """This class represents a MediaRoom Set-up-Box Remote Control."""

    def __init__(self, ip, port=8082, timeout=60, loop=None):
        self.timeout = timeout
        self.stb_ip = ip
        self.stb_port = port
        self.loop = loop
        self.mr_protocol = None
        self.stb_recv = self.stb_send = None

    def __repr__(self):
        return self.stb_ip

    async def open_control(self):
        try:
            async with timeout(OPEN_CONTROL_TIMEOUT, loop=self.loop):
                self.mr_protocol = await installMediaroomProtocol(box_ip=self.stb_ip, loop=self.loop)
                _LOGGER.info("Connecting to %s:%s" % (self.stb_ip, self.stb_port))
                self.stb_recv, self.stb_send = await asyncio.open_connection(self.stb_ip, self.stb_port, loop=self.loop) 
                await self.stb_recv.read(6)
                _LOGGER.info("Connected to %s:%s" % (self.stb_ip, self.stb_port))
        except asyncio.TimeoutError as e:
            _LOGGER.error("Timeout connecting to %s", self.stb_ip)

    async def send_cmd(self, cmd):
        _LOGGER.debug("Send cmd = %s", cmd)
        if self.stb_recv == self.stb_send:
            await self.open_control()

        if cmd not in Commands and cmd not in range(0,999):
            _LOGGER.error("Unknown command")
            raise PyMediaroomError("Unknown commands")

        keys = []
        if cmd in range(0,999):
            for c in str(cmd):
                keys.append(Commands["Number"+str(c)])
        else:
            keys = [Commands[cmd]]

        for key in keys:
            _LOGGER.debug("{} key={}".format(cmd, key))
            self.stb_send.write("key={}\n".format(key).encode('UTF-8'))
            _ = await self.stb_recv.read(3)
            await asyncio.sleep(0.300)

    async def turn_on(self):
        """Turn off media player."""
        standby = await self.get_standby()
        _LOGGER.debug("turn_on %s", standby)
        standby = await self.get_standby()
        if standby:
            await self.send_cmd('Power')

    async def turn_off(self):
        """Turn off media player."""
        playing = await self.get_playing()
        _LOGGER.debug("turn_off %s", playing)
        if playing:
            await self.send_cmd('Power')

    def __del__(self):
        if self.stb_send:
            self.stb_send.close()
            self.mr_protocol.close()
            _LOGGER.info("Disconnected")

    async def get_state(self):
        if not self.mr_protocol:
            await self.open_control()
        try:        
            async with timeout(GET_STATE_TIMEOUT, loop=self.loop):
                notify = await self.mr_protocol.responses.get()
                
                if notify.tune:
                    return State.PLAYING
                else:
                    return State.STANDBY
        except asyncio.TimeoutError as e:
            return State.OFF
        
    async def get_standby(self):
        state = await self.get_state()
        return state == STANDBY 

    async def get_playing(self):
        state = await self.get_state()
        return state == PLAYING

    def update(self):
        if self.s == None:
            self.s = Remote.create_socket(timeout=self.timeout)

        src = None
        try:
            while src != self.stb_ip:
                data, src = self.get_notify(self.s)

            for line in data.split('\n'):
                _LOGGER.debug(line)

            if '<tune' in data:
                self._standby = False
            else:
                self._standby = True

        except socket.timeout:
            _LOGGER.warning("Couldn't get NOTIFY message")
            self._standby = None

async def discover(ignore_list = [], max_wait=30, loop=None):
    stbs = []
    try:
        async with timeout(max_wait, loop=loop):
            mr_protocol = await installMediaroomProtocol() 
            while True:
                notify = await mr_protocol.responses.get()
                stbs.append(notify.ip_address)
    except asyncio.TimeoutError as e:
        mr_protocol.close()
        _LOGGER.debug("discover() timeout!")

    return set([stb for stb in stbs if stb not in ignore_list])