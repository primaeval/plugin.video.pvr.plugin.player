from rpc import RPC
from types import *
from xbmcswift2 import Plugin
from xbmcswift2 import actions
import HTMLParser
import datetime
import json
import os
import random
import re
import requests
import sqlite3
import time
import xbmc,xbmcaddon,xbmcvfs,xbmcgui
import xbmcplugin

plugin = Plugin()
big_list_view = False

def log2(v):
    xbmc.log(repr(v))

def log(v):
    xbmc.log(re.sub(',',',\n',repr(v)))

def get_icon_path(icon_name):
    addon_path = xbmcaddon.Addon().getAddonInfo("path")
    return os.path.join(addon_path, 'resources', 'img', icon_name+".png")


def remove_formatting(label):
    label = re.sub(r"\[/?[BI]\]",'',label)
    label = re.sub(r"\[/?COLOR.*?\]",'',label)
    return label

@plugin.route('/addon/<id>')
def addon(id):
    addon = plugin.get_storage(id)
    items = []
    for name in sorted(addon):
        url = addon[name]
        items.append(
        {
            'label': name,
            'path': url,
            'thumbnail':get_icon_path('tv'),
            'is_playable':True,
        })
    return items

@plugin.route('/player')
def player():
    if not plugin.get_setting('addons.folder'):
        dialog = xbmcgui.Dialog()
        dialog.notification("addons.ini Creator", "Set Folder",xbmcgui.NOTIFICATION_ERROR )
        xbmcaddon.Addon ('plugin.video.addons.ini.creator').openSettings()

    addons = plugin.get_storage("addons")
    for a in addons.keys():
        add = plugin.get_storage(a)
        add.clear()
    addons.clear()

    folder = plugin.get_setting("addons.folder")
    file = plugin.get_setting("addons.file")
    filename = os.path.join(folder,file)
    f = xbmcvfs.File(filename,"rb")
    lines = f.read().splitlines()

    addon = None
    for line in lines:
        if line.startswith('['):
            a = line.strip('[]')
            addons[a] = a
            addon = plugin.get_storage(a)
            addon.clear()
        elif "=" in line:
            (name,url) = line.split('=',1)
            if url and addon is not None:
                addon[name] = url

    items = []
    for id in sorted(addons):
        items.append(
        {
            'label': id,
            'path': plugin.url_for('addon',id=id),
            'thumbnail':get_icon_path('tv'),
        })
    return items

@plugin.route('/play/<url>')
def play(url):
    xbmc.executebuiltin('PlayMedia(%s)' % url)

@plugin.route('/pvr_subscribe')
def pvr_subscribe():
    plugin.set_setting("pvr.subscribe","true")
    xbmc.executebuiltin('Container.Refresh')

@plugin.route('/pvr_unsubscribe')
def pvr_unsubscribe():
    plugin.set_setting("pvr.subscribe","false")
    xbmc.executebuiltin('Container.Refresh')

@plugin.route('/add_folder/<id>/<name>/<path>')
def add_folder(id,name,path):
    folders = plugin.get_storage('folders')
    folders[path] = id
    folder_names = plugin.get_storage('folder_names')
    folder_names[path] = name
    xbmc.executebuiltin('Container.Refresh')

@plugin.route('/remove_folder/<path>')
def remove_folder(path):
    folders = plugin.get_storage('folders')
    if path in folders:
        del folders[path]
    folder_names = plugin.get_storage('folder_names')
    if path in folder_names:
        del folder_names[path]
    xbmc.executebuiltin('Container.Refresh')

@plugin.route('/clear_cache')
def clear_cache():
    last_read = plugin.get_storage('last_read')
    last_read.clear()
    xbmcvfs.delete('special://profile/addon_data/plugin.video.pvr.plugin.player/cache.json')

@plugin.route('/clear')
def clear():
    folders = plugin.get_storage('folders')
    folders.clear()
    folder_names = plugin.get_storage('folder_names')
    folder_names.clear()

