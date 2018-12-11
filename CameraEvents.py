"""
Attach event listener to Dahua devices
Borrowed code from https://github.com/johnnyletrois/dahua-watch
And https://github.com/SaWey/home-assistant-dahua-event
Author: PsycikNZ
"""


REQUIREMENTS = ['pycurl>=7']

import threading
import requests
import logging
import os
import socket
import pycurl
import time
import paho.mqtt.client as paho   # pip install paho-mqtt

mqttc = paho.Client("CameraEvents", clean_session=True)

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# add formatter to ch
ch.setFormatter(formatter)
_LOGGER.addHandler(ch)

#URL_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/eventManager.cgi?action=attach&channel=0&codes=%5B{events}%5D"
#CHANNEL_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/configManager.cgi?action=getConfig&name=ChannelTitle"

#CONFIG_SCHEMA = vol.Schema({
#    DOMAIN:
#        vol.All(cv.ensure_list, [vol.Schema({
#            vol.Optional(CONF_NAME): cv.string,
#            vol.Optional("protocol", default="http"): cv.string,
#            vol.Optional("user", default="admin"): cv.string,
#            vol.Optional("password", default="admin"): cv.string,
#            vol.Required("host"): cv.string,
#            vol.Optional("port", default=80): int,
#            vol.Optional("events", default="VideoMotion,CrossLineDetection,AlarmLocal,VideoLoss,VideoBlind"): cv.string,
#            vol.Optional("channels"): vol.All(cv.ensure_list,[vol.Schema({
#                    vol.Required("number"): int,
#                    vol.Required(CONF_NAME): cv.string,
#            })])
#        })])
#}, extra=vol.ALLOW_EXTRA)


def setup( config):
    """Set up Dahua event listener."""
    #config = config.get(DOMAIN)

    dahua_event = DahuaEventThread(
        config
    )

    def _start_dahua_event(_event):
        dahua_event.start()

    def _stop_dahua_event(_event):
        dahua_event.stopped.set()

    return True

#class config():
#    def __init__(self):
#        self.Name = "NVR"
#        self.Master = True
#        self.Protocol = "http"
#        self.Host = "192.168.10.64"
#        self.Port = "80"
#        self.Events = "VideoMotion,CrossLineDetection,AlarmLocal,VideoLoss,VideoBlind"
#        self.User = "Remote"
#        self.Password = "Dragon25"

    
        


class DahuaDevice():
    URL_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/eventManager.cgi?action=attach&channel=0&codes=%5B{events}%5D"
    CHANNEL_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/configManager.cgi?action=getConfig&name=ChannelTitle"

    def __init__(self, name, device_cfg):
        self.Name = name
        self.CurlObj = None
        self.Connected = None
        self.Reconnect = None
        self.user = device_cfg.get("user")
        self.password = device_cfg.get("pass")

        self.url = self.URL_TEMPLATE.format(
            protocol=device_cfg.get("protocol"),
            host=device_cfg.get("host"),
            port=device_cfg.get("port"),
            events=device_cfg.get("events")
        )
        self.isNVR = False
        try:
            self.isNVR = device_cfg.get("isNVR")

            if self.isNVR:
                self.channelurl  = self.CHANNEL_TEMPLATE.format(
                    protocol=device_cfg.get("protocol"),
                    host=device_cfg.get("host"),
                    port=device_cfg.get("port")
                )
                # get channel names here
                
                response = requests.get(self.channelurl,auth=requests.auth.HTTPDigestAuth(self.user,self.password))
                print response.text
                #table.ChannelTitle[0].Name=Garage
                #table.ChannelTitle[1].Name=Backyard
                #table.ChannelTitle[2].Name=Frontdoor
                #table.ChannelTitle[3].Name=Backdoor

        except Exception,e:
            _LOGGER.debug("Device " + name + " is not an NVR: " + str(e))
            _LOGGER.debug("Device " + name + " is not an NVR")
        
    


    def OnConnect(self):
        _LOGGER.debug("[{0}] OnConnect()".format(self.Name))
        self.Connected = True

    def OnDisconnect(self, reason):
        _LOGGER.debug("[{0}] OnDisconnect({1})".format(self.Name, reason))
        self.Connected = False


    def OnReceive(self, data):
        Data = data.decode("utf-8", errors="ignore")
        _LOGGER.debug("[{0}]: {1}".format(self.Name, Data))

        for Line in Data.split("\r\n"):
            if Line == "HTTP/1.1 200 OK":
                self.OnConnect()

            if not Line.startswith("Code="):
                continue

            Alarm = dict()
            Alarm["name"] = self.Name
            for KeyValue in Line.split(';'):
                Key, Value = KeyValue.split('=')
                Alarm[Key] = Value

            if Alarm["index"] in self.Channels:
                Alarm["channel"] = self.Channels[Alarm["index"]]

            _LOGGER.info("dahua_event_received: "+  Alarm["name"] + " Index: " + Alarm["index"])
            mqttc.connect("mqtt.andc.nz", int(1883), 60)
            mqttc.publish("CameraEventsPy/" + Alarm["index"] + "/" + Alarm["name"])
            mqttc.disconnect()
            #self.hass.bus.fire("dahua_event_received", Alarm)

