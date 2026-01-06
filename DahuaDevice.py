import threading
import requests
import datetime
import re
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
#import paho.mqtt.client as paho   # pip install paho-mqtt
import base64

class DahuaDevice():
    #EVENT_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/eventManager.cgi?action=attach&channel=0&codes=%5B{events}%5D"
    EVENT_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/eventManager.cgi?action=attach&codes=%5B{events}%5D"
    CHANNEL_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/configManager.cgi?action=getConfig&name=ChannelTitle"
    SNAPSHOT_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/snapshot.cgi?channel={channel}"
    #SNAPSHOT_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/snapshot.cgi?chn={channel}"
    SNAPSHOT_EVENT = "{protocol}://{host}:{port}/cgi-bin/eventManager.cgi?action=attachFileProc&Flags[0]=Event&Events=%5B{events}%5D"
     #cgi-bin/snapManager.cgi?action=attachFileProc&Flags[0]=Event&Events=[VideoMotion%2CVideoLoss]    
    PLAYBACK_TEMPLATE = "rtsp://{host}:{port}/cgi-bin/playback.cgi?channel={channel}&starttime={starttime}&endtime={endtime}"

    
    

    def __init__(self,  name, logger, device_cfg, client, basetopic, homebridge=None, publishImages=False):
        if device_cfg["channels"]:
            self.channels = device_cfg["channels"]
        else:
            self.channels = {}
        self.Name = name
        self.logger = logger
        self.CurlObj = None
        self.Connected = None
        self.Reconnect = None
        self.MQTTConnected = None
        self.user = device_cfg.get("user")
        self.password = device_cfg.get("pass")
        self.auth = device_cfg.get("auth")
        self.mqtt = device_cfg.get("mqtt")
        self.protocol  = device_cfg.get("protocol")
        self.host = device_cfg.get("host")
        self.port = device_cfg.get("port")
        self.alerts = device_cfg.get("alerts")
        self.token = device_cfg.get("token")
        self.client = client
        self.basetopic = basetopic
        self.homebridge = homebridge
        self.snapshotoffset = device_cfg.get("snapshotoffset")
        self.playbackoffset = device_cfg.get("playbackoffset")
        self.playbacklength = device_cfg.get("playbacklength")
        self.publishImages = publishImages

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
                self.snapshotevents = self.SNAPSHOT_EVENT.format(
                    protocol=self.protocol,
                    host=self.host,
                    port=self.port,
                    events=device_cfg.get("events")    
                )
                
                #RPCConnect(1)

                # get channel names here
                #table.ChannelTitle[0].Name=Garage
                self.logger.debug("Device " + name + " Getting channel ids: " + self.channelurl)
                response = requests.get(self.channelurl,auth=requests.auth.HTTPDigestAuth(self.user,self.password))
                for line in response.text.splitlines():
                    match = re.search(r'.\[(?P<index>\d+?)\]\..+\=(?P<channel>.+)',line)
                    if match:
                        _index = int(match.group("index"))
                        _channel = match.group("channel")
                        self.channels[_index] = _channel
                        self.logger.debug("Device " + name + " Adding channel: " + str(_index) + " Name: " + _channel)
            else:
                self.channels[0] = self.Name

            self.logger.info("Created Data Device: " + name)

        except Exception as e:
            self.logger.debug("Device " + name + " is not an NVR: " + str(e))
            self.logger.debug("Device " + name + " is not an NVR")


    def channelIsMine(self,channelname="",channelid=-1):
        channelidInt = -1
        if isinstance(channelid,str):
            channelidInt = int(channelid)
        else:
            channelidInt = channelid
        for channel in self.channels:
            if channelname is not None and channelname == self.channels[channel]:
                return channel
            elif channelidInt > -1 and channel == channelidInt:
                return channel

        return -1

 
    def SnapshotImage(self, channel, channelName, message,publishImages=False):
        """Takes a snap shot image for the specified channel
        channel (index number starts at 1)
        channelName if known for messaging
        message message to post
        nopublish True/False for posting to MQTT"""
        imageurl  = self.SNAPSHOT_TEMPLATE.format(
                host=self.host,
                protocol=self.protocol,
                port  = self.port,
                channel=channel
            )
        image = None
        self.logger.info("Snapshot Url: " + imageurl)
        try:
            if self.auth == "digest":
                image = requests.get(imageurl, stream=True,auth=requests.auth.HTTPDigestAuth(self.user, self.password)).content
            else:
                image = requests.get(imageurl, stream=True,auth=requests.auth.HTTPBasicAuth(self.user, self.password)).content
        
            imagepayload = ""
            if image is not None and len(image) > 0:
                #fp = open("image.jpg", "wb")
                #fp.write(image) #r.text is the binary data for the PNG returned by that php script
                #fp.close()
                #construct image payload
                #{{ \"message\": \"Motion Detected: {0}\", \"imagebase64\": \"{1}\" }}"
                imagepayload = (base64.encodebytes(image)).decode("utf-8")
                if publishImages:
                    msgpayload = json.dumps({"message":message,"imagebase64":imagepayload})
                else:
                    msgpayload = json.dumps({"message":message,"imagurl":imageurl})
                #msgpayload = "{{ \"message\": \"{0}\", \"imagebase64\": \"{1}\" }}".format(message,imgpayload)
                
                self.client.publish(self.basetopic +"/{0}/Image".format(channelName),msgpayload)

        except Exception as ex:
            self.logger.error("Error sending image: " + str(ex))
            try:
                
                with open("default.png", 'rb') as thefile:
                    imagepayload = thefile.read().encode("base64")
                msgpayload = json.dumps({"message":"ERR:" + message, "imagebase64": imagepayload})
            except:
                pass
        
       
        return image

    
    def SearchImages(self,channel,starttime, endtime, events,publishImages=False, message='',delay=0):
        """Searches for images for the channel
        channel is a numerical channel index (starts at 1)
        starttime is the start search time
        endtime is the end search time (or now)
        events is a list of event types"""
        #Create Finder
        #http://<ip>/cgi-bin/mediaFileFind.cgi?action=factory.create 
        MEDIA_FINDER="{protocol}://{host}:{port}/cgi-bin/mediaFileFind.cgi?action=factory.create"
        MEDIA_START="{protocol}://{host}:{port}/cgi-bin/mediaFileFind.cgi?action=findFile&object={object}&condition.Channel={channel}" + \
            "&condition.StartTime={starttime}&condition.EndTime={endtime}&condition.Types[0]=jpg&condition.Flag[0]=Event" \
            "&condition.Events[0]={events}"
        MEDIA_START="{protocol}://{host}:{port}/cgi-bin/mediaFileFind.cgi?action=findFile&object={object}" + \
            "&condition.Channel={channel}" + \
            "&condition.StartTime={starttime}&condition.EndTime={endtime}" + \
            "&condition.Flags%5b0%5d=Event&condition.Types%5b0%5d=jpg"
            #&condition.Types=%5b0%5d=jpg" 
            #&condition.Types[0]=jpg
            #&condition.Flags[0]=Event&condition.Types[0]=jpg
            #&condition.Flags%5b0%5d=Event&condition.Types%5b0%5d=jpg
            #%5B{events}%5D
        #MEDIA_START="{protocol}://{host}:{port}/cgi-bin/mediaFileFind.cgi?action=findFile&object={object}" + \
        #    "&condition.Channel={channel}" + \
        #    "&condition.StartTime=2019-12-05%2006:20:48&condition.EndTime=2019-12-05%2009:28:48&condition.Flags%5b0%5d=Event&condition.Types%5b0%5d=jpg"

        #Start Find
        #http://<ip>/cgi-bin/mediaFileFind.cgi?action=findFile&object=<objectId>&condition.Channel=<channel>&condition.StartTime=
        #  <start>&condition.EndTime=<end>&condition.Dirs[0]=<dir>&condition.Types[0]=<type>&condition.Flag[0]=<flag>&condition.E vents[0]=<event>
        #Start to find file wth the above condition. 
        # If start successfully, return true, else return false. 
        #  object : The object Id is got from interface in 10.1.1 
        #  Create condition.Channel: in which channel you want to find the file . 
        # condition.StartTime/condition.EndTime: the start/end time when recording. 
        # condition.Dirs: in which directories you want to find the file. It is an array. 
        #   The index starts from 0. The range of dir is {“/mnt/dvr/sda0”, “/mnt/dvr/sda1”}. 
        #   This condition can be omitted. If omitted, find files in all the directories. 
        # condition.Types: which types of the file you want to find. It is an array. 
        #   The index starts from 0. The range of type is {“dav”,“jpg”, “mp4”}. If omitted, 
        #   find files with all the types. 
        # condition.Flags: which flags of the file you want to find. It is an array. 
        #   The index starts from 0. The range of flag is {“Timing”, “Manual”, “Marker”, “Event”, “Mosaic”, “Cutout”}. 
        #   If omitted, find files with all the flags. 
        # condition.Event: by which event the record file is triggered. It is an array. 
        #   The index starts from 0. The range of event is {“AlarmLocal”, “VideoMotion”, “VideoLoss”, “VideoBlind”, “Traffic*”}. 
        #   This condition can be omitted. If omitted, find files of all the events. 
        #   Example: Find file in channel 1, in directory “/mnt/dvr/sda0",event type is "AlarmLocal" or 
        #   "VideoMotion", file type is “dav”, and time between 2011-1-1 12:00:00 and 2011-1-10 12:00:00 , 
        #   URL is: http://<ip>/cgi-bin/mediaFileFind.cgi?action=findFile&object=08137&condition.Channel=1&conditon.Dir[0]=”/mnt/dvr/sda0”& conditon.Event[0]=AlarmLocal&conditon.Event[1]=VideoMotion&condition.StartTime=2011-1-1%2012:00:00&condition.EndTi me=2011-1-10%2012:00:00

        #Find next File
        # http://<ip>/cgi-bin/mediaFileFind.cgi?action=findNextFile&object=<objectId>&count=<fileCount> Comment 
        MEDIA_NEXT="{protocol}://{host}:{port}/cgi-bin/mediaFileFind.cgi?action=findNextFile&object={object}&count=50"
        
        MEDIA_LOADFILE="{protocol}://{host}:{port}/cgi-bin/RPC_Loadfile{file}"

        #Close Finder
        #http://<ip>/cgi-bin/mediaFileFind.cgi?action=close&object=<objectId> 
        MEDIA_CLOSE="{protocol}://{host}:{port}/cgi-bin/mediaFileFind.cgi?action=close&object={object}"

        if delay > 0:
            time.sleep(delay)

        finderurl  = MEDIA_FINDER.format(
                host=self.host,
                protocol=self.protocol,
                port  = self.port
            )
        objectId = ""
        cookies = {}
        s = requests.Session()
        if self.auth == "digest":
            auth = requests.auth.HTTPDigestAuth(self.user, self.password)
        else:
            auth = auth=requests.auth.HTTPBasicAuth(self.user, self.password)

        channelName = "Unknown"
        try:
            channelName = self.channels[channel-1]
        except:
            pass

        self.logger.info("SearchImages Finder Url: " + finderurl)
        try:
            #first request needs authentication
            if self.auth == "digest":
                result = s.get(finderurl, stream=True,auth=auth,cookies=cookies).content
            else:
                result = s.get(finderurl, stream=True,auth=auth,cookies=cookies).content

            #result = b'result=3021795080\r\n' 
            # Get the object id of the finder request, needed for subsequent searches
            objectId = self.ConvertLinesToDict(result.decode())["result"]
            self.logger.info("SearchImages:  Opened a search object: " + objectId)
            # perform a search.  Startime and endtime in the following format: 2011-1-1%2012:00:00
            finderurl = MEDIA_START.format(host=self.host,protocol=self.protocol,port=self.port,
                object=objectId,channel=channel,
                starttime=starttime.strftime("%Y-%m-%d%%20%H:%M:%S"),
                endtime=endtime.strftime("%Y-%m-%d%%20%H:%M:%S")
                ,events="*")
            #finderurl = finderurl + requests.utils.quote("&condition.Types[0]=jpg")
            self.logger.info("SearchImages:  FinderURL: " + finderurl)
            result = s.get(finderurl, stream=True,auth=auth,cookies=cookies)
            if result.status_code == 200:
                finderurl = MEDIA_NEXT.format(host=self.host,protocol=self.protocol,port=self.port,object=objectId)
                result = s.get(finderurl,auth=auth,cookies=cookies)
                mediaItem = {}
                if result.status_code == 200:
                    #start downloading the images.
                    mediaItem = self.ConvertLinesToDict(result.content.decode())
                    finderurl = MEDIA_CLOSE.format(host=self.host,protocol=self.protocol,port=self.port,
                        object=objectId)
                    
                    # Close the media find object
                    result = s.get(finderurl,auth=auth,cookies=cookies).content
                    #images = []
                    #imagesize = 0
                    #expectedsize = 0
                    image = None
                    self.logger.info("SearchImages: Found " + str(len(mediaItem)) + " images to process")
                    
                    filepath = ""

                    if type(mediaItem) is list:
                        for item in mediaItem:
                            filepath = item['FilePath']
                            self.logger.debug("SearchImages: Creating url for image: " + filepath)
                            loadurl = MEDIA_LOADFILE.format(host=self.host,protocol=self.protocol,port=self.port,file=filepath)
                            self.logger.debug("SearchImages: LoadUrl: " + loadurl)
                            result = s.get(loadurl,auth=auth,cookies=cookies,stream=True)
                            #result = s.get(loadurl,auth=auth,cookies=cookies)
                            image = self.ProcessSearchImage(item,result)
                            if image is not None:
                                break
                    else:
                        filepath = mediaItem['FilePath']
                        self.logger.debug("SearchImages: Creating url for image: " + filepath)
                        loadurl = MEDIA_LOADFILE.format(host=self.host,protocol=self.protocol,port=self.port,file=filepath)
                        self.logger.debug("SearchImages: LoadUrl: " + loadurl)
                        result = s.get(loadurl,auth=auth,cookies=cookies,stream=True)
                        #result = s.get(loadurl,auth=auth,cookies=cookies)
                        image = self.ProcessSearchImage(mediaItem,result)
                        
                    if image is not None:
                        imagepayload = (base64.encodebytes(image)).decode("utf-8")
                        if publishImages:
                            msgpayload = json.dumps({"message":message,"imagebase64":imagepayload})
                        else:
                            msgpayload = json.dumps({"message":message,"imageurl":loadurl})
                        #msgpayload = "{{ \"message\": \"{0}\", \"imagebase64\": \"{1}\" }}".format(message,imgpayload)

                    #imageio.mimsave('movie.gif',images, duration=1.5)
                    #try:
                    #    slack = Slacker(self.token)
                    #    with open('movie.gif', 'rb') as f:
                    #        slack.files.upload(file_=BytesIO(f.read()),
                    #           title="Image'",
                    ##            channels=slack.channels.get_channel_id('camera'),
                    #            filetype='gif')
                    #except Exception as slackEx:
                    #    print(str(slackEx))
                    #'found': '3', 
                    #'items[0].Channel': '0', 
                    #'items[0].Cluster': '171757', 
                    #'items[0].Disk': '9',
                    #'items[0].EndTime': '2019-12-06 08:33:29', 
                    #'items[0].FilePath': '/mnt/dvr/2019-12-06...0][0].jpg', 
                    #'items[0].Length': '674816', 
                    #'items[0].Partition': '1', 
                    #'items[0].StartTime': '2019-12-06 08:33:29', 
                    #'items[0].Type': 'jpg',
                    #'items[0].VideoStream': 'Main',
                    #result = s.get(finderurl,auth=auth,cookies=cookies)
            else: #if result.status_code == 200:
                self.logger.info("SearchImages: Nothing Found for " + objectId)
        except Exception as ex:
            # if there's been an error and we've got an object id, close the finder.
            print("Error in search images: " + str(ex))
            if len(objectId) > 0:
                finderurl = MEDIA_CLOSE.format(host=self.host,protocol=self.protocol,port=self.port,
                object=objectId)
                result = s.get(finderurl,auth=auth,cookies=cookies).content
            pass

        return ""
    #def SearchImages(self,channel,starttime, endtime, events,nopublish=True, message='',delay=0):

    def SearchClips(self,channel,starttime, endtime, events,publishImages=False, message='',delay=0):
        """Searches for clips for the channel
        channel is a numerical channel index (starts at 1)
        starttime is the start search time
        endtime is the end search time (or now)
        events is a list of event types
        Posts the url of the found clip"""
        #Create Finder
        #http://<ip>/cgi-bin/mediaFileFind.cgi?action=factory.create 
        MEDIA_FINDER="{protocol}://{host}:{port}/cgi-bin/mediaFileFind.cgi?action=factory.create"
        MEDIA_START="{protocol}://{host}:{port}/cgi-bin/mediaFileFind.cgi?action=findFile&object={object}&condition.Channel={channel}" + \
            "&condition.StartTime={starttime}&condition.EndTime={endtime}&condition.Types[0]=dav&condition.Flag[0]=Event" \
            "&condition.Events[0]={events}"
        MEDIA_START="{protocol}://{host}:{port}/cgi-bin/mediaFileFind.cgi?action=findFile&object={object}" + \
            "&condition.Channel={channel}" + \
            "&condition.StartTime={starttime}&condition.EndTime={endtime}" + \
            "&condition.Flags%5b0%5d=Event&condition.Types%5b0%5d=dav"
            #&condition.Types=%5b0%5d=jpg" 
            #&condition.Types[0]=jpg
            #&condition.Flags[0]=Event&condition.Types[0]=jpg
            #&condition.Flags%5b0%5d=Event&condition.Types%5b0%5d=jpg
            #%5B{events}%5D
        #MEDIA_START="{protocol}://{host}:{port}/cgi-bin/mediaFileFind.cgi?action=findFile&object={object}" + \
        #    "&condition.Channel={channel}" + \
        #    "&condition.StartTime=2019-12-05%2006:20:48&condition.EndTime=2019-12-05%2009:28:48&condition.Flags%5b0%5d=Event&condition.Types%5b0%5d=jpg"

        #Start Find
        #http://<ip>/cgi-bin/mediaFileFind.cgi?action=findFile&object=<objectId>&condition.Channel=<channel>&condition.StartTime=
        #  <start>&condition.EndTime=<end>&condition.Dirs[0]=<dir>&condition.Types[0]=<type>&condition.Flag[0]=<flag>&condition.E vents[0]=<event>
        #Start to find file wth the above condition. 
        # If start successfully, return true, else return false. 
        #  object : The object Id is got from interface in 10.1.1 
        #  Create condition.Channel: in which channel you want to find the file . 
        # condition.StartTime/condition.EndTime: the start/end time when recording. 
        # condition.Dirs: in which directories you want to find the file. It is an array. 
        #   The index starts from 0. The range of dir is {“/mnt/dvr/sda0”, “/mnt/dvr/sda1”}. 
        #   This condition can be omitted. If omitted, find files in all the directories. 
        # condition.Types: which types of the file you want to find. It is an array. 
        #   The index starts from 0. The range of type is {“dav”,“jpg”, “mp4”}. If omitted, 
        #   find files with all the types. 
        # condition.Flags: which flags of the file you want to find. It is an array. 
        #   The index starts from 0. The range of flag is {“Timing”, “Manual”, “Marker”, “Event”, “Mosaic”, “Cutout”}. 
        #   If omitted, find files with all the flags. 
        # condition.Event: by which event the record file is triggered. It is an array. 
        #   The index starts from 0. The range of event is {“AlarmLocal”, “VideoMotion”, “VideoLoss”, “VideoBlind”, “Traffic*”}. 
        #   This condition can be omitted. If omitted, find files of all the events. 
        #   Example: Find file in channel 1, in directory “/mnt/dvr/sda0",event type is "AlarmLocal" or 
        #   "VideoMotion", file type is “dav”, and time between 2011-1-1 12:00:00 and 2011-1-10 12:00:00 , 
        #   URL is: http://<ip>/cgi-bin/mediaFileFind.cgi?action=findFile&object=08137&condition.Channel=1&conditon.Dir[0]=”/mnt/dvr/sda0”& conditon.Event[0]=AlarmLocal&conditon.Event[1]=VideoMotion&condition.StartTime=2011-1-1%2012:00:00&condition.EndTi me=2011-1-10%2012:00:00

        #Find next File
        # http://<ip>/cgi-bin/mediaFileFind.cgi?action=findNextFile&object=<objectId>&count=<fileCount> Comment 
        MEDIA_NEXT="{protocol}://{host}:{port}/cgi-bin/mediaFileFind.cgi?action=findNextFile&object={object}&count=50"
        
        MEDIA_LOADFILE="{protocol}://{host}:{port}/cgi-bin/RPC_Loadfile{file}"

        #Close Finder
        #http://<ip>/cgi-bin/mediaFileFind.cgi?action=close&object=<objectId> 
        MEDIA_CLOSE="{protocol}://{host}:{port}/cgi-bin/mediaFileFind.cgi?action=close&object={object}"

        if delay > 0:
            time.sleep(delay)

        finderurl  = MEDIA_FINDER.format(
                host=self.host,
                protocol=self.protocol,
                port  = self.port
            )
        objectId = ""
        cookies = {}
        s = requests.Session()
        if self.auth == "digest":
            auth = requests.auth.HTTPDigestAuth(self.user, self.password)
        else:
            auth = auth=requests.auth.HTTPBasicAuth(self.user, self.password)

        channelName = "Unknown"
        try:
            channelName = self.channels[channel-1]
        except:
            pass

        self.logger.info("SearchClips Finder Url: " + finderurl)
        try:
            #first request needs authentication
            if self.auth == "digest":
                result = s.get(finderurl, stream=True,auth=auth,cookies=cookies).content
            else:
                result = s.get(finderurl, stream=True,auth=auth,cookies=cookies).content

            #result = b'result=3021795080\r\n' 
            # Get the object id of the finder request, needed for subsequent searches
            objectId = self.ConvertLinesToDict(result.decode())["result"]
            self.logger.info("SearchClips:  Opened a search object: " + objectId)
            # perform a search.  Startime and endtime in the following format: 2011-1-1%2012:00:00
            finderurl = MEDIA_START.format(host=self.host,protocol=self.protocol,port=self.port,
                object=objectId,channel=channel,
                starttime=starttime.strftime("%Y-%m-%d%%20%H:%M:%S"),
                endtime=endtime.strftime("%Y-%m-%d%%20%H:%M:%S")
                ,events="*")
            #finderurl = finderurl + requests.utils.quote("&condition.Types[0]=dav")
            self.logger.info("SearchClips:  FinderURL: " + finderurl)
            result = s.get(finderurl, stream=True,auth=auth,cookies=cookies)
            if result.status_code == 200:
                finderurl = MEDIA_NEXT.format(host=self.host,protocol=self.protocol,port=self.port,object=objectId)
                result = s.get(finderurl,auth=auth,cookies=cookies)
                mediaItem = {}
                if result.status_code == 200:
                    #start downloading the images.
                    mediaItem = self.ConvertLinesToDict(result.content.decode())
                    finderurl = MEDIA_CLOSE.format(host=self.host,protocol=self.protocol,port=self.port,
                        object=objectId)
                    
                    # Close the media find object
                    result = s.get(finderurl,auth=auth,cookies=cookies).content
                    #images = []
                    #imagesize = 0
                    #expectedsize = 0
                    image = None
                    self.logger.info("SearchClips: Found " + str(len(mediaItem)) + " images to process")
                    
                    filepath = ""

                    if type(mediaItem) is list:
                        for item in mediaItem:
                            filepath = item['FilePath']
                            self.logger.debug("SearchClips: Creating url for image: " + filepath)
                            loadurl = MEDIA_LOADFILE.format(host=self.host,protocol=self.protocol,port=self.port,file=filepath)
                            self.logger.debug("SearchClips: LoadUrl: " + loadurl)
                            #result = s.get(loadurl,auth=auth,cookies=cookies,stream=True)
                            if not publishImages:
                                self.logger.debug("SearchClips:  Publishing " + filepath)
                                self.client.publish(self.basetopic +"/{0}/Clip".format(channelName),loadurl)
                            #result = s.get(loadurl,auth=auth,cookies=cookies)
                            #image = self.ProcessSearchImage(item,result)
                            #if image is not None:
                            #    break
                    else:
                        filepath = mediaItem['FilePath']
                        self.logger.debug("SearchClips: Creating url for image: " + filepath)
                        loadurl = MEDIA_LOADFILE.format(host=self.host,protocol=self.protocol,port=self.port,file=filepath)
                        self.logger.debug("SearchImages: LoadUrl: " + loadurl)
                        #result = s.get(loadurl,auth=auth,cookies=cookies,stream=True)
                        if not publishImages:
                            self.logger.debug("SearchClips:  Publishing " + filepath)
                            self.client.publish(self.basetopic +"/{0}/Clip".format(channelName),loadurl)
                        #result = s.get(loadurl,auth=auth,cookies=cookies)
                        #image = self.ProcessSearchImage(mediaItem,result)
                        
            else: #if result.status_code == 200:
                self.logger.info("SearchClips: Nothing Found for " + objectId)
        except Exception as ex:
            # if there's been an error and we've got an object id, close the finder.
            print("Error in search clips: " + str(ex))
            if len(objectId) > 0:
                finderurl = MEDIA_CLOSE.format(host=self.host,protocol=self.protocol,port=self.port,
                object=objectId)
                result = s.get(finderurl,auth=auth,cookies=cookies).content
            pass

        return ""
    #def SearchClips(self,channel,starttime, endtime, events,nopublish=True, message='',delay=0):

    def ProcessSearchImage(self,item,result):
        #image = result.raw.read()
        #with open("1.jpg", 'wb') as f:
        #    for chunk in result:
        #        f.write(chunk)
        image = result.content
        imagesize = len(image)
        #image = result.content
        
        expectedsize =  int(item['Length'])
        expectedsize = int(float(expectedsize) * 0.65)
        self.logger.debug("SearchImages: Image " + item['FilePath'] + " Expected Size: (85%)" + str(expectedsize) 
            + "  Downloaded Size: " + str(imagesize))
        if imagesize >= expectedsize:
            #imagepayload = ""
            if image is not None and len(image) > 0:
                self.logger.debug("SearchImages:  This one meets size requirements: " + item['FilePath'])
                #fp = open("image.jpg", "wb")
                #fp.write(image) #r.text is the binary data for the PNG returned by that php script
                #fp.close()
                #construct image payload
                #{{ \"message\": \"Motion Detected: {0}\", \"imagebase64\": \"{1}\" }}"
                self.logger.info("SearchImages:   heres an image to post")
                return image
            else:
                self.logger.debug("SearchImages: Image too small: " + item['FilePath'] + " @  " + str(imagesize))
            #try:
            #    im = Image.open(BytesIO(result.content))
            #    im.resize((im.size[0] // 2, im.size[1] // 2), Image.ANTIALIAS) 
            #    images.append(im)
            #except Exception as imgEx:
            #    print(str(imgEx))
            #    pass
        #fp = open("image" + str(imagecount) + ".jpg", "wb")
        #fp.write(result.content) #r.text is the binary data for the PNG returned by that php script
        #fp.close()

    def CreatePlaybackUrl(self, channel, starttime):
        """Creates a playback url for the specified channel and starttime
        channel (index number starts at 1)
        starttime datetime object for start time of playback"""
        playbackStart = starttime - datetime.timedelta(seconds=self.playbackoffset)
        playbackEnd = playbackStart + datetime.timedelta(seconds=self.playbacklength)
        playbackurl  = self.PLAYBACK_TEMPLATE.format(
                host=self.host,
                port  = 554,
                channel=channel+1,
                starttime=playbackStart.strftime("%Y-%m-%d%%20%H:%M:%S"),
                endtime=playbackEnd.strftime("%Y-%m-%d%%20%H:%M:%S")
            )
        return playbackurl

    # Connected to camera
    def OnConnect(self):
        self.logger.debug("[{0}] OnConnect()".format(self.Name))
        self.Connected = True

    #disconnected from camera
    def OnDisconnect(self, reason):
        self.logger.debug("[{0}] OnDisconnect({1})".format(self.Name, reason))
        self.Connected = False

    #on receive data from camera.
    def OnReceive(self, data):
        #self.client.loop_forever()
        Data = data.decode("utf-8", errors="ignore")    
        self.logger.debug("[{0}]: {1}".format(self.Name, Data))

        crossData = ""

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
                Alarm["channel"] = self.Name + ":" + str(index)

            eventStart = False
            camera = Alarm["channel"]
            #mqttc.connect(self.mqtt["IP"], int(self.mqtt["port"]), 60)
            if Alarm["Code"] == "VideoMotion":
                self.logger.info("Video Motion received: "+  Alarm["name"] + " Index: " + Alarm["channel"] + " Code: " + Alarm["Code"])
                if not self.client.connected_flag:
                        self.client.reconnect()
                if Alarm["action"] == "Start":
                    eventStart = True
                    self.client.publish(self.basetopic +"/" + Alarm["Code"] + "/" + Alarm["channel"] ,"ON")
                    self.client.publish(self.basetopic +"/" + Alarm["channel"] + "/event" ,"ON")
                    if self.alerts:
                        #possible new process:
                        #http://192.168.10.66/cgi-bin/snapManager.cgi?action=attachFileProc&Flags[0]=Event&Events=[VideoMotion%2CVideoLoss]
                        process = threading.Thread(target=self.SnapshotImage,args=(index+self.snapshotoffset,Alarm["channel"],"Motion Detected: {0}".format(Alarm["channel"]),self.publishImages))
                        process.daemon = True                            # Daemonize thread
                        process.start()
                        
                    #send playback url to playback topic
                    if self.playbackoffset > -1:
                        playbackurl = self.CreatePlaybackUrl(index,datetime.datetime.now())
                        self.client.publish(self.basetopic +"/" + Alarm["channel"] + "/playback" ,playbackurl)   
                else: #if Alarm["action"] == "Start":
                    eventStart = False
                    self.client.publish(self.basetopic +"/" + Alarm["Code"] + "/" + Alarm["channel"] ,"ON")
                    self.client.publish(self.basetopic +"/" + Alarm["channel"] + "/event" ,"OFF")
                    #self.logger.info("ReceiveData: calling search Clips") 
                    #starttime = datetime.datetime.now() - datetime.timedelta(minutes=1)
                    #endtime = datetime.datetime.now() 
                    #process2 = threading.Thread(target=self.SearchClips,args=(index+self.snapshotoffset,starttime,endtime,'',False,'Search Clips VideoMotion',30,self.publishImages))
                    #process2.daemon = True                            # Daemonize thread
                    #process2.start()
            elif Alarm["Code"] == "AlarmLocal":
                self.logger.info("Alarm Local received: "+  Alarm["name"] + " Index: " + str(index) + " Code: " + Alarm["Code"])
                # Start action reveived, turn alarm on.
                if Alarm["action"] == "Start":
                    eventStart = True
                    if not self.client.connected_flag:
                        self.client.reconnect()
                    self.client.publish(self.basetopic +"/" + Alarm["Code"] + "/" +  str(index) ,"ON")
                else: #if Alarm["action"] == "Start":
                    eventStart = False
                    self.client.publish(self.basetopic +"/" + Alarm["Code"] + "/" +  str(index) ,"OFF")
            elif Alarm["Code"] ==  "CrossRegionDetection" or Alarm["Code"] ==  "CrossLineDetection":
                if Alarm["action"] == "Start":
                    eventStart = True
                    self.client.publish(self.basetopic +"/" + Alarm["channel"] + "/event" ,"ON")
                    regionText = Alarm["Code"]
                    try:

                        crossData = json.loads(Alarm["data"])
                        self.logger.info(Alarm["Code"] + " received: " + Alarm["data"] )
                        if "Direction" not in crossData:
                            direction = "unknown"                        
                        else:
                            direction = crossData["Direction"]

                        region = crossData["Name"]
                        object = crossData["Object"]["ObjectType"]
                        regionText = "{} With {} in {} direction for {} region".format(Alarm["Code"],object,direction,region)
                    except Exception as ivsExcept:
                        self.logger.error("Error getting IVS data: " + str(ivsExcept))
                        
                    self.client.publish(self.basetopic +"/IVS/" + Alarm["channel"] ,regionText)
                    if self.alerts:
                        #possible new process:
                        #http://192.168.10.66/cgi-bin/snapManager.cgi?action=attachFileProc&Flags[0]=Event&Events=[VideoMotion%2CVideoLoss]
                        process = threading.Thread(target=self.SnapshotImage,args=(index+self.snapshotoffset,Alarm["channel"],"IVS: {0}: {1}".format(Alarm["channel"],regionText,self.publishImages)))
                        process.daemon = True                            # Daemonize thread
                        process.start() 
                    if self.playbackoffset > -1:
                        playbackurl = self.CreatePlaybackUrl(index,datetime.datetime.now())
                        self.client.publish(self.basetopic +"/" + Alarm["channel"] + "/playback" ,playbackurl)  
                else:   #if Alarm["action"] == "Start":
                    eventStart = False
                    self.client.publish(self.basetopic +"/" + Alarm["channel"] + "/event" ,"OFF")
                    #self.logger.info("ReceiveData: calling search Clips") 
                    #starttime = datetime.datetime.now() - datetime.timedelta(minutes=1)
                    #endtime = datetime.datetime.now() 
                    #process2 = threading.Thread(target=self.SearchClips,args=(index+self.snapshotoffset,starttime,endtime,'',False,'Search Clips IVS',30,self.publishImages))
                    #process2.daemon = True                            # Daemonize thread
                    #process2.start()

            else: #if Alarm["Code"] == "VideoMotion": - unknown event
                self.logger.info("dahua_event_received: "+  Alarm["name"] + " Index: " + Alarm["channel"] + " Code: " + Alarm["Code"])
                if Alarm["action"] == "Start": 
                    eventStart = True
                    self.client.publish(self.basetopic +"/" + Alarm["channel"] + "/event" ,"ON")
                else:
                    eventStart = False
                    self.client.publish(self.basetopic +"/" + Alarm["channel"] + "/event" ,"OFF")
                self.client.publish(self.basetopic +"/" + Alarm["channel"] + "/" + Alarm["name"],Alarm["Code"])
                
            #if self.homebridge:
            #    if eventStart:
            #        self.client.publish(self.basetopic + "/motion",camera)
            #    else:
            #        self.client.publish(self.basetopic + "/motion/reset",camera)
            #2019-01-27 08:28:19,658 - __main__ - INFO - dahua_event_received: NVR Index: NVR:0 Code: CrossRegionDetection
            #2019-01-27 08:28:19,674 - __main__ - INFO - dahua_event_received: NVR Index: NVR:0 Code: CrossRegionDetection
            #2019-01-27 08:28:19,703 - __main__ - INFO - dahua_event_received: NVR Index: NVR:0 Code: CrossLineDetection
            #2019-01-27 08:28:19,729 - __main__ - INFO - dahua_event_received: NVR Index: NVR:0 Code: CrossRegionDetection
            #2019-01-27 08:28:19,743 - __main__ - INFO - dahua_event_received: NVR Index: NVR:0 Code: CrossLineDetection
            #mqttc.disconnect()
            #self.hass.bus.fire("dahua_event_received", Alarm)

    def ConvertLinesToDict(self,Data):
        results = dict()
        items = []
        currentIndex = ''
        indexCount = 0
        for Line in Data.split("\r\n"):
            if len(Line) == 0:
                if len(items) > 0:
                    items.append(results)
                    return items
                else:
                    return results
            if Line.find("[") > -1:
                if 'found' in results:
                    indexCount = int(results['found'])
                    results = dict()
                #array value found
                #items[0].Channel': '0'
                Item, Value = Line.split('=')
                Index, Key = Item.split(".")
                if currentIndex == '':
                    currentIndex = Index
                #Index= Index.replace("]","")
                if Index != currentIndex:
                    currentIndex = Index
                    items.append(results)
                    results = dict()
                results[Key] = Value.replace("\r\n","")
            else:

                for KeyValue in Line.split(';'):
                    Key, Value = KeyValue.split('=')
                    results[Key] = Value.replace("\r\n","")
        #else:
        #    for KeyValue in Data.split(';'):
        #        Key, Value = KeyValue.split('=')
        #        results[Key] = Value.replace("\r\n","")
        if len(items) > 0:
            return items
        else:
            return results