@plugin.route('/add_channel')
def add_channel():
    channels = plugin.get_storage('channels')
    d = xbmcgui.Dialog()
    channel = d.input("Add Channel")
    if channel:
        channels[channel] = plugin.url_for('stream_search',channel=channel)
    xbmc.executebuiltin('Container.Refresh')


@plugin.route('/remove_channel')
def remove_channel():
    channels = plugin.get_storage('channels')
    channel_list = sorted(channels)
    d = xbmcgui.Dialog()
    which = d.select("Remove Channel",channel_list)
    if which == -1:
        return
    channel = channel_list[which]
    del channels[channel]
    xbmc.executebuiltin('Container.Refresh')

@plugin.route('/remove_this_channel/<channel>')
def remove_this_channel(channel):
    channels = plugin.get_storage('channels')
    del channels[channel]
    xbmc.executebuiltin('Container.Refresh')

@plugin.route('/clear_channels')
def clear_channels():
    channels = plugin.get_storage('channels')
    channels.clear()
    xbmc.executebuiltin('Container.Refresh')

@plugin.route('/import_channels')
def import_channels():
    channels = plugin.get_storage('channels')
    ids = plugin.get_storage('ids')
    d = xbmcgui.Dialog()
    filename = d.browse(1, 'Import Channels', 'files', '', False, False, 'special://home/')
    if not filename:
        return
    if filename.endswith('.ini'):
        lines = xbmcvfs.File(filename,'rb').read().splitlines()
        for line in lines:
            if not line.startswith('[') and not line.startswith('#') and "=" in line:
                channel_url = line.split('=',1)
                if len(channel_url) == 2:
                    name = channel_url[0]
                    channels[name] = ""
    elif filename.endswith('.xml') or filename.endswith('.xmltv'):
        data = xbmcvfs.File(filename,'rb').read()
        match = re.compile(
            '<channel.*?id="(.*?)">.*?<display-name.*?>(.*?)</display-name>',
            flags=(re.DOTALL | re.MULTILINE)
            ).findall(data)
        for id,name in match:
            channels[name] = ""
            ids[name] = id
    d.notification("PVR Plugin Player", "Finished Importing Channels")
    xbmc.executebuiltin('Container.Refresh')

@plugin.route('/make_m3u')
def make_m3u():
    channels = plugin.get_storage('channels')
    ids = plugin.get_storage('ids')
    f = xbmcvfs.File('special://profile/addon_data/plugin.video.pvr.plugin.player/channels.m3u','wb')
    f.write('#EXTM3U\n')
    for channel in sorted(channels):
        id = ids.get(channel,channel)
        url = channels.get(channel)
        if not url:
            url = plugin.url_for(play_channel,station=channel)
        if url.startswith('plugin'):
            url = ("http://localhost:%s/?" % plugin.get_setting('Port')) + url
        f.write('#EXTINF:-1 tvg-id="%s" tvg-name="%s" group-title="English" tvg-logo="%s.png",%s\n' % (id,id,id,channel))
        f.write('%s\n' % url.encode("utf8"))
    f.close()


@plugin.route('/export_channels')
def export_channels():
    channels = plugin.get_storage('channels')

    f = xbmcvfs.File('special://profile/addon_data/plugin.video.pvr.plugin.player/stream_searcher_export.ini','wb')
    for channel in sorted(channels):
        url = plugin.url_for('stream_search',channel=channel)
        s = "%s=%s\n" % (channel,url)
        f.write(s)
    f.close()


