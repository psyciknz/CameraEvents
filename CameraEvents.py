"""
Attach event listener to Dahua devices
Borrowed code from https://github.com/johnnyletrois/dahua-watch
And https://github.com/SaWey/home-assistant-dahua-event
Author: PsycikNZ
"""


REQUIREMENTS = ['pycurl>=7']

import threading
import requests
import re
import ConfigParser
import logging
import os
import socket
import pycurl
import json
import time
import paho.mqtt.client as paho   # pip install paho-mqtt
import base64

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


class DahuaDevice():
    #EVENT_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/eventManager.cgi?action=attach&channel=0&codes=%5B{events}%5D"
    EVENT_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/eventManager.cgi?action=attach&codes=%5B{events}%5D"
    CHANNEL_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/configManager.cgi?action=getConfig&name=ChannelTitle"
    SNAPSHOT_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/snapshot.cgi?channel={channel}"

    
    

    def __init__(self,  name, device_cfg, client, basetopic):
        self.channels = {}
        self.Name = name
        self.CurlObj = None
        self.Connected = None
        self.Reconnect = None
        self.MQTTConnected = None
        self.user = device_cfg.get("user")
        self.password = device_cfg.get("pass")
        self.auth = device_cfg.get("auth")
        self.mqtt = mqtt
        self.protocol  = device_cfg.get("protocol")
        self.host = device_cfg.get("host")
        self.port = device_cfg.get("port")
        self.alerts = True
        self.client = client
        self.basetopic = basetopic

        #generate the event url
        self.url = self.EVENT_TEMPLATE.format(
            protocol=self.protocol,
            host=self.host,
            port=self.port,
            events=device_cfg.get("events")
            
        )
        
        
        self.isNVR = False
        try:
            # Get NVR parm, to get channel names if NVR
            self.isNVR = device_cfg.get("isNVR")

            if self.isNVR:
                #generate the channel url
                self.channelurl  = self.CHANNEL_TEMPLATE.format(
                    protocol=device_cfg.get("protocol"),
                    host=device_cfg.get("host"),
                    port=device_cfg.get("port")
                )
                
                # get channel names here
                #table.ChannelTitle[0].Name=Garage
                response = requests.get(self.channelurl,auth=requests.auth.HTTPDigestAuth(self.user,self.password))
                for line in response.text.splitlines():
                    match = re.search('.\[(?P<index>[0-4])\]\..+\=(?P<channel>.+)',line)
                    if match:
                        _index = int(match.group("index"))
                        _channel = match.group("channel")
                        self.channels[_index] = _channel
            else:
                self.channels[0] = self.Name

        except Exception,e:
            _LOGGER.debug("Device " + name + " is not an NVR: " + str(e))
            _LOGGER.debug("Device " + name + " is not an NVR")

    def channelIsMine(self,channelname="",channelid=-1):
        for channel in self.channels:
            if channelname is not None and channelname == self.channels[channel]:
                return channel
            elif channelid > -1 and channel == channelid:
                return channel

        return -1
                

    

    def SnapshotImage(self, channel, channelName, message):
        imageurl  = self.SNAPSHOT_TEMPLATE.format(
                host=self.host,
                protocol=self.protocol,
                port  = self.port,
                channel=channel
            )
        image = None
        if self.auth == "digest":
            image = requests.get(imageurl, stream=True,auth=requests.auth.HTTPDigestAuth(self.user, self.password)).content
        else:
            image = requests.get(imageurl, stream=True,auth=requests.auth.HTTPBasicAuth(self.user, self.password)).content
        
        try:
            if image is not None and len(image) > 0:
                #construct image payload
                #{{ \"message\": \"Motion Detected: {0}\", \"imagebase64\": \"{1}\" }}"
                imgpayload = base64.encodestring(image)
                msgpayload = json.dumps({"message":message,"imagebase64":imgpayload})
                #msgpayload = "{{ \"message\": \"{0}\", \"imagebase64\": \"{1}\" }}".format(message,imgpayload)
                
                self.client.publish(self.basetopic +"/{0}/Image".format(channelName),msgpayload)
        except Exception,ex:
            _LOGGER.error("Error sending image: " + str(ex))
    

    # Connected to camera
    def OnConnect(self):
        _LOGGER.debug("[{0}] OnConnect()".format(self.Name))
        self.Connected = True

    #disconnected from camera
    def OnDisconnect(self, reason):
        _LOGGER.debug("[{0}] OnDisconnect({1})".format(self.Name, reason))
        self.Connected = False

    #on receive data from camera.
    def OnReceive(self, data):
        #self.client.loop_forever()
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

            index =  int( Alarm["index"]         )
            if index in self.channels:
                Alarm["channel"] = self.channels[index]
            else:
                Alarm["channel"] = self.Name + ":" + index

            #mqttc.connect(self.mqtt["IP"], int(self.mqtt["port"]), 60)
            if Alarm["Code"] == "VideoMotion":
                _LOGGER.info("Video Motion received: "+  Alarm["name"] + " Index: " + Alarm["channel"] + " Code: " + Alarm["Code"])
                if Alarm["action"] == "Start":
                    self.client.publish(self.basetopic +"/" + Alarm["Code"] + "/" + Alarm["channel"] ,"ON")
                    if self.alerts:
                        process = threading.Thread(target=self.SnapshotImage,args=(index,Alarm["channel"],"Motion Detected: {0}".format(Alarm["channel"])))
                        process.daemon = True                            # Daemonize thread
                        process.start()    
                else:
                    self.client.publish(self.basetopic +"/" + Alarm["Code"] + "/" + Alarm["channel"] ,"OFF")
            else:
                _LOGGER.info("dahua_event_received: "+  Alarm["name"] + " Index: " + Alarm["channel"] + " Code: " + Alarm["Code"])
                self.client.publish(self.basetopic +"/" + Alarm["index"] + "/" + Alarm["name"],Alarm["Code"])

            #mqttc.disconnect()
            #self.hass.bus.fire("dahua_event_received", Alarm)

    



