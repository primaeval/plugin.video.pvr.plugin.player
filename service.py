from BaseHTTPServer import BaseHTTPRequestHandler,HTTPServer
from xbmcgui import ListItem
#from xbmc import executebuiltin, Player
import xbmc
from xbmcaddon import Addon
#from time import time, sleep
from threading import Thread
import datetime, time
from datetime import date, timedelta

# This is a throwaway variable to deal with a python bug
throwaway = datetime.datetime.strptime('20110101','%Y%m%d')

ADDON = Addon("plugin.video.pvr.plugin.player")
PORT_NUMBER = int(ADDON.getSetting("Port"))

def log(x):
    xbmc.log(repr(x))

def total_seconds(td):
    return (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6) / 10**6

def runService():
    log("[plugin.video.pvr.plugin.player] Starting Service...")
    xbmc.executebuiltin('RunPlugin(plugin://plugin.video.pvr.plugin.player/service)')
    log("[plugin.video.pvr.plugin.player] Finished Service...")
    now = datetime.datetime.now()
    ADDON.setSetting('serviced', str(now + timedelta(hours=0)).split('.')[0])
    
class KodiPlayer(xbmc.Player):
    def __init__(self, *args, **kwargs):
        xbmc.Player.__init__(self)
        self.file = None

    def onPlayBackStarted(self):
        self.file = self.getPlayingFile()    
        
    @classmethod
    def onPlayBackStopped(self):        
        self.file = None

class myHandler(BaseHTTPRequestHandler):
    def do_HEAD(s):
        url = s.path[2:]
        player_monitor.stop()
        player_monitor.play(url)
        while(player_monitor.file != None): #Timeout
            time.sleep(1)
        s.send_response(301)
        #s.send_header("Location", 'http://vs-hls-uk-live.akamaized.net/pool_30/live/bbc_one_hd/bbc_one_hd.isml/bbc_one_hd-pa4%3d128000-video%3d827008.m3u8')
        s.send_header("Location", player_monitor.file)
        s.end_headers()
    def do_GET(s):
        s.do_HEAD()
    '''
    def do_GETx(self):
        self.send_response(200)
        self.send_header('Content-type','text/html')
        self.end_headers()

        Last = int(ADDON.getSetting("LastPlay"))
        Now = int(time.time())
        if Now-Last>4:
            ADDON.setSetting("LastPlay","%d" % Now)
        else:
            return

        url = self.path[2:]
        listitem = ListItem(path=url)
        listitem.setInfo(type="Video", infoLabels={"mediatype": "movie", "title": "LiveTV"})
        xbmc.Player().play(url, listitem)
        return
    '''
    
player_monitor = KodiPlayer()
monitor = xbmc.Monitor()
timer = ADDON.getSetting('timer')
try:
    httpd = HTTPServer(('', PORT_NUMBER), myHandler)
    httpd_thread = Thread(target=httpd.serve_forever)
    httpd_thread.start()

    if ADDON.getSetting('startup') == 'true':
        runService()
    if timer and timer != 'None':
        while not xbmc.abortRequested:
            serviced = ADDON.getSetting('serviced')
            serviced_time = time.strptime(serviced.encode("utf8"), "%Y-%m-%d %H:%M:%S")
            last_time = datetime.datetime.fromtimestamp(time.mktime(serviced_time))
            next_time = None
            next_time = ADDON.getSetting('time')
            if next_time:
                hour,minute = next_time.split(':')
                now = datetime.datetime.now()
                next_time = now.replace(hour=int(hour),minute=int(minute),second=0,microsecond=0)
                if next_time < now:
                    next_time = next_time + timedelta(hours=24)
            if not next_time:
                quit()
            now = datetime.datetime.now()
            waiting_time = next_time - now
            seconds = total_seconds(waiting_time)
            if seconds == 0 and timer == 'Time':
                seconds = 86400
            elif seconds < 1:
                seconds = 1
            next = datetime.datetime.now() + timedelta(seconds=seconds+1)
            log("[plugin.video.pvr.plugin.player] Waiting Until %s (%s seconds to go)" % (str(next).split('.')[0], seconds))
            monitor.waitForAbort(float(seconds))
            time.sleep(1)
            if xbmc.abortRequested:
                quit()
            runService()
    else:
        while not xbmc.abortRequested:
            time.sleep(2)
    httpd_thread = None
    httpd.shutdown()
    httpd.server_close()
except Exception as detail:
    xbmc.executebuiltin('Notification(PVR Plugin Player,"Can not open Server at port {0}", {1})'.format(PORT_NUMBER,3000))
    pass