# embystuff
Emby Tools
sync_watched.py: When you have multiple users that all watch stuff together on one of their devices and you want to sync their watched statuses between accounts. 
Just add any media to a custom playlist that multiple people watch together and define that playlist in config.json.

sqlite3 db will allow newest changes to be synced every time so if user1 marks an item as watched and then user2 marks it as unwatched, user2 will override.

config.json should look like:
```{
    "emby_url":, "http://your.emby.url:8096",
    "sync_users": [
        {"username": "USER1", "password": "PASSWORD1"},
        {"username": "USER2", "password": "PASSWORD2"}
    ],
   "playlist_name": "Watching Together"
   "db": "/path/to/database.db"
}
```