@plugin.route('/folder/<id>/<path>')
def folder(id,path):
    folders = plugin.get_storage('folders')
    try: response = RPC.files.get_directory(media="files", directory=path, properties=["thumbnail"])
    except: return
    files = response["files"]
    dirs = dict([[remove_formatting(f["label"]), f["file"]] for f in files if f["filetype"] == "directory"])
    links = {}
    thumbnails = {}
    for f in files:
        if f["filetype"] == "file":
            label = remove_formatting(f["label"])
            file = f["file"]
            while (label in links):
                label = "%s." % label
            links[label] = file
            thumbnails[label] = f["thumbnail"]

    items = []

    for label in sorted(dirs):
        folder_path = dirs[label]
        context_items = []
        if folder_path in folders:
            fancy_label = "[COLOR yellow][B]%s[/B][/COLOR] " % label
            context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Remove Folder', 'XBMC.RunPlugin(%s)' % (plugin.url_for(remove_folder, path=folder_path))))
        else:
            fancy_label = "[B]%s[/B]" % label
            context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Add Folder', 'XBMC.RunPlugin(%s)' % (plugin.url_for(add_folder, id=id, name=label, path=folder_path))))
        items.append(
        {
            'label': fancy_label,
            'path': plugin.url_for('folder',id=id, path=folder_path),
            'thumbnail': get_icon_path('tv'),
            'context_menu': context_items,
        })

    for label in sorted(links):
        items.append(
        {
            'label': label,
            'path': plugin.url_for('play',url=links[label]),
            'thumbnail': thumbnails[label],
        })
    return items

@plugin.route('/pvr')
def pvr():
    index = 0
    urls = []
    pvr_channels = {}
    for group in ["radio","tv"]:
        urls = urls + xbmcvfs.listdir("pvr://channels/%s/All channels/" % group)[1]
    for group in ["radio","tv"]:
        groupid = "all%s" % group
        try: json_query = RPC.PVR.get_channels(channelgroupid=groupid, properties=[ "thumbnail", "channeltype", "hidden", "locked", "channel", "lastplayed", "broadcastnow" ] )
        except: continue
        if "channels" in json_query:
            for channel in json_query["channels"]:
                channelname = channel["label"]
                channelid = channel["channelid"]-1
                channellogo = channel['thumbnail']
                streamUrl = urls[index]
                index = index + 1
                url = "pvr://channels/%s/All channels/%s" % (group,streamUrl)
                pvr_channels[url] = channelname
    items = []
    for url in sorted(pvr_channels, key=lambda x: pvr_channels[x]):
        name = pvr_channels[url]
        items.append(
        {
            'label': name,
            'path': url,
            'is_playable': True,
        })
    return items

@plugin.route('/subscribe')
def subscribe():
    folders = plugin.get_storage('folders')
    ids = {}
    for folder in folders:
        id = folders[folder]
        ids[id] = id
    all_addons = []
    for type in ["xbmc.addon.video", "xbmc.addon.audio"]:
        try: response = RPC.addons.get_addons(type=type,properties=["name", "thumbnail"])
        except: continue
        if "addons" in response:
            found_addons = response["addons"]
            all_addons = all_addons + found_addons

    seen = set()
    addons = []
    for addon in all_addons:
        if addon['addonid'] not in seen:
            addons.append(addon)
        seen.add(addon['addonid'])

    items = []

    pvr = plugin.get_setting('pvr.subscribe')
    context_items = []
    label = "PVR"
    if pvr == "true":
        fancy_label = "[COLOR yellow][B]%s[/B][/COLOR] " % label
        context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Remove Folder', 'XBMC.RunPlugin(%s)' % (plugin.url_for(pvr_unsubscribe))))
    else:
        fancy_label = "[B]%s[/B]" % label
        context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Add Folder', 'XBMC.RunPlugin(%s)' % (plugin.url_for(pvr_subscribe))))
    items.append(
    {
        'label': fancy_label,
        'path': plugin.url_for('pvr'),
        'thumbnail':get_icon_path('tv'),
        'context_menu': context_items,
    })

    addons = sorted(addons, key=lambda addon: remove_formatting(addon['name']).lower())
    for addon in addons:
        label = remove_formatting(addon['name'])
        id = addon['addonid']
        path = "plugin://%s" % id
        context_items = []
        if id in ids:
            fancy_label = "[COLOR yellow][B]%s[/B][/COLOR] " % label
            context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Remove Folder', 'XBMC.RunPlugin(%s)' % (plugin.url_for(remove_folder, path=path))))
        else:
            fancy_label = "[B]%s[/B]" % label
            context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Add Folder', 'XBMC.RunPlugin(%s)' % (plugin.url_for(add_folder, id=id, name=label, path=path))))
        items.append(
        {
            'label': fancy_label,
            'path': plugin.url_for('folder',id=id, path=path),
            'thumbnail': get_icon_path('tv'),
            'context_menu': context_items,
        })
    return items

