import pytest
import CameraEvents

class dummy_mqtt(object):
    def __init__(self):
        self.payload = ''
        self.topic = ''
    
    def publish(self,topic,payload):
        self.payload = payload
        self.topic = topic
        pass

def create_device():
    device_cfg = {}
    channels = {}
    device_cfg["channels"] = channels
    #device_cfg.set(["channels"]
    device_cfg["Name"] = "test"
    device_cfg["user"] =  "user"
    device_cfg["password"] = "pass"
    device_cfg["auth"] = "digest"
    device_cfg["mqtt"] = "localhost"
    device_cfg["protocol"]  = "http"
    device_cfg["host"] =  "192.168.1.108"
    device_cfg["port"] = 80
    device_cfg["alerts"] = False
    device_cfg["snapshotoffset"] = 0
    client = dummy_mqtt()
    client.connected_flag = True

    basetopic = "CameraEvents"
    
    device = CameraEvents.DahuaDevice("Camera", device_cfg, client,basetopic,homebridge=False,publishImages=True)
    return device

def func(x):
    return x + 1

def test_answer():
    assert func(3) == 4

def test_answer2():
    assert func(3) == 4

def test_dahua_create():
    device = create_device()
    assert device is not None

def test_dahua_receive_video_motion():
    device = create_device()
    data = str.encode("--myboundary\r\nContent-Length:37\r\nCode=VideoMotion;action=Start;index=1")
    device.OnReceive(data)
    assert device.client.topic == "CameraEvents/Camera:1/event" and device.client.payload == 'ON'
    data = str.encode("--myboundary\r\nContent-Length:37\r\nCode=VideoMotion;action=Stop;index=1")
    device.OnReceive(data)
    assert device.client.topic == "CameraEvents/Camera:1/event" and device.client.payload == 'OFF'


def test_dahua_receive_alarm_local():
    device = create_device()
    data = str.encode("--myboundary\r\nContent-Length:37\r\nCode=AlarmLocal;action=Start;index=1")
    device.OnReceive(data)
    assert device.client.topic == "CameraEvents/AlarmLocal/1" and device.client.payload == 'ON'
    data = str.encode("--myboundary\r\nContent-Length:37\r\nCode=AlarmLocal;action=Stop;index=1")
    device.OnReceive(data)
    assert device.client.topic == "CameraEvents/AlarmLocal/1" and device.client.payload == 'OFF'

def test_dahua_receive_alarm_local_Index_mismatch():
    device = create_device()
    data = str.encode("--myboundary\r\nContent-Length:37\r\nCode=AlarmLocal;action=Start;index=5")
    device.OnReceive(data)
    assert device.client.topic == "CameraEvents/AlarmLocal/5" and device.client.payload == 'ON'
    data = str.encode("--myboundary\r\nContent-Length:37\r\nCode=AlarmLocal;action=Stop;index=5")
    device.OnReceive(data)
    assert device.client.topic == "CameraEvents/AlarmLocal/5" and device.client.payload == 'OFF'


def test_dahua_receive_crossRegion():
    device = create_device()
    data = str.encode('Code=CrossRegionDetection;action=Start;index=1;data={' \
    '"Action" : "Cross",' \
    '"Class" : "Normal",' \
    '"CountInGroup" : 1,' \
    '"DetectRegion" : [ ' \
    '   [ 789, 3839 ], ' \
    '   [ 789, 3866 ],' \
    '   [ 2124, 2649 ],' \
    '   [ 3135, 2757 ], ' \
    '   [ 3721, 2190 ], ' \
    '   [ 6371, 3893 ], ' \
    '   [ 7766, 5217 ], ' \
    '   [ 7422, 8083 ], ' \
    '   [ 1982, 8110 ] ' \
    '], ' \
    '"Direction" : "Enter", ' \
    '"EventSeq" : 3, ' \
    '"FrameSequence" : 2781, ' \
    '"GroupID" : 0, ' \
    '"IndexInGroup" : 0, ' \
    '"LocaleTime" : "2019-01-31 18:04:58", ' \
    '"Mark" : 0, ' \
    '"Name" : "Courtyard", ' \
    '"Object" : { ' \
    ' "Action" : "Appear", ' \
    ' "BoundingBox" : [ 680, 1176, 1864, 5880 ], ' \
    ' "Center" : [ 1272, 3528 ], ' \
    ' "Confidence" : 0, ' \
    ' "FrameSequence" : 0, ' \
    ' "LowerBodyColor" : [ 0, 0, 0, 0 ], ' \
    ' "MainColor" : [ 0, 0, 0, 0 ], ' \
    ' "ObjectID" : 84, ' \
    ' "ObjectType" : "Human", ' \
    ' "RelativeID" : 0, ' \
    ' "Source" : 0.0, ' \
    ' "Speed" : 0, ' \
    ' "SpeedTypeInternal" : 0 ' \
    '}, ' \
    '"PTS" : 42951682690.0, ' \
    '"RuleId" : 1, ' \
    '"Sequence" : 0, ' \
    '"Source" : 30670016.0, ' \
    '"Track" : null, ' \
    '"UTC" : 1548929098.0, ' \
    '"UTCMS" : 633 ' \
    '} ' )
    device.OnReceive(data)
    
    assert device is not None

