import pymysql

def get_connection():
    return pymysql.connect(
        host="localhost",
        user="root",
        password='Sruti#2004',
        database="library_dbms",
        cursorclass=pymysql.cursors.DictCursor
    )