@plugin.route('/service')
def service():
    if plugin.get_setting('channels.type') != '0':
        channels = plugin.get_storage('channels')
        ids = plugin.get_storage('ids')
        if plugin.get_setting('channels.clear') == 'true':
            channels.clear()
            ids.clear()
        if plugin.get_setting('channels.type') == '1':
            filename = plugin.get_setting('channels.file')
        else:
            filename = plugin.get_setting('channels.url')
        if filename.endswith('.ini'):
            lines = xbmcvfs.File(filename,'rb').read().splitlines()
            for line in lines:
                if not line.startswith('[') and not line.startswith('#') and "=" in line:
                    channel_url = line.split('=',1)
                    if len(channel_url) == 2:
                        name = channel_url[0]
                        channels[name] = ""
                        #log(name)
        elif filename.endswith('.xml') or filename.endswith('.xmltv'):
            data = xbmcvfs.File(filename,'rb').read()
            match = re.compile(
                '<channel.*?id="(.*?)">.*?<display-name.*?>(.*?)</display-name>',
                flags=(re.DOTALL | re.MULTILINE)
                ).findall(data)
            for id,name in match:
                channels[name] = ""
                ids[name] = id
    file_name = 'special://profile/addon_data/plugin.video.pvr.plugin.player/cache.json'
    folders = plugin.get_storage('folders')
    last_read = plugin.get_storage('last_read')
    streams = {}
    if plugin.get_setting('folders.clear') == 'false':
        f = xbmcvfs.File(file_name,'rb')
        data = f.read()
        f.close()
        if data:
            streams = json.loads(data)

    for folder in folders:
        path = folder
        id = folders[folder]
        now = datetime.datetime.now()
        last_read[folder] = now.isoformat()

        if not id in streams:
            streams[id] = {}
        try: response = RPC.files.get_directory(media="files", directory=path)
        except: continue
        if not 'error' in response:
            if 'files' not in response:
                continue
            files = response["files"]
            for f in files:
                if f["filetype"] == "file":
                    label = remove_formatting(f["label"])
                    file = f["file"]
                    streams[id][file] = label

    f = xbmcvfs.File(file_name,'wb')
    data = json.dumps(streams,indent=2)
    f.write(data)
    f.close()

@plugin.route('/folder_streams')
def folder_streams():
    file_name = 'special://profile/addon_data/plugin.video.pvr.plugin.player/cache.json'
    folders = plugin.get_storage('folders')
    last_read = plugin.get_storage('last_read')
    streams = {}
    f = xbmcvfs.File(file_name,'rb')
    data = f.read()
    f.close()
    if data:
        streams = json.loads(data)

    for folder in folders:
        path = folder
        id = folders[folder]
        now = datetime.datetime.now()
        last_time = last_read.get(folder)
        if last_time:
            try:
                last_time = datetime.datetime.strptime(last_time, '%Y-%m-%dT%H:%M:%S.%f')
            except ValueError:
                last_time = datetime.datetime.strptime(last_time, '%Y-%m-%dT%H:%M:%S')
            hours = int(plugin.get_setting('cache.hours'))
            if last_time > now - datetime.timedelta(hours=hours):
                continue
        last_read[folder] = now.isoformat()

        if not id in streams:
            streams[id] = {}
        try: response = RPC.files.get_directory(media="files", directory=path)
        except: continue
        if not 'error' in response:
            if 'files' not in response:
                continue
            files = response["files"]
            for f in files:
                if f["filetype"] == "file":
                    label = remove_formatting(f["label"])
                    file = f["file"]
                    streams[id][file] = label

    f = xbmcvfs.File(file_name,'wb')
    data = json.dumps(streams,indent=2)
    f.write(data)
    f.close()

    return streams

