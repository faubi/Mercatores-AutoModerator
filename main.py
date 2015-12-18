import datetime, re, traceback, random
import phpbblib, util
from actions import get_actions
    
class MessageQueue:
    
    def __init__(self, queue, action, player):
        self.queue = queue
        self.action = action
        self.player = player
        
    def append(self, message):
        self.queue.append(message)
        
    def quote(self, message):
        self.queue.append('[quote="{0}"][b]{1}[/b][/quote]{2}\n'.format(self.player, self.action, message))

def main(db, log):
    with open('/tmp/merca', 'w') as merca:
        pass
    cursor = db.cursor()
    
    log('Logging into forum')
    
    forum = phpbblib.Forum('http://forums.xkcd.com')
    username = util.get_global(cursor, 'forum_username')
    password = util.get_global(cursor, 'forum_password')
    forum.login(username, password)
    
    log('Login successful')

    thread = forum.get_thread(util.get_global(cursor, 'thread_id'))
    
    message_queue = []
    
    last_post_count = util.get_post_count(cursor)
    
    log('Checking for new posts')
    
    success_point = util.get_global(cursor, 'success_point')
    
    if thread.post_count > last_post_count:
        actions = get_actions(cursor)
        log('Beginning post loop')
        posts = thread.get_posts(last_post_count)
        post_number = last_post_count
        for post in posts:
            if post.author.casefold() != username.casefold() and post_number != 0:
                log('Handling post {0}'.format(post_number))
                action_spans = [span for span in post.content_html.find_all('span') if span.has_attr('style') and 'font-weight: bold' in span['style']]
                action_lines = []
                for span in action_spans:
                    action_lines += [line.strip() for line in span.strings if not re.match(r'^\s*$', line)]
                log('Found {0} actions in post'.format(len(action_lines)))
                for line in action_lines:
                    linequeue = MessageQueue(message_queue, line, post.author)
                    found_match = False
                    for regex, function in actions:
                        match = regex.match(line)
                        if match:
                            found_match = True
                            try:
                                successful = function(linequeue, post.author, **match.groupdict())
                            except Exception as e:
                                linequeue.quote('An exception occured while processing this action:[code]{0}[/code]'.format(traceback.format_exc(chain=False)))
                                successful = False
                            break
                    if not found_match:
                        linequeue.quote('I can\'t understand this. Did you misspell something or submit an invalid action? ')
                        sucessful = False
                    if not successful:
                        message_queue.append('The rest of the actions in [url={0}]{1}\'s post[/url] have been skipped due to this error.'.format(post.url, post.author))
                        break
            cursor.execute('INSERT INTO posts VALUES (?, ?, ?)', (post_number, post.author, str(post.content_html)))
            if success_point and post_number < success_point:
                message_queue = []
            post_number += 1
            turn_change = util.select(cursor, 'turn_changes', post_number=post_number)
            if turn_change:
                do_new_turn(cursor, log)
                try:
                    message_queue.extend(game_state_post(cursor))
                except Exception as e:
                    message_queue.append('An exception occurred while generating the game state summary:[code]{0}[/code]'.format(traceback.format_exc(chain=False)))
    
    def make_posts(messages):    
        character_limit = 10000
        current_post = ''
                
        for message in message_queue:
            new_length = len(message) + len(current_post)
            if current_post != '':
                new_length += 1
            if new_length > character_limit:
                thread.make_post(current_post)
                current_post = ''
            if current_post != '':
                current_post += '\n'
            current_post += message
        thread.make_post(current_post)
        
    log('Checking for new turn')
    new_turn = util.check_new_turn(cursor)
        
    
    if message_queue:
        log('Posting updates')
        try:
            message_queue.extend(game_state_post(cursor))
        except Exception as e:
            message_queue.append('An exception occurred while generating the game state summary:[code]{0}[/code]'.format(traceback.format_exc(chain=False)))
        make_posts(message_queue)
    
    if new_turn:
        log('Updating turn')
        messages = ['[size=200]Turn {0} Begins[/size]\n'.format(turn_number)]
        try:
            do_new_turn(cursor)
        except Exception as e:
            message_queue.append('An exception occurred while handling the turn transition:[code]{0}[/code]'.format(traceback.format_exc(chain=False)))
        else:
            messages.extend(game_state_post(cursor))
        log('Posting new turn')
        make_posts(messages)
        
    log('Cleaning up and logging out')
    util.cleanup(cursor)
    forum.logout()
    
