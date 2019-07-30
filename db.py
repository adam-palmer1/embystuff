import sqlite3
import os

def connect(db_file):
    if os.path.isfile(db_file):
        con = sqlite3.connect(db_file)
    else:
        con = sqlite3.connect(db_file)
        watched_history_sql = """
        CREATE TABLE watched_history (
            id integer PRIMARY KEY,
            ItemId unsigned long long NOT NULL,
            UserId varchar NOT NULL,
            Played varchar NOT NULL,
            PlaybackPositionTicks integer NOT NULL,
            updatedWhen TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
        """
        cur = con.cursor()
        cur.execute(watched_history_sql)
    return con

def set(con, user_id, item_id, played, playbackpositionticks):
    #Delete any older reference to this ItemId
    cur = con.cursor()
    sql = "DELETE FROM watched_history WHERE ItemId = " + str(item_id) + ";"
    cur.execute(sql)
    sql = "INSERT INTO watched_history (ItemID, UserId, Played, PlaybackPositionTicks) VALUES ('" + str(item_id) +  "', '" + str(user_id) + "', '"+ str(played) + "', "+ str(playbackpositionticks) + ");"
    cur.execute(sql)

def get(con, item_id, user_id=None):
    cur = con.cursor()
    sql = "SELECT UserId, Played, PlaybackPositionTicks FROM watched_history WHERE ItemId = " + str(item_id)
    if user_id is not None:
        sql += " AND user_id ='" + str(user_id) + "'"
    res = cur.execute(sql)
    return cur.fetchone() #(UserId, Played, PlaybackPositionTicks)

def get_all(con):
    cur = con.cursor()
    sql = "SELECT ItemId FROM watched_history;"
    res = cur.execute(sql)
    return [str(i[0]) for i in cur.fetchall()]

def save(con):
    con.commit()