@plugin.route('/stream_search/<channel>')
def stream_search(channel):
    file_name = 'special://profile/addon_data/plugin.video.pvr.plugin.player/cache.json'
    folders = plugin.get_storage('folders')
    folder_names = plugin.get_storage('folder_names')
    last_read = plugin.get_storage('last_read')
    streams = {}
    f = xbmcvfs.File(file_name,'rb')
    data = f.read()
    f.close()
    if data:
        streams = json.loads(data)

    for folder in folders:
        #log(folder)
        path = folder
        id = folders[folder]
        folder_name = folder_names.get(folder,'')
        now = datetime.datetime.now()
        last_time = last_read.get(folder)
        if last_time:
            try:
                last_time = datetime.datetime.strptime(last_time, '%Y-%m-%dT%H:%M:%S.%f')
            except ValueError:
                last_time = datetime.datetime.strptime(last_time, '%Y-%m-%dT%H:%M:%S')
            except:
                last_time = now
            hours = int(plugin.get_setting('cache.hours'))
            if last_time > now - datetime.timedelta(hours=hours):
                continue
        last_read[folder] = now.isoformat()

        if not id in streams:
            streams[id] = {}
        try: response = RPC.files.get_directory(media="files", directory=path)
        except: continue
        if not 'error' in response:
            if 'files' not in response:
                continue
            files = response["files"]
            for f in files:
                if f["filetype"] == "file":
                    label = remove_formatting(f["label"])
                    file = f["file"]
                    if plugin.get_setting('folder.name') == 'true':
                        streams[id][file] = "%s - %s" % (folder_name,label)
                    else:
                        streams[id][file] = label

    f = xbmcvfs.File(file_name,'wb')
    data = json.dumps(streams,indent=2)
    f.write(data)
    f.close()

    channel_search = channel.decode("utf8").lower().replace(' ','')
    stream_list = []
    for id in sorted(streams):
        files = streams[id]
        for f in sorted(files, key=lambda k: files[k]):
            label = files[f]
            label_search = label.decode("utf8").lower().replace(' ','')
            if label_search in channel_search or channel_search in label_search:
                stream_list.append((id,f,label))
    if plugin.get_setting('folder.name') == 'true':
        labels = ["%s" % (x[2]) for x in stream_list]
    else:
        labels = ["[%s] %s" % (x[0],x[2]) for x in stream_list]

    d = xbmcgui.Dialog()
    which = d.select(channel, labels)
    if which == -1:
        return
    stream_name = stream_list[which][2]
    stream_link = stream_list[which][1]
    plugin.set_resolved_url(stream_link)


@plugin.route('/play_channel/<station>')
def play_channel(station):
    streams = plugin.get_storage('channels')
    if station in streams and streams[station]:
        plugin.set_resolved_url(streams[station])
    else:
        choose_stream(station)

@plugin.route('/alternative_play/<station>')
def alternative_play(station):
    streams = plugin.get_storage('streams')
    if station in streams and streams[station]:
        xbmc.executebuiltin('XBMC.RunPlugin(%s)' % streams[station])
    else:
        choose_stream(station)

