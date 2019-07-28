#!/usr/bin/python3

# Script to sync watched status between users on Emby
# Author: Adam Palmer <adam@adampalmer.me>
# Credit: https://github.com/faush01/EmbyToolbox/blob/master/WatchedStatusBackup

#config.json should look like:
#{
#    "emby_url":, "http://your.emby.url:8096",
#    "sync_users": [
#        {"username": "USER1", "password": "PASSWORD1"},
#        {"username": "USER2", "password": "PASSWORD2"}
#    ],
#   "playlist_name": "Watching Together"
#}

#EDIT config_file VARIABLE BELOW!
config_file="/home/adam/code/emby/config.json"


import json
import requests
import hashlib
from urllib.parse import quote
from pprint import pprint

def error(msg):
    print(msg)
    quit()

def get_headers(auth_user=None):
    headers = {}
    auth_string = "MediaBrowser Client=\"EmbyBackup\",Device=\"BackupClient\",DeviceId=\"10\",Version=\"1\""
    if auth_user is not None:
        auth_string += ",UserId=\"" + auth_user['user_id'] + "\""
        headers["X-MediaBrowser-Token"] = auth_user["access_token"]
    headers["Accept-encoding"] = "gzip"
    headers["Accept-Charset"] = "UTF-8,*"
    headers["X-Emby-Authorization"] = auth_string
    return headers

def authenticate(base_url, username, password):
    auth_url = base_url + "/Users/AuthenticateByName?format=json"
    hashed_password = hashlib.sha1(password.encode('utf-8')).hexdigest()
    message_data = {}
    message_data["username"] = quote(username)
    message_data["password"] = hashed_password
    message_data["pw"] = quote(password)
    response = requests.post(auth_url, data=message_data, headers=get_headers())
    return response.json()

def get_playlist_id(base_url, auth_user, playlist_name):
    url = base_url + "/emby/Users/" + auth_user['user_id'] + "/Views"
    response = requests.get(url, headers=get_headers(auth_user))
    for item in response.json()['Items']:
        if item['CollectionType'] == 'playlists':
            #foreach item['Id'] which is a playlist ID:
            #url = base_url + "/emby/Users/" + auth_user['user_id'] + "/Items/" + item['Id']
            #response = requests.get(url, headers=get_headers(auth_user))
            #Is this the playlist we're looking for?
            url = base_url + "/emby/Users/" + auth_user['user_id'] + "/Items" + "?SortBy=IsFolder%2CSortName&SortOrder=Ascending&Fields=BasicSyncInfo%2CPrimaryImageAspectRatio%2CProductionYear%2CStatus%2CEndDate&ImageTypeLimit=1&EnableImageTypes=Primary%2CBackdrop%2CThumb&StartIndex=0&ParentId=" + item['Id']
            response = requests.get(url, headers=get_headers(auth_user))
            for i in response.json()['Items']:
                if i['Name'] == playlist_name:
                    return i['Id']
    return None

def get_playlist_items(base_url, auth_user, playlist_id):
    url = base_url + "/emby/Playlists/" + playlist_id + "/Items?Fields=PrimaryImageAspectRatio%2CUserData%2CProductionYear&EnableImageTypes=Primary%2CBackdrop%2CBanner%2CThumb&UserId=" + auth_user['user_id']
    response = requests.get(url, headers=get_headers(auth_user))
    playlistItemIDs = []
    for item in response.json()['Items']:
        playlistItemIDs.append(item['Id'])
    return playlistItemIDs

def get_watched_list(base_url, auth_user):
    url = base_url + "/emby/Users/" + auth_user['user_id'] + "/Items" + "?Recursive=true&Fields=Path,ExternalUrls&IsMissing=False&IncludeItemTypes=Movie,Episode&ImageTypeLimit=0"
    response = requests.get(url, headers=get_headers(auth_user))
    return response.json()

