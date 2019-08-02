#!/usr/bin/python3

# Script to sync watched status between users on Emby
# Author: Adam Palmer <adam@adampalmer.me>
# Credit: https://github.com/faush01/EmbyToolbox/blob/master/WatchedStatusBackup

#EDIT config_file VARIABLE BELOW!
config_file="/home/adam/code/emby/config.json"


import json
import requests
import hashlib
from urllib.parse import quote
from datetime import datetime
import db
from pprint import pprint

def do_log(l):
    now = datetime.now()
    print("[%s] %s" % (now.strftime("%Y-%m-%d %H:%M:%S"), l))

def error(msg):
    do_log(msg)
    quit()

def str2bool(s):
    return str(s).lower() in ("yes", "true", "t", "1")


def get_headers(auth_user=None):
    headers = {}
    auth_string = "MediaBrowser Client=\"EmbyWatchedSync\",Device=\"WatchedSync\",DeviceId=\"10\",Version=\"1\""
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

def get_collection_id(base_url, auth_user, collection_name):
    url = base_url + "/emby/Users/" + auth_user['user_id'] + "/Items"
    response = requests.get(url, headers=get_headers(auth_user))
    for item in response.json()['Items']:
        if item['Name'] == 'Collections':
            #Is this the collection we're looking for?
            url = base_url + "/emby/Users/" + auth_user['user_id'] + "/Items" + "?SortBy=IsFolder%2CSortName&SortOrder=Ascending&Fields=BasicSyncInfo%2CPrimaryImageAspectRatio%2CProductionYear%2CStatus%2CEndDate&ImageTypeLimit=1&EnableImageTypes=Primary%2CBackdrop%2CThumb&StartIndex=0&ParentId=" + item['Id']
            response = requests.get(url, headers=get_headers(auth_user))
            for i in response.json()['Items']:
                if i['Name'] == collection_name:
                    return i['Id']
    return None

def get_collection_items(base_url, auth_user, collection_id, collectionItemIDs):
    url = base_url + "/emby/Users/" + auth_user['user_id'] + "/Items?ParentId=" + collection_id + "&Fields=PrimaryImageAspectRatio%2CBasicSyncInfo%2CCanDelete%2CProductionYear%2CPremiereDate&EnableTotalRecordCount=false"
    response = requests.get(url, headers=get_headers(auth_user))
    for item in response.json()['Items']:
        if item['IsFolder'] is True:
            #recurse with this new folder
            get_collection_items(base_url, auth_user, item['Id'], collectionItemIDs)
        else:
            collectionItemIDs.append(item['Id'])

def get_watched_list(base_url, auth_user):
    url = base_url + "/emby/Users/" + auth_user['user_id'] + "/Items" + "?Recursive=true&Fields=Path,ExternalUrls&IsMissing=False&IncludeItemTypes=Movie,Episode&ImageTypeLimit=0"
    response = requests.get(url, headers=get_headers(auth_user))
    return response.json()

def _watched_list_played(base_url, auth_user, item, played, ticks):
    url = base_url + "/emby/Users/" + auth_user['user_id'] + "/PlayedItems/" + item
    data = {"Played": played, "PlaybackPositionTicks": ticks}
    requests.post(url, headers=get_headers(auth_user), json=data)
    return (url, data)

def _watched_list_unplayed(base_url, auth_user, item, played, ticks):
    url = base_url + "/emby/Users/" + auth_user['user_id'] + "/PlayedItems/" + item
    data = {"Played": played, "PlaybackPositionTicks": ticks}
    requests.delete(url, headers=get_headers(auth_user), json=data)
    return (url, data)

def _watched_list_ticks(base_url, auth_user, item, played, ticks):
    url = base_url + "/emby/Users/" + auth_user['user_id'] + "/PlayingItems/" + item
    data = {"PositionTicks": ticks}
    requests.delete(url, headers=get_headers(auth_user), json=data)
    return (url, data)