class DahuaEventThread(threading.Thread):
    """Connects to device and subscribes to events"""
    Devices = []
    NumActivePlayers = 0

    CurlMultiObj = pycurl.CurlMulti()
    NumCurlObjs = 0
	

    def __init__(self,  mqtt, cameras):
        """Construct a thread listening for events."""

        self.basetopic = mqtt["basetopic"]

        self.client = paho.Client("CameraEvents", clean_session=True)
        self.client.on_connect = self.mqtt_on_connect
        #self.client.on_message = self.mqtt_on_message
        self.client.message_callback_add(self.basetopic +"/+/picture",self.mqtt_on_picture_message)
        self.client.message_callback_add(self.basetopic +"/+/alerts",self.mqtt_on_alert_message)
        
        self.client.will_set(self.basetopic +"/$online",False,0,True)
        

        self.alerts = True

        for device_cfg in cameras:

            device = DahuaDevice(device_cfg.get("name"), device_cfg, self.client,self.basetopic)
            self.Devices.append(device)

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
        
        self.client.connect(mqtt["IP"], int(mqtt["port"]), 60)
        self.client.loop_start()

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

    def mqtt_on_connect(self, client, userdata, flags, rc):
        if rc==0:
            _LOGGER.info("Connected to MQTT OK Returned code={0}".format(rc))
            self.client.publish(self.basetopic +"/$online",True,0,False)
            if self.alerts:
                state = "ON"
            else:
                state = "OFF"

            for device in self.Devices:
                device.alerts = state
                self.client.publish(self.basetopic +"" + device.Name + "/alerts/state",state)
            self.client.subscribe(self.basetopic +"/#")
            #self.client.subscribe("CameraEventsPy/alerts")
            
        else:
            _LOGGER.info("Camera : {0}: Bad mqtt connection Returned code={1}".format("self.Name",rc) )

    def mqtt_on_picture_message(self,client, userdata, msg):

        #if msg.payload.decode() == "Hello world!":
        _LOGGER.info("Picture Msg Received: Topic:{0} Payload:{1}".format(msg.topic,msg.payload))
        msgchannel = msg.topic.split("/")[1]
        for device in self.Devices:
            channel = device.channelIsMine(msgchannel)
            if channel > -1:
                _LOGGER.debug("Found Camera: {0} channel: {1}: Name:{2}".format(device.Name,channel,device.channels[channel]))
                device.SnapshotImage(channel,msgchannel,"Snap Shot Image")
                break
    
                    
    def mqtt_on_alert_message(self,client, userdata, msg):
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
                self.client.publish(self.basetopic +"/" + device.Name + "/alerts/state",msg.payload)

if __name__ == '__main__':

    cameras = []
    cp = ConfigParser.ConfigParser()
    cp.read("config.ini")
    camera_items = cp.items( "Cameras" )
    for key, camera_key in camera_items:
        #do something with path
        camera_cp = cp.items(camera_key)
        camera = {}
        #temp = cp.get(camera_key,"host")
        camera["host"] = cp.get(camera_key,'host')
        camera["protocol"] = cp.get(camera_key,'protocol')
        camera["isNVR"] = cp.get(camera_key,'isNVR')
        camera["name"] = cp.get(camera_key,'name')
        camera["port"] = cp.get(camera_key,'port')
        camera["user"] = cp.get(camera_key,'user')
        camera["pass"] = cp.get(camera_key,'pass')
        camera["auth"] = cp.get(camera_key,'auth')
        camera["events"] = cp.get(camera_key,'events')
        cameras.append(camera)

    mqtt = {}
    mqtt["IP"] = cp.get("MQTT Broker","IP")
    mqtt["port"] = cp.get("MQTT Broker","port")
    mqtt["basetopic"] = cp.get("MQTT Broker","BaseTopic")
    dahua_event = DahuaEventThread(mqtt,cameras)

    dahua_event.start()

    

    