def set_watched_list(base_url, auth_user, sync_played, sync_ticks):
    posts = []
    for s in sync_played: #(Id, Played, PlaybackPositionTicks)
        url = base_url + "/emby/Users/" + auth_user['user_id'] + "/PlayedItems/" + s[0]
        data = {"Played": s[1], "PlaybackPositionTicks": s[2]}
        requests.post(url, headers=get_headers(auth_user), json=data)
        posts.append( (url, data) )
    for s in sync_ticks: #(Id, Played, PlaybackPositionTicks)
        url = base_url + "/emby/Sessions/Playing/Progress"
        data = {"PositionTicks": s[2],"ItemId": s[0],"EventName":"timeupdate"}
        requests.post(url, headers=get_headers(auth_user), json=data)
        posts.append( (url, data) )
    return posts

#Main code block
#Load the config
with open(config_file, "r") as cf:
    config = json.load(cf)

auths = []
#Authenticate each user and get an AccessToken back from the server
for user in config['sync_users']:
    user_auth = authenticate(config['emby_url'], user['username'], user['password'])
    auths.append( {"username": user['username'], "access_token": user_auth['AccessToken'], "user_id": user_auth['User']['Id']} )

#Using the first user, get a list of all playlists
playlistId = get_playlist_id(config['emby_url'], auths[0], config['playlist_name'])
if playlistId is None:
    error("Couldn't find playlist")
playlistItemIDs = get_playlist_items(config['emby_url'], auths[0], playlistId)

#Next, get the user's watched/watching list:
user_watched_list = {}
for auth_user in auths:
    user_watched_list.update({auth_user['user_id'] : {}})
    watched_list = get_watched_list(config['emby_url'], auth_user)
    for item in watched_list['Items']: #Is this something we're watching together?
        if item['Id'] in playlistItemIDs:
            if item['UserData']['Played'] is False and item['UserData']['PlaybackPositionTicks'] is not 0:
                user_watched_list[auth_user['user_id']].update( {item['Id']: (item['UserData']['Played'], item['UserData']['PlaybackPositionTicks'])} )
            if item['UserData']['Played'] is True:
                user_watched_list[auth_user['user_id']].update( {item['Id']: (item['UserData']['Played'], item['UserData']['PlaybackPositionTicks'])} )

#Now find the differences between watched lists that need syncing:
to_sync = {} #dict of {user_id: {..., }
for user in auths: #prebuild list of user ids
    to_sync.update({user['user_id']: user})
    to_sync[user['user_id']].update({'sync_played':[], 'sync_ticks':[]})

for user_id in user_watched_list:
    user_watched_ids = user_watched_list[user_id].keys()  #get the id of everything on that user's watch list
    other_user_ids = set(user_watched_list.keys()) - set([user_id]) #get a list of all users other than this one
    for other_user_id in other_user_ids: #for every other user
        other_user_watched_ids = user_watched_list[other_user_id].keys() #get a list of the other user's watched stuff
        #for each item in user_id's list:
        for item in user_watched_list[user_id]:
            if item not in user_watched_list[other_user_id]: #if the item is not in the other user's list then:
                if user_watched_list[user_id][item][0] is True: #we finished it
                    to_sync[other_user_id]['sync_played'].append((item,) + user_watched_list[user_id][item]) #add to other user's sync list
                else:
                    if int(item[1]) > 0: #ticks > 0. we didn't finish it
                        to_sync[other_user_id]['sync_ticks'].append((item,) + user_watched_list[user_id][item]) #add to other user's sync list
            else: #if it is, then:
                if user_watched_list[other_user_id][item][0] is False: #if other_user_id did not finish it
                    if user_watched_list[user_id][item][0] is True: #if user did finish it
                        to_sync[other_user_id]['sync_played'].append((item,) + user_watched_list[user_id][item]) #add to other user's sync list
                    else: #neither user finished it
                        if int(user_watched_list[user_id][item][1]) > int(user_watched_list[other_user_id][item][1]): #If user is further ahead in the item than other user
                            to_sync[other_user_id]['sync_ticks'].append((item,) + user_watched_list[user_id][item]) #add to other user's sync list
#Now sync to_sync.
for user in to_sync:
    posts = set_watched_list(config['emby_url'], to_sync[user], to_sync[user]['sync_played'], to_sync[user]['sync_ticks'])
    pprint(posts)