def set_watched_list(base_url, auth_user, con):
    posts = []
    #this was refactored and became a bit of a mess. s[0] is itemid, s[1] is true/false for watched and s[2] is ticks.
    #the return of the _function (url, data) is added to (s[3], post_type) for logging purposes. s[3] is a debug value
    #that was added in the calculate_sync_list function to determine where/why an item was added.

    seen_items = []
    for post_type in ['sync_played', 'sync_unplayed', 'sync_ticks']:
        for s in auth_user[post_type]:
            if s[0] in seen_items: #Don't allow dups
                break
            seen_items.append(s[0])
            if post_type == 'sync_played':
                posts.append( _watched_list_played(base_url, auth_user, s[0], s[1], s[2]) + (auth_user['user_id'], s[3], post_type) )
            elif post_type == 'sync_ticks':
                posts.append( _watched_list_ticks(base_url, auth_user, s[0], s[1], s[2]) + (auth_user['user_id'], s[3], post_type) )
            elif post_type == 'sync_unplayed':
                posts.append( _watched_list_unplayed(base_url, auth_user, s[0], s[1], s[2]) + (auth_user['user_id'], s[3], post_type) )
                posts.append( _watched_list_ticks(base_url, auth_user, s[0], s[1], s[2]) + (auth_user['user_id'], s[3], post_type) )
            db.set(con, auth_user['user_id'], s[0], s[1], s[2])
    db.save(con)
    return posts

def calculate_sync_list(user_watched_list, collectionItemIDs, con):
    #Get a list of everyhting that the database has seen before
    db_seen = db.get_all(con)

    #Now find the differences between watched lists that need syncing:
    to_sync = {} #dict of {user_id: {..., }
    for user in auths: #prebuild list of user ids
        to_sync.update({user['user_id']: user})
        to_sync[user['user_id']].update({'sync_played':[], 'sync_unplayed':[], 'sync_ticks':[]})

    for user_id in user_watched_list:
        user_watched_ids = user_watched_list[user_id].keys()  #get the id of everything on that user's watch list
        other_user_ids = set(user_watched_list.keys()) - set([user_id]) #get a list of all users other than this one
        for other_user_id in other_user_ids: #for every other user
            other_user_watched_ids = user_watched_list[other_user_id].keys() #get a list of the other user's watched stuff
            #for each item in user_id's list:
            for item in user_watched_list[user_id]:
                in_db = False
                item_added = False
                if item in db_seen: #We've seen this item before in the DB, we'll have to use default rules:
                    #if we get here, item will always be in all users watch lists
                    (db_user_id, db_watched, db_ticks) = db.get(con, item) #we've seen this item before, so different rules apply:
                    in_db = True
                if item not in user_watched_list[other_user_id]: #if the item is not in the other user's list then:
                    if in_db is True and str2bool(db_watched) is True:
                        #it's watched in the DB. It's watched on our list, but not on the other users. So other user has unwatched it.
                        to_sync[user_id]['sync_unplayed'].append((item,) + user_watched_list[user_id][item] + (1,))
                        item_added = True
                    elif user_watched_list[user_id][item][0] is True: #we finished it
                        to_sync[other_user_id]['sync_played'].append((item,) + user_watched_list[user_id][item] + (8,)) #add to other user's sync list
                        item_added = True
                    else:
                        if int(user_watched_list[user_id][item][1]) > 0: #ticks > 0. we didn't finish it
                            to_sync[other_user_id]['sync_ticks'].append((item,) + user_watched_list[user_id][item] + (2,)) #add to other user's sync list
                            item_added = True
                else: #if it is, then:
                    if item in db_seen: #If it's in the DB, e.g. we've seen it and synced it before
                        #if anyone has different to what's synced and in the DB, then defer to them
                        if str2bool(user_watched_list[other_user_id][item][0]) is not str2bool(db_watched):
                            if str2bool(user_watched_list[other_user_id][item][0]) is False:
                                #DB says it's watched, other user says it isn't. Trust other user
                                to_sync[user_id]['sync_unplayed'].append((item,) + user_watched_list[other_user_id][item] + (3,)) #this syncs ticks too
                                item_added = True
                            else: #DB says it's unwatched, user says it's watched
                                to_sync[user_id]['sync_played'].append((item,) + user_watched_list[other_user_id][item] + (4,))
                                item_added = True
                        if user_watched_list[other_user_id][item][1] != user_watched_list[user_id][item][1]: #if users disagree over ticks.
                            #Go with whoever doesn't agree with the DB
                            if user_watched_list[other_user_id][item][1] == db_ticks:
                                to_sync[other_user_id]['sync_ticks'].append((item,) + user_watched_list[user_id][item] + (5,)) #sync from the disagreeing user
                                item_added = True
                            elif user_watched_list[user_id][item][1] == db_ticks:
                                to_sync[user_id]['sync_ticks'].append((item,) + user_watched_list[other_user_id][item] + (9,)) #sync from the disagreeing user
                                item_added = True
                            else: #everyone disagrees, DB included. Go with whichever is greater. 
                                if int(user_watched_list[user_id][item][1]) > int(user_watched_list[other_user_id][item][1]):
                                    to_sync[other_user_id]['sync_ticks'].append((item,) + user_watched_list[user_id][item] + (10,))
                                    item_added = True
                                else:
                                    to_sync[user_id]['sync_ticks'].append((item,) + user_watched_list[other_user_id][item] + (11,))
                                    item_added = True
                    else:
                        if user_watched_list[other_user_id][item][0] is False: #if other_user_id did not finish it
                            if user_watched_list[user_id][item][0] is True: #if user did finish it
                                to_sync[other_user_id]['sync_played'].append((item,) + user_watched_list[user_id][item] + (6,)) #add to other user's sync list
                                item_added = True
                            else: #neither user finished it
                                if int(user_watched_list[user_id][item][1]) > int(user_watched_list[other_user_id][item][1]): #If user is further ahead in the item than other user
                                    to_sync[other_user_id]['sync_ticks'].append((item,) + user_watched_list[user_id][item] + (7,)) #add to other user's sync list
                                    item_added = True
                #end of `for item`
                if item_added is False: #This item isn't being synced as it's already synced between users
                    if item not in db_seen: #This item isn't in the database either
                        #db.set(con, user_id, item_id, played, playbackpositionticks):
                        db.set(con, user_id, item, str(user_watched_list[user_id][item][0]), user_watched_list[other_user_id][item][1])
                        db_seen.append(item)
    return to_sync

