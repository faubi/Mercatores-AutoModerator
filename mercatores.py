#!/usr/bin/python3
import sqlite3, argparse, sys, os, traceback
import main, setup

argparser = argparse.ArgumentParser(description='Mercatores Automod')
argparser.add_argument('--db-path', default='game.db', help='Path to database file')
argparser.add_argument('--setup', action='store_true', help='Set up database instead of running')
argparser.add_argument('-q', '--quiet', action='store_true', help='Don\'t log messages. Doesn\'t apply to --setup')
argparser.add_argument('--force-new-turn', action='store_true', help='Force a new turn instead of checking the thread')
argparser.add_argument('--reset', action='store_true', help='Reset database and rerun from beginning')
argparser.add_argument('--set-success', type=int, default=0, help='Set the post number before which responses won\'t be posted')
args = argparser.parse_args()
    
if args.quiet:
    log = lambda x:None
else:
    log = print

if not (args.setup or os.path.exists(args.db_path)):
    sys.exit('Game database not found')
    
try:
    db = sqlite3.connect(args.db_path)
    db.row_factory = sqlite3.Row
except sqlite3.OperationalError as error:
    sys.exit('Sqlite3 error: {0}'.format(error))
    
log('Connected to database')
    
try:
    if args.setup:
        setup.setup(db)
    elif args.force_new_turn:
        main.do_new_turn(db.cursor(), log)
    elif args.reset:
        setup.reset_db(db)
    elif args.set_success:
        main.set_success_point(db.cursor(), args.set_success)
    else:
        main.main(db, log)
except Exception as e:
    print('Error: {0}'.format(traceback.format_exc()))
finally:
    db.commit()
    db.close()