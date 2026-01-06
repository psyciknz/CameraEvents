# -*- coding: utf-8 -*-
#!/usr/bin/python3
"""
Attach event listener to Dahua devices
Borrowed code from https://github.com/johnnyletrois/dahua-watch
And https://github.com/SaWey/home-assistant-dahua-event
Author: PsycikNZ
"""


import threading
import datetime
import time
#import imageio
#from PIL import ImageFile
#from PIL import Image
#from io import BytesIO

#from slacker import Slacker
try:
    #python 3+
    from configparser import ConfigParser
except:
    # Python 2.7
    from ConfigParser import ConfigParser
import logging
import os
import socket
import pycurl
import json
import time
from paho.mqtt import client as mqtt_client   # pip install paho-mqtt
import base64
import DahuaDevice

version = "0.3.0"
#ImageFile.LOAD_TRUNCATED_IMAGES = True
#mqttc = paho.Client("CameraEvents-" + socket.gethostname(), clean_session=True)

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# add formatter to ch
ch.setFormatter(formatter)
_LOGGER.addHandler(ch)



def setup( config):
    """Set up Dahua event listener."""
    #config = config.get(DOMAIN)

    dahua_event = DahuaEventThread(
        None,
        None
    )

    def _start_dahua_event(_event):
        dahua_event.start()

    def _stop_dahua_event(_event):
        dahua_event.stopped.set()

    return True