#Main code block
#Load the config
with open(config_file, "r") as cf:
    config = json.load(cf)

#Connect to the database
con = db.connect(config['db'])

auths = []
#Authenticate each user and get an AccessToken back from the server
for user in config['sync_users']:
    user_auth = authenticate(config['emby_url'], user['username'], user['password'])
    auths.append( {"username": user['username'], "access_token": user_auth['AccessToken'], "user_id": user_auth['User']['Id']} )

#Using the first user, get a list of all collections
collectionId = get_collection_id(config['emby_url'], auths[0], config['collection_name'])
if collectionId is None:
    error("Couldn't find collection")
collectionItemIDs = []
get_collection_items(config['emby_url'], auths[0], collectionId, collectionItemIDs)

#Next, get the user's watched/watching list:
user_watched_list = {}
for auth_user in auths:
    user_watched_list.update({auth_user['user_id'] : {}})
    watched_list = get_watched_list(config['emby_url'], auth_user)
    for item in watched_list['Items']: #Is this something we're watching together?
        if item['Id'] in collectionItemIDs:
            if item['UserData']['Played'] is False and item['UserData']['PlaybackPositionTicks'] is not 0:
                user_watched_list[auth_user['user_id']].update( {item['Id']: (item['UserData']['Played'], item['UserData']['PlaybackPositionTicks'])} )
            if item['UserData']['Played'] is True:
                user_watched_list[auth_user['user_id']].update( {item['Id']: (item['UserData']['Played'], item['UserData']['PlaybackPositionTicks'])} )

to_sync = calculate_sync_list(user_watched_list, collectionItemIDs, con)

#Now sync to_sync.
for user in to_sync:
    posts = set_watched_list(config['emby_url'], to_sync[user], con)
    if posts != []:
        do_log(posts)
db.save(con)