@plugin.route('/choose_stream/<station>')
def choose_stream(station):
    station = station.decode("utf8")
    streams = plugin.get_storage('channels')
    d = xbmcgui.Dialog()

    addons = folder_streams()
    addon_labels = ["Guess", "Browse", "Playlist", "PVR", "Favourites", "Clear", "Search"]+sorted(addons)
    addon = d.select("Addon: "+station,addon_labels)
    if addon == -1:
        return
    s = station.lower().replace(' ','')
    sword = s.replace('1','one')
    sword = sword.replace('2','two')
    sword = sword.replace('4','four')
    found_streams = {}
    if addon == 0:
        for a in sorted(addons):
            for f in sorted(addons[a]):
                c = addons[a][f]
                n = c.decode("utf8").lower().replace(' ','')
                if n:
                    label = "[%s] %s" % (a,c)
                    if (s.startswith(n) or n.startswith(s)):
                        found_streams[label] = f
                    elif (sword.startswith(n) or n.startswith(sword)):
                        found_streams[label] = f

        stream_list = sorted(found_streams)
        if stream_list:
            choice = d.select(station,stream_list)
            if choice == -1:
                return
            streams[station] = found_streams[stream_list[choice]]
            plugin.set_resolved_url(streams[station])
    elif addon == 1:
        try:
            response = RPC.addons.get_addons(type="xbmc.addon.video",properties=["name", "thumbnail"])
        except:
            return
        if "addons" not in response:
            return
        found_addons = response["addons"]
        if not found_addons:
            return
        name_ids = sorted([(remove_formatting(a['name']),a['addonid']) for a in found_addons])
        names = [x[0] for x in name_ids]
        selected_addon = d.select("Addon: "+station,names)
        if selected_addon == -1:
            return
        id = name_ids[selected_addon][1]
        path = "plugin://%s" % id
        while True:
            try:
                response = RPC.files.get_directory(media="files", directory=path, properties=["thumbnail"])
            except Exception as detail:
                return
            files = response["files"]
            dirs = sorted([[remove_formatting(f["label"]),f["file"],] for f in files if f["filetype"] == "directory"])
            links = sorted([[remove_formatting(f["label"]),f["file"]] for f in files if f["filetype"] == "file"])
            labels = ["[COLOR blue]%s[/COLOR]" % a[0] for a in dirs] + ["%s" % a[0] for a in links]
            selected = d.select("Addon: "+station,labels)
            if selected == -1:
                return
            if selected < len(dirs):
                dir = dirs[selected]
                path = dir[1]
            else:
                link = links[selected]
                streams[station] = link[1]
                name = link[0]
                plugin.set_resolved_url(streams[station])
    elif addon == 2:
        playlist = d.browse(1, 'Playlist: %s' % station, 'files', '', False, False)
        if not playlist:
            return
        data = xbmcvfs.File(playlist,'rb').read()
        matches = re.findall(r'#EXTINF:.*?,(.*?)\n(.*?)\n',data,flags=(re.DOTALL | re.MULTILINE))
        names = []
        urls =[]
        for name,url in matches:
            names.append(name.strip())
            urls.append(url.strip())
        if names:
            index = d.select("Choose stream: %s" % station,names)
            if index != -1:
                stream = urls[index]
                stream_name = names[index]
                streams[station] = stream
                plugin.set_resolved_url(streams[station])
    elif addon == 3:
        index = 0
        urls = []
        channels = {}
        for group in ["radio","tv"]:
            dirs,files = xbmcvfs.listdir("pvr://channels/%s/" % group)
            all_channels = dirs[0]
            urls = urls + xbmcvfs.listdir("pvr://channels/%s/%s/" % (group,all_channels))[1]
        for group in ["radio","tv"]:
            groupid = "all%s" % group
            json_query = RPC.PVR.get_channels(channelgroupid=groupid, properties=[ "thumbnail", "channeltype", "hidden", "locked", "channel", "lastplayed", "broadcastnow" ] )
            if "channels" in json_query:
                for channel in json_query["channels"]:
                    channelname = channel["label"]
                    streamUrl = urls[index]
                    index = index + 1
                    url = "pvr://channels/%s/%s/%s" % (group,all_channels,streamUrl)
                    channels[channelname] = url
        labels = sorted(channels)
        selected_channel = d.select('PVR: %s' % station,labels)
        if selected_channel == -1:
            return
        stream_name = labels[selected_channel]
        stream = channels[stream_name]
        streams[station] = stream
        plugin.set_resolved_url(streams[station])
    elif addon == 4:
        data = xbmcvfs.File('special://profile/favourites.xml','rb').read()
        matches = re.findall(r'<favourite.*?name="(.*?)".*?>(.*?)<',data,flags=(re.DOTALL | re.MULTILINE))
        favourites = {}
        for name,value in matches:
            if value[0:11] == 'PlayMedia("':
                value = value[11:-2]
            elif value[0:10] == 'PlayMedia(':
                value = value[10:-1]
            elif value[0:22] == 'ActivateWindow(10025,"':
                value = value[22:-9]
            elif value[0:21] == 'ActivateWindow(10025,':
                value = value[22:-8]
            else:
                continue
            value = re.sub('&quot;','',value)
            favourites[name] = unescape(value)
        names = sorted(favourites)
        fav = d.select('PVR: %s' % station,names)
        if fav == -1:
            return
        stream_name = names[fav]
        stream = favourites[stream_name]
        streams[station] = stream
        plugin.set_resolved_url(streams[station])
    elif addon == 5:
        streams[station] = None
        xbmc.executebuiltin("Container.Refresh")
        return
    elif addon == 6:
        streams[station] = plugin.url_for('stream_search',channel=station)
        xbmc.executebuiltin("Container.Refresh")
        return
    else:
        addon_id = addon_labels[addon]
        addon_channels = addons[addon_id]
        label_stream = sorted([[addon_channels[x],x] for x in addon_channels])
        channel_labels = [x[0] for x in label_stream]
        channel = d.select("["+addon_id+"] "+station,channel_labels)
        if channel == -1:
            return
        streams[station] = label_stream[channel][1]
        plugin.set_resolved_url(streams[station])