class DahuaEventThread(threading.Thread):
    """Connects to device and subscribes to events"""
    Devices = []
    NumActivePlayers = 0

    CurlMultiObj = pycurl.CurlMulti()
    NumCurlObjs = 0
	

    def __init__(self,  cameras):
        """Construct a thread listening for events."""

        for device_cfg in cameras:

            device = DahuaDevice(device_cfg.get("name"), device_cfg)
            self.Devices.append(device)

            CurlObj = pycurl.Curl()
            device.CurlObj = CurlObj

            CurlObj.setopt(pycurl.URL, device.url)
            CurlObj.setopt(pycurl.CONNECTTIMEOUT, 30)
            CurlObj.setopt(pycurl.TCP_KEEPALIVE, 1)
            CurlObj.setopt(pycurl.TCP_KEEPIDLE, 30)
            CurlObj.setopt(pycurl.TCP_KEEPINTVL, 15)
            CurlObj.setopt(pycurl.HTTPAUTH, pycurl.HTTPAUTH_DIGEST)
            CurlObj.setopt(pycurl.USERPWD, "%s:%s" % (device.user, device.password))
            CurlObj.setopt(pycurl.WRITEFUNCTION, device.OnReceive)

            self.CurlMultiObj.add_handle(CurlObj)
            self.NumCurlObjs += 1

            _LOGGER.debug("Added Dahua device at: %s", device.url)

        threading.Thread.__init__(self)
        self.stopped = threading.Event() 


    def run(self):
        """Fetch events"""
        while 1:
            Ret, NumHandles = self.CurlMultiObj.perform()
            if Ret != pycurl.E_CALL_MULTI_PERFORM:
                break

        Ret = self.CurlMultiObj.select(1.0)
        while not self.stopped.isSet():
            # Sleeps to ease load on processor
            time.sleep(.05)
            Ret, NumHandles = self.CurlMultiObj.perform()

            if NumHandles != self.NumCurlObjs:
                _, Success, Error = self.CurlMultiObj.info_read()

                for CurlObj in Success:
                    DahuaDevice = next(iter(filter(lambda x: x.CurlObj == CurlObj, self.Devices)), None)
                    if DahuaDevice.Reconnect:
                        _LOGGER.debug("Dahua Reconnect: %s", DahuaDevice.Name)
                        continue

                    DahuaDevice.OnDisconnect("Success")
                    DahuaDevice.Reconnect = time.time() + 5

                for CurlObj, ErrorNo, ErrorStr in Error:
                    DahuaDevice = next(iter(filter(lambda x: x.CurlObj == CurlObj, self.Devices)), None)
                    if DahuaDevice.Reconnect:
                        continue

                    DahuaDevice.OnDisconnect("{0} ({1})".format(ErrorStr, ErrorNo))
                    DahuaDevice.Reconnect = time.time() + 5

                for DahuaDevice in self.Devices:
                    if DahuaDevice.Reconnect and DahuaDevice.Reconnect < time.time():
                        self.CurlMultiObj.remove_handle(DahuaDevice.CurlObj)
                        self.CurlMultiObj.add_handle(DahuaDevice.CurlObj)
                        DahuaDevice.Reconnect = None
            #if Ret != pycurl.E_CALL_MULTI_PERFORM: break

if __name__ == '__main__':
    #_config = config()
    CAMERAS = [
        {
            "host": "192.168.10.64",
            "protocol": "http",
            "name" : "NVR",
            "isNVR": True,
            "port": 80,
            "user": "Remote",
            "pass": "Dragon25",
            "events": "VideoMotion,CrossLineDetection,AlarmLocal,VideoLoss,VideoBlind"
        }
    ]
        #,
        #{
        #    "host": "192.168.10.65",
        #    "protocol": "http",
        #    "name": "Roof",
        #    "port": 80,
        #    "user": "USER",
        #    "pass": "PASSWORD",
        #    "events": "CrossLineDetection"
        #}
    #]
    #_config.readConfig(CAMERAS)

    dahua_event = DahuaEventThread(CAMERAS)

    dahua_event.start()

    

    