def test_dahua_receive_crossRegion_createSnapshot():
    device = create_device()
    data = str.encode('Code=CrossRegionDetection;action=Start;index=1;data={' \
    '"Action" : "Cross",' \
    '"Class" : "Normal",' \
    '"CountInGroup" : 1,' \
    '"DetectRegion" : [ ' \
    '   [ 789, 3839 ], ' \
    '   [ 789, 3866 ],' \
    '   [ 2124, 2649 ],' \
    '   [ 3135, 2757 ], ' \
    '   [ 3721, 2190 ], ' \
    '   [ 6371, 3893 ], ' \
    '   [ 7766, 5217 ], ' \
    '   [ 7422, 8083 ], ' \
    '   [ 1982, 8110 ] ' \
    '], ' \
    '"Direction" : "Enter", ' \
    '"EventSeq" : 3, ' \
    '"FrameSequence" : 2781, ' \
    '"GroupID" : 0, ' \
    '"IndexInGroup" : 0, ' \
    '"LocaleTime" : "2019-01-31 18:04:58", ' \
    '"Mark" : 0, ' \
    '"Name" : "Courtyard", ' \
    '"Object" : { ' \
    ' "Action" : "Appear", ' \
    ' "BoundingBox" : [ 680, 1176, 1864, 5880 ], ' \
    ' "Center" : [ 1272, 3528 ], ' \
    ' "Confidence" : 0, ' \
    ' "FrameSequence" : 0, ' \
    ' "LowerBodyColor" : [ 0, 0, 0, 0 ], ' \
    ' "MainColor" : [ 0, 0, 0, 0 ], ' \
    ' "ObjectID" : 84, ' \
    ' "ObjectType" : "Human", ' \
    ' "RelativeID" : 0, ' \
    ' "Source" : 0.0, ' \
    ' "Speed" : 0, ' \
    ' "SpeedTypeInternal" : 0 ' \
    '}, ' \
    '"PTS" : 42951682690.0, ' \
    '"RuleId" : 1, ' \
    '"Sequence" : 0, ' \
    '"Source" : 30670016.0, ' \
    '"Track" : null, ' \
    '"UTC" : 1548929098.0, ' \
    '"UTCMS" : 633 ' \
    '} ' )
    device.OnReceive(data)
    
    assert device is not None

def test_dahua_receive_crossRegion_NoDirection():
    device = create_device()
    data = str.encode('Code=CrossRegionDetection;action=Start;index=1;data={' \
    '"Action" : "Cross",' \
    '"Class" : "Normal",' \
    '"CountInGroup" : 1,' \
    '"DetectRegion" : [ ' \
    '   [ 789, 3839 ], ' \
    '   [ 789, 3866 ],' \
    '   [ 2124, 2649 ],' \
    '   [ 3135, 2757 ], ' \
    '   [ 3721, 2190 ], ' \
    '   [ 6371, 3893 ], ' \
    '   [ 7766, 5217 ], ' \
    '   [ 7422, 8083 ], ' \
    '   [ 1982, 8110 ] ' \
    '], ' \
    '"EventSeq" : 3, ' \
    '"FrameSequence" : 2781, ' \
    '"GroupID" : 0, ' \
    '"IndexInGroup" : 0, ' \
    '"LocaleTime" : "2019-01-31 18:04:58", ' \
    '"Mark" : 0, ' \
    '"Name" : "Courtyard", ' \
    '"Object" : { ' \
    ' "Action" : "Appear", ' \
    ' "BoundingBox" : [ 680, 1176, 1864, 5880 ], ' \
    ' "Center" : [ 1272, 3528 ], ' \
    ' "Confidence" : 0, ' \
    ' "FrameSequence" : 0, ' \
    ' "LowerBodyColor" : [ 0, 0, 0, 0 ], ' \
    ' "MainColor" : [ 0, 0, 0, 0 ], ' \
    ' "ObjectID" : 84, ' \
    ' "ObjectType" : "Human", ' \
    ' "RelativeID" : 0, ' \
    ' "Source" : 0.0, ' \
    ' "Speed" : 0, ' \
    ' "SpeedTypeInternal" : 0 ' \
    '}, ' \
    '"PTS" : 42951682690.0, ' \
    '"RuleId" : 1, ' \
    '"Sequence" : 0, ' \
    '"Source" : 30670016.0, ' \
    '"Track" : null, ' \
    '"UTC" : 1548929098.0, ' \
    '"UTCMS" : 633 ' \
    '} ' )
    device.OnReceive(data)
    