@plugin.route('/channel_player')
def channel_player():
    channels = plugin.get_storage("channels")

    items = []
    for channel in sorted(channels):
        context_items = []
        context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Choose Stream', 'XBMC.RunPlugin(%s)' % (plugin.url_for(choose_stream, station=channel))))
        context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Add Channel', 'XBMC.RunPlugin(%s)' % (plugin.url_for(add_channel))))
        context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Remove Channel', 'XBMC.RunPlugin(%s)' % (plugin.url_for(remove_this_channel, channel=channel))))
        context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Import Channels', 'XBMC.RunPlugin(%s)' % (plugin.url_for(import_channels))))
        context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Clear Channels', 'XBMC.RunPlugin(%s)' % (plugin.url_for(clear_channels))))

        items.append(
        {
            'label': channel,
            'path': plugin.url_for('play_channel', station=channel),
            'thumbnail':get_icon_path('tv'),
            'is_playable': True,
            'context_menu': context_items,
        })
    return items

@plugin.route('/')
def index():
    items = []

    context_items = []
    context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Clear Folders', 'XBMC.RunPlugin(%s)' % (plugin.url_for(clear))))
    context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Reset Cache', 'XBMC.RunPlugin(%s)' % (plugin.url_for(clear_cache))))
    items.append(
    {
        'label': "Folders",
        'path': plugin.url_for('subscribe'),
        'thumbnail':get_icon_path('tv'),
        'context_menu': context_items,
    })

    context_items = []
    context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Add Channel', 'XBMC.RunPlugin(%s)' % (plugin.url_for(add_channel))))
    context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Remove Channel', 'XBMC.RunPlugin(%s)' % (plugin.url_for(remove_channel))))
    context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Import Channels', 'XBMC.RunPlugin(%s)' % (plugin.url_for(import_channels))))
    context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Export Channels', 'XBMC.RunPlugin(%s)' % (plugin.url_for(export_channels))))
    context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Clear Channels', 'XBMC.RunPlugin(%s)' % (plugin.url_for(clear_channels))))
    context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Make m3u', 'XBMC.RunPlugin(%s)' % (plugin.url_for(make_m3u))))
    items.append(
    {
        'label': "Channels",
        'path': plugin.url_for('channel_player'),
        'thumbnail':get_icon_path('tv'),
        'context_menu': context_items,
    })
    if plugin.get_setting('service.show') == 'true':
        items.append(
        {
            'label': "Service",
            'path': plugin.url_for('service'),
            'thumbnail':get_icon_path('settings'),
            'context_menu': context_items,
        })
    return items

if __name__ == '__main__':
    plugin.run()
    if big_list_view == True:
        view_mode = int(plugin.get_setting('view_mode'))
        plugin.set_view_mode(view_mode)