class DahuaEventThread(threading.Thread):
    """Connects to device and subscribes to events"""
    Devices = []
    NumActivePlayers = 0

    CurlMultiObj = pycurl.CurlMulti()
    NumCurlObjs = 0
	

    def __init__(self,  mqtt_cfg, cameras):
        """Construct a thread listening for events."""

        self.basetopic = mqtt_cfg["basetopic"]
        self.homebridge = mqtt_cfg["homebridge"]

        self.client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION1,"CameraEvents-" + socket.gethostname(), clean_session=True)
        if not mqtt_cfg["user"] is None and not mqtt_cfg["user"] == '':
            self.client.username_pw_set(mqtt_cfg["user"], mqtt_cfg["password"])
        self.client.on_connect = self.mqtt_on_connect
        self.client.on_disconnect = self.mqtt_on_disconnect
        self.client.message_callback_add(self.basetopic +"/+/picture",self.mqtt_on_picture_message)
        self.client.message_callback_add(self.basetopic +"/+/alerts",self.mqtt_on_alert_message)
        
        self.client.will_set(self.basetopic +"/$online",False,qos=0,retain=True)

        for device_cfg in cameras:

            device = DahuaDevice.DahuaDevice(device_cfg.get("name"),_LOGGER, device_cfg, self.client,self.basetopic, self.homebridge, mqtt_cfg["mqttimages"])

            _LOGGER.info("Device %s created on Url %s.  Alert Status: %s" % (device.Name, device.host, device.alerts))

            self.Devices.append(device)

            #could look at this method: https://github.com/tchellomello/python-amcrest/blob/master/src/amcrest/event.py
            CurlObj = pycurl.Curl()
            device.CurlObj = CurlObj

            CurlObj.setopt(pycurl.URL, device.url)
            
            CurlObj.setopt(pycurl.CONNECTTIMEOUT, 30)
            CurlObj.setopt(pycurl.TCP_KEEPALIVE, 1)
            CurlObj.setopt(pycurl.TCP_KEEPIDLE, 30)
            CurlObj.setopt(pycurl.TCP_KEEPINTVL, 15)
            if device.auth == 'digest':
                CurlObj.setopt(pycurl.HTTPAUTH, pycurl.HTTPAUTH_DIGEST)
                CurlObj.setopt(pycurl.USERPWD, "%s:%s" % (device.user, device.password))
            else:
                CurlObj.setopt(pycurl.HTTPAUTH, pycurl.HTTPAUTH)
                CurlObj.setopt(pycurl.USERPWD, "%s:%s" % (device.user, device.password))
            CurlObj.setopt(pycurl.WRITEFUNCTION, device.OnReceive)

            self.CurlMultiObj.add_handle(CurlObj)
            self.NumCurlObjs += 1

            _LOGGER.debug("Added Dahua device at: %s", device.url)

        #connect to mqtt broker
        
        _LOGGER.debug("Connecting to MQTT Broker")
        self.client.connect(mqtt_cfg["IP"], int(mqtt_cfg["port"]), 60)
        
        _LOGGER.debug("Starting MQTT Loop")
        self.client.loop_start()

        threading.Thread.__init__(self)
        self.stopped = threading.Event() 


    def run(self):
        heartbeat = 0
        """Fetch events"""
        while 1:
            Ret, NumHandles = self.CurlMultiObj.perform()
            if Ret != pycurl.E_CALL_MULTI_PERFORM:
                break

        Ret = self.CurlMultiObj.select(1.0)
        while not self.stopped.is_set():
            # Sleeps to ease load on processor
            time.sleep(.05)
            heartbeat = heartbeat + 1
            if heartbeat % 1000 == 0:
                _LOGGER.debug("Heartbeat: " + str(datetime.datetime.now()))
                if not self.client.connected_flag:
                    self.client.reconnect()
                self.client.publish(self.basetopic +"/$heartbeat",str(datetime.datetime.now()))

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

    def mqtt_on_connect(self, client, userdata, flags, rc):
        if rc==0:
            _LOGGER.info("Connected to MQTT OK Returned code={0}".format(rc))
            self.client.connected_flag=True
            self.client.publish(self.basetopic +"/$online",True,qos=0,retain=True)
            self.client.publish(self.basetopic +"/$version",version,qos=0,retain=True)
            #if self.alerts:
            #    state = "ON"
            #else:
            #    state = "OFF"

            for device in self.Devices:
                if device.alerts:
                    state = "ON"
                else:
                    state = "OFF"
                self.client.publish(self.basetopic +"/" + device.Name + "/alerts/state",state,qos=0,retain=True)
            self.client.subscribe(self.basetopic +"/+/picture")
            self.client.subscribe(self.basetopic +"/+/alerts")

            #self.client.subscribe("CameraEventsPy/alerts")
            
        else:
            _LOGGER.info("Camera : {0}: Bad mqtt connection Returned code={1}".format("self.Name",rc) )
            self.client.connected_flag=False

    def mqtt_on_disconnect(self, client, userdata, rc):
        logging.info("disconnecting reason  "  +str(rc))
        self.client.connected_flag=False
        

    def mqtt_on_picture_message(self,client, userdata, msg):

        #if msg.payload.decode() == "Hello world!":
        _LOGGER.info("Picture Msg Received: Topic:{0} Payload:{1}".format(msg.topic,msg.payload))
        msgchannel = msg.topic.split("/")[1]
        for device in self.Devices:
            channel = device.channelIsMine(channelid=msgchannel)
            if channel > -1:
                _LOGGER.debug("Found Camera: {0} channel: {1}: Name:{2}".format(device.Name,channel,device.channels[channel]))
                if msg.payload is not None:
                    try:
                        datestring = ''
                        datestring = (msg.payload).decode()
                        d = datetime.datetime.strptime(datestring, "%Y-%m-%dT%H:%M:%S")
                        #def SearchImages(self,channel,starttime, endtime, events):
                        device.SearchImages(channel+device.snapshotoffset,d,d + datetime.timedelta(minutes=2),'',publishImages=device.publishImages,message="Snap Shot Image"  )
                    except Exception as searchI:
                        _LOGGER.warn("Error searching images: " + str(searchI))
                        d = None
                        pass
                else:
                    device.SnapshotImage(channel+device.snapshotoffset,msgchannel,"Snap Shot Image")
                break
    
                    
    def mqtt_on_alert_message(self,client, userdata, msg):
        if msg.payload.decode("utf-8").lower() == 'on' or msg.payload.decode("utf-8").lower() == 'true':
            newState = True
        else:
            newState = False

        deviceName = msg.topic.split('/')[1]
        _LOGGER.info("Camera: {0}: Msg Received: Topic:{1} Payload:{2}".format(deviceName,msg.topic,msg.payload))
        for device in self.Devices:
            #channel = self.Devices[device].channelIsMine("Garage")
            if device.Name == deviceName:
                device.alerts = newState
                _LOGGER.info("Turning Alerts {0}".format( newState))
                self.client.publish(self.basetopic +"/" + device.Name + "/alerts/state",msg.payload,qos=0,retain=True)

    def mqtt_on_cross_message(self,client, userdata, msg):
        if msg.payload == 'ON':
            newState = True
        else:
            newState = False

        deviceName = msg.topic.split('/')[1]
        _LOGGER.info("Camera: {0}: Msg Received: Topic:{1} Payload:{2}".format(deviceName,msg.topic,msg.payload))
        for device in self.Devices:
            #channel = self.Devices[device].channelIsMine("Garage")
            if device.Name == deviceName:
                device.alerts = newState
                _LOGGER.info("Turning Alerts {0}".format( newState))
                self.client.publish(self.basetopic +"/" + device.Name + "/alerts/state",msg.payload,qos=0,retain=True)