def do_new_turn(cursor, log):
    cursor.execute('INSERT INTO turn_changes (post_number) VALUES (?)', (util.get_post_count(),))
    cursor.execute('UPDATE players SET phase=1 WHERE phase=2')
    cursor.execute('DELETE FROM offers')
    cursor.execute('UPDATE globals SET turn_number=turn_number+1')
    util.update_last_turn_date(cursor)
    turn_number = util.get_global(cursor, 'turn_number')
    #TODO loan defaults
    cursor.execute('DELETE FROM price_changes WHERE ends <=?', (turn_number,))
    cursor.execute('DELETE FROM current_events WHERE ends <=?', (turn_number,))
    #cursor.execute('INSERT INTO current_events (myth_power_id, ends) SELECT myth_power_id, ends FROM queued_events WHERE starts <=?', (turn_number,))
    #cursor.execute('DELETE FROM queued_events WHERE starts <=?', (turn_number,))
    # TODO apply current events
    queued_events = util.select(cursor, 'queued_events', starts=turn_number)
    for queued_event in queued_events:
        cursor.execute('DELETE FROM queued_events WHERE id=?', (queued_event['id'],))
        event = util.select(cursor, 'events', id=queued_event['event_id'])
        if event['type'] == 0:
            # Give items event
            player_id = util.select(cursor, 'give_items_event_players', queued_event_id=queued_event['id'])['player_id']
            cursor.execute('DELETE FROM give_items_event_players WHERE queued_event_id=?' (queued_event['id'],))
            cursor.execute('SELECT item_id, quantity FROM give_items_event_items WHERE event_id=? ORDER BY priority', (event['id'],))
            items = cursor.fetchall()
            for item_id, quantity in items:
                free_capacity = util.get_free_capacity(cursor, player_id)
                item_capacity = select('items', id=item_id)['capacity']
                if free_capacity < item_capacity:
                    break
                quantity = min(free_capacity//item_capacity, quantity)
                util.give_items(cursor, player_id, item_id, quantity)
        #if event['type'] in (1, 2):
            #Price change event
            #price_change = util.select(cursor, 'price_change_events', event_id=event['id'])
            #ends = turn_number + price_change['duration']
            #if event['type'] == 1:
                # Region price change
                #region_id = util.select(cursor, 'price_change_event_regions', queued_event_id=queued_event['id'])['region_id']
                #for item in util.select_all(cursor, 'items'):
                    #cursor.execute('INSERT INTO price_changes (region_id, item_id, buy_change, sell_change, ends) VALUES (?, ?, ?, ?, ?)',
                        #(region_id, item['id'], price_change['buy_change'], price_change['sell_change'], ends))
        elif event['type'] == 1:
            cursor.execute(
                """INSERT INTO price_changes (region_id, item_id, buy_change, sell_change, ends)
                SELECT pcer.region_id, items.id, pce.buy_change, pce.sell_change, pce.duration+globals.turn_number
                FROM price_change_events AS pce JOIN price_change_event_regions AS pcer JOIN items JOIN globals
                WHERE pce.event_id=? AND pcer.queued_event_id=?""",
                (event['id'], queued_event['id']))
            cursor.execute('DELETE FROM price_change_event_regions WHERE queued_event_id=?', (queued_event['id'],))
        elif event['type'] == 2:
            cursor.execute(
                """INSERT INTO price_changes (region_id, item_id, buy_change, sell_change, ends)
                SELECT regions.id, pcei.item_id, pce.buy_change, pce.sell_change, pce.duration+globals.turn_number
                FROM price_change_events AS pce JOIN price_change_event_items AS pcei JOIN regions JOIN globals
                WHERE pce.event_id=? AND pcei.event_id=?""",
                (event['id'], event['id']))
        if event['type'] == 1 or event['type'] == 2:
            cursor.execute(
                """INSERT INTO current_events (message, ends) SELECT ?, pce.duration+globals.turn_number
                FROM price_change_events AS pce JOIN globals
                WHERE pce.event_id=?""", (queued_event['message'], event['id']))
    cursor.execute('DELETE FROM unused_myth')
    cursor.execute('DELETE FROM available_myth')
    gods = util.select_all(cursor, 'gods')
    for god in gods:
        myth_powers = util.select_all(cursor, 'myth_powers', god_id=god['id'])
        if myth_powers:
            cursor.execute('INSERT INTO available_myth (myth_power_id, purchased) SELECT ?, 0', (random.choice(myth_powers)['id'],))
        
    
def game_state_post(cursor):
    section = lambda title, message:'[u]{0}[/u][spoiler]{1}[/spoiler]'.format(title, message or 'There is nothing here')
    section_list = lambda title, elements:section(title, util.bbcode_list(elements))
    messages = ['\n\n[size=150]Current Game State[/size]']
    #Turn, Deadline
    turn_number = util.get_global(cursor, 'turn_number')
    deadline = util.get_deadline(cursor)
    time_left = deadline - datetime.datetime.now()
    messages.append('[b]Turn {0}. Deadline in {1} days, {2} hours, {3} minutes[/b]'.format(turn_number, time_left.days, time_left.seconds//3600, time_left.seconds%3600//60))
    #Player Offices
    players = util.select_all(cursor, 'players')
    player_offices = []
    for player in players:
        offices = util.select_all(cursor, 'offices', player_id=player['id'])
        office_text = []
        for office in offices:
            region_name = util.select(cursor, 'regions', id=office['region_id'])['name']
            for _ in range(office['quantity']):
                office_text.append('{0} (level {1})'.format(region_name, office['level']))
        player_offices.append('{0}: {1}. Total Capacity: {2}'.format(player['name'], ', '.join(office_text), 
            util.get_total_capacity(cursor, player['id'])))
    messages.append(section_list('Player offices', player_offices))
    #Player Resources
    player_resources = []
    for player in players:
        items = util.select_all(cursor, 'inventories', player_id=player['id'])
        player_resources.append('{0}: {1}'.format(player['name'], util.format_items(cursor, items)))
    messages.append(section_list('Player resources', player_resources))
    #Items Offered to Gods
    player_myth = []
    gods = util.select_all(cursor, 'gods')
    for player in players:
        god_items = []
        for god in gods:
            myth_items = util.select_all(cursor, 'myth_offered', player_id=player['id'], god_id=god['id'])
            if myth_items:
                god_items.append('{0} to {1}'.format(god['name'], util.format_items(cursor, myth_items)))
        player_myth.append('{0}: {1}'.format(player['name'], ', '.join(god_items)))
    messages.append(section_list('Offered to gods', player_myth))
    #Open Offers
    offers = util.select_all(cursor, 'offers')
    offers_list = []
    for offer in offers:
        offerer = util.select(cursor, 'players', id=offer['offerer'])
        offeree = util.select(cursor, 'players', id=offer['offeree'])
        cursor.execute('SELECT item_id, quantity FROM offer_items WHERE offer_id=? AND quantity > 0', (offer['id'],))
        offerer_items = util.format_items(cursor, cursor.fetchall())
        cursor.execute('SELECT item_id, -quantity FROM offer_items WHERE offer_id=? AND quantity < 0', (offer['id'],))
        offeree_items = util.format_items(cursor, cursor.fetchall())
        offers_list.append('{0}:[list]\n{1}: {2}\n{3}: {4}[/list]'.format(
            offer['name'], offerer['name'], offerer_items, offeree['name'], offeree_items))
    messages.append(section_list('Open offers', offers_list))
    #Loans
    for title, accepted in (('Offered', 0),('Active', 1)):
        loans = util.select_all(cursor, 'loans', accepted=0)
        loans_list = []
        for loan in loans:
            offerer = util.select(cursor, 'players', id=loan['offerer'])
            offeree = util.select(cursor, 'players', id=loan['offeree'])        
            loans_list.append('{0}:[list]{1} to {2}: {3} coins, {4} interest, due turn {5}'.format(
                loan['name'], offerer['name'], offeree['name'], loan['coins'], loan['interest'], loan['due_by']))
        messages.append(section_list(title+' Loans', loans_list))
    if turn_number >= util.get_param(cursor, 'myth_powers_start'):
        #Available Myth Powers
        myth_powers = []
        for god in gods:
            myth_power = util.get_current_power(cursor, god['id'])
            if myth_power:
                power_price = util.select_all(cursor, 'myth_power_prices', myth_power_id=myth_power['id'])
                power_text = '{0}: {1} ({2}): {3}'.format(god['name'], myth_power['name'], util.format_items(cursor, power_price), myth_power['description'])
                if myth_power['purchased']:
                    power_text = '[s]' + power_text + '[/s]'
                myth_powers,append(power_text)
        messages.append(section_list('Current Myth Powers', myth_powers))
        #Current Events
        events = util.select_all(cursor, 'current_events')
        messages.append(section_list('Current Events', (event['message'] for event in events)))
        #Queued Events
        queued_events = util.select_all(cursor, 'queued_events')
        turns = sorted(set(event['starts'] for event in queued_events))
        events_list = []
        for turn in turns:
            events_list.append(util.bbcode_list(event['message'] for event in queued_events if event['starts'] == turn))
        messages.append(section_list('Future Events', events_list))
    #Current Prices
    for title, price_function in (('Current Prices', util.get_price), ('Standard Prices', util.get_base_price)):
        buyable_items = util.select_all(cursor, 'items', buyable=1)
        regions = util.select_all(cursor, 'regions')
        table_items = [buyable_items[i:i+8] for i in range(0, len(buyable_items), 8)]
        table_text = ''
        for item_row in table_items:
            table = []
            table.append(['Sell to / Buy from'] + [item['name'] for item in item_row])
            for region in regions:
                table_row = [region['name']]
                for item in item_row:
                    table_row.append('{0}/{1}'.format(*(util.get_price(cursor, region['id'], item['id'], buying) for buying in (1,0))))
                table.append(table_row)
            table_text += '[code]' + util.text_table(table, dividers=(1, 1, 2)) + '[/code]'
        messages.append(section(title, table_text))
    #Office Prices
    office_prices = []
    for region in regions:
        price = util.get_office_price(cursor, region['id'])
        office_prices.append('{0}: {1} coins'.format(region['name'], price))
    messages.append(section_list('Office Prices', office_prices))
    #Upgrade Prices
    upgrade_prices = []
    cursor.execute('SELECT MAX(level) FROM office_levels')
    max_level = cursor.fetchone()[0]
    for level in range(2, max_level+1):
        upgrade_price = util.select_all(cursor, 'upgrade_prices', level=level)
        upgrade_prices.append('Upgrade to level {0}: {1}'.format(level, util.format_items(cursor, upgrade_price)))
    messages.append(section_list('Office Upgrade Prices', upgrade_prices))
    #Unused Myth
    unused_myth_list = []
    for player in players:
        powers = util.select_all(cursor, 'unused_myth', player_id=player['id'])
        unused_myth_list.append('{0}: {1}'.format(player['name'], ', '.join(util.select(cursor, 'myth_powers', id=power['id'])['name'] for power in powers)))
    messages.append(section_list('Unused Myth Powers', unused_myth_list))
    return messages

def set_success_point(cursor, success_point):
    cursor.execute('UPDATE globals SET success_point=?', (success_point,))