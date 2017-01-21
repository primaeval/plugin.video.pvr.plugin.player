from BaseHTTPServer import BaseHTTPRequestHandler,HTTPServer
from xbmcgui import ListItem
from xbmc import executebuiltin, Player
from xbmcaddon import Addon
from time import time, sleep
from threading import Thread

MyAddon = Addon("plugin.video.pvr.plugin.player")
PORT_NUMBER = int(MyAddon.getSetting("Port"))

class myHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type','text/html')
        self.end_headers()

        Last = int(MyAddon.getSetting("LastPlay"))
        Now = int(time())
        if Now-Last>4:
            MyAddon.setSetting("LastPlay","%d" % Now)
        else:
            return 

        url = self.path[2:]
        listitem = ListItem(path=url)
        listitem.setInfo(type="Video", infoLabels={"mediatype": "movie", "title": "LiveTV"})
        Player().play(url, listitem)
        return

try:
    httpd = HTTPServer(('', PORT_NUMBER), myHandler)
    httpd_thread = Thread(target=httpd.serve_forever)
    httpd_thread.start()
    while not xbmc.abortRequested:
        sleep(2)
    httpd_thread = None
    httpd.shutdown()
    httpd.server_close()
except: 
    executebuiltin('Notification(PVR Plugin Player,"Can not open Server at port {0}", {1})'.format(PORT_NUMBER,3000))
    pass