if __name__ == '__main__':

    cameras = []
    cp = ConfigParser()
    _LOGGER.info("Loading config")
    filename = {"config.ini","conf/config.ini"}
    dataset = cp.read(filename)

    try:
        if len(dataset) != 1:
            raise ValueError( "Failed to open/find all files")
        camera_items = cp.items( "Cameras" )
        for key, camera_key in camera_items:
            #do something with path
            camera_cp = cp.items(camera_key)
            camera = {}
            #temp = cp.get(camera_key,"host")
            camera["host"] = cp.get(camera_key,'host')
            camera["protocol"] = cp.get(camera_key,'protocol')
            camera["isNVR"] = cp.getboolean(camera_key,'isNVR',fallback=False)
            camera["name"] = cp.get(camera_key,'name')
            camera["port"] = cp.getint(camera_key,'port')
            camera["user"] = cp.get(camera_key,'user')
            camera["pass"] = cp.get(camera_key,'pass')
            camera["auth"] = cp.get(camera_key,'auth')
            camera["events"] = cp.get(camera_key,'events')
            camera["alerts"] = cp.getboolean(camera_key,"alerts",fallback=True)
            channels = {}
            if cp.has_option(camera_key,'channels'):
                try:
                    channellist = cp.get(camera_key,'channels').split('|')
                    for channel in channellist:
                        channelIndex = channel.split(':')[0]
                        channelName = channel.split(':')[1]
                        channels[int(channelIndex)] = channelName
                        
                except Exception as e:
                    _LOGGER.warning("Warning, No channel list in config (may be obtained from NVR):" + str(e))
                    channels = {}
                    
            camera["channels"] = channels
            
            # added new snapshot offset section.
            if cp.has_option(camera_key,'snapshotoffset'):
                camera["snapshotoffset"] = cp.getint(camera_key,'snapshotoffset')
            else:
                camera["snapshotoffset"] = 0
            
            # added new playback offset section.  If -1 turned off, else will start playback from this offset in seconds
            if cp.has_option(camera_key,'playbackoffset'):
                camera["playbackoffset"] = cp.getint(camera_key,'playbackoffset')
            else:
                camera["playbackoffset"] = -1
            # sets playback length.
            if cp.has_option(camera_key,'playbacklength') and camera["playbackoffset"] > -1:
                camera["playbacklength"] = cp.getint(camera_key,'playbacklength')
            else:
                camera["playbacklength"] = 10

            token = ""
            if cp.has_option("Slack","token"):
                token = cp.get("Slack","token")
                camera["token"] = token

            cameras.append(camera)

        mqtt_cfg = {}
        mqtt_cfg["IP"] = cp.get("MQTT Broker","IP")
        mqtt_cfg["port"] = cp.get("MQTT Broker","port")
        mqtt_cfg["basetopic"] = cp.get("MQTT Broker","BaseTopic")
        mqtt_cfg["user"] = cp.get("MQTT Broker","user",fallback=None)
        mqtt_cfg["password"] = cp.get("MQTT Broker","password",fallback=None)
        mqtt_cfg["homebridge"] = cp.getboolean("MQTT Broker","HomebridgeEvents",fallback=False)
        mqtt_cfg["mqttimages"] = cp.getboolean("MQTT Broker","PostImagesToMQTT",fallback=True)
        dahua_event = DahuaEventThread(mqtt_cfg,cameras)

        dahua_event.start()
    except Exception as ex:
        _LOGGER.error("Error starting:" + str(ex))

    

    

