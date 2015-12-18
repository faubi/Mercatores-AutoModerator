import datetime, util

def setup(db):
    cursor = db.cursor()
    create_schema(cursor)
    init_values(cursor)
    cursor.execute('INSERT INTO globals DEFAULT VALUES')
    cursor.execute('UPDATE globals SET forum_username=?', (input('Enter forum username: '),))
    cursor.execute('UPDATE globals SET forum_password=?', (input('Enter forum password: '),))
    cursor.execute('UPDATE globals SET thread_id=?', (int(input('Enter thread_id: ')),))
    cursor.execute('UPDATE globals SET last_turn_date=?', (datetime.datetime.now().isoformat(),))
    cursor.execute('UPDATE globals SET turn_number=1')
    cursor.execute('UPDATE globals SET success_point=0')
    print('Setup successful')
    
def create_schema(cursor):
    with open('schema.sql') as schema_file:
        cursor.executescript(schema_file.read())
        
def init_values(cursor):
    with open('values.sql') as values_file:
        cursor.executescript(values_file.read())
    
def reset_db(db):
    cursor = db.cursor()
    cursor.execute('SELECT name FROM sqlite_master WHERE type = "table"')
    tables = cursor.fetchall()
    for table in tables:
        name = table['name']
        if name in ('globals', 'turn_changes'):
            continue
        cursor.execute('DELETE FROM {0}'.format(name))
    init_values(cursor)
    util.set_last_turn_date(cursor, util.get_deadline(cursor)-datetime.timedelta(
        days=util.get_param(cursor, 'days_per_turn')*util.get_global(cursor, 'turn_number')))
    cursor.execute('UPDATE globals SET turn_number=1')
    
    