def test_dahua_receive_crossRegion_NoName():
    device = create_device()
    data = str.encode('Code=CrossRegionDetection;action=Start;index=1;data={' \
    '"Action" : "Cross",' \
    '"Class" : "Normal",' \
    '"CountInGroup" : 1,' \
    '"DetectRegion" : [ ' \
    '   [ 789, 3839 ], ' \
    '   [ 789, 3866 ],' \
    '   [ 2124, 2649 ],' \
    '   [ 3135, 2757 ], ' \
    '   [ 3721, 2190 ], ' \
    '   [ 6371, 3893 ], ' \
    '   [ 7766, 5217 ], ' \
    '   [ 7422, 8083 ], ' \
    '   [ 1982, 8110 ] ' \
    '], ' \
    '"EventSeq" : 3, ' \
    '"FrameSequence" : 2781, ' \
    '"GroupID" : 0, ' \
    '"IndexInGroup" : 0, ' \
    '"LocaleTime" : "2019-01-31 18:04:58", ' \
    '"Mark" : 0, ' \
    '"Object" : { ' \
    ' "Action" : "Appear", ' \
    ' "BoundingBox" : [ 680, 1176, 1864, 5880 ], ' \
    ' "Center" : [ 1272, 3528 ], ' \
    ' "Confidence" : 0, ' \
    ' "FrameSequence" : 0, ' \
    ' "LowerBodyColor" : [ 0, 0, 0, 0 ], ' \
    ' "MainColor" : [ 0, 0, 0, 0 ], ' \
    ' "ObjectID" : 84, ' \
    ' "ObjectType" : "Human", ' \
    ' "RelativeID" : 0, ' \
    ' "Source" : 0.0, ' \
    ' "Speed" : 0, ' \
    ' "SpeedTypeInternal" : 0 ' \
    '}, ' \
    '"PTS" : 42951682690.0, ' \
    '"RuleId" : 1, ' \
    '"Sequence" : 0, ' \
    '"Source" : 30670016.0, ' \
    '"Track" : null, ' \
    '"UTC" : 1548929098.0, ' \
    '"UTCMS" : 633 ' \
    '} ' )
    device.OnReceive(data)

    assert device is not None

def test_dahua_receive_crossLine():
   device = create_device()
   data = str.encode('Code=CrossLineDetection;action=Start;index=0;data={'\
   '"Class" : "Normal",'\
   '"CountInGroup" : 1,'\
   '"DetectLine" : ['\
   '   [ 3843, 5677 ],'\
   '   [ 6512, 5136 ]'\
   '],'\
   '"Direction" : "RightToLeft",'\
   '"EventSeq" : 1,'\
   '"FrameSequence" : 8723,'\
   '"GroupID" : 1,'\
   '"IndexInGroup" : 0,'\
   '"LocaleTime" : "2019-02-02 16:10:50",'\
   '"Mark" : 0,'\
   '"Name" : "Gate",'\
   '"Object" : {'\
   '   "Action" : "Appear",'\
   '   "BoundingBox" : [ 2944, 3520, 5072, 7872 ],'\
   '   "Center" : [ 4008, 5696 ],'\
   '   "Confidence" : 0,'\
   '   "FrameSequence" : 0,'\
   '   "ObjectID" : 105,'\
   '   "ObjectType" : "Smoke",'\
   '   "RelativeID" : 0,'\
   '   "Source" : 0.0,'\
   '   "Speed" : 0,'\
   '   "SpeedTypeInternal" : 0'\
   '},'\
   '"PTS" : 42950631010.0,'\
   '"RuleId" : 1,'\
   '"Sequence" : 0,'\
   '"Source" : 36149128.0,'\
   '"Track" : null,'\
   '"UTC" : 1549080650.0,'\
   '"UTCMS" : 702'\
   '} ')
   device.OnReceive(data)
    
   assert device is not None