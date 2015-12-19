import re, util
from collections import Counter

def get_actions(cursor):
    actions = [] #[(regex, function)]

    def action(regex):
        regex = re.sub(r'\{(.*?)}', lambda m:r'(?P<{0}>.*?)'.format(m.group(1)), regex) + r'\.?$'
        compiled_regex = re.compile(regex, flags=re.IGNORECASE)            
        return lambda function: actions.append((compiled_regex, function))
            
    selector = util.Selector(cursor)
    select = selector.select
    select_all = selector.select_all
            
    @action('Join')
    def join(queue, username):
        if select('players', name=username):
            queue.quote('You cannot join because you are already playing!')
            return False
        else:
            cursor.execute('INSERT INTO players (name, phase) VALUES (?, 0)', (username,))
            player_id = cursor.lastrowid
            util.give_coins(cursor, player_id, util.get_param(cursor, 'starting_coins'))
            roma_id = util.get_param(cursor, 'roma_id')
            util.give_offices(cursor, player_id, roma_id, 1, 1)
            region_name = select('regions', id=roma_id)['name']
            queue.quote('You have successfully joined the game and have been given an office in {0}. Choose a region for your second office to begin.'.format(region_name))
            return True
            
    @action('Take office in {region_name}')
    def take_office(queue, username, region_name):
        player = select('players', name=username)
        if not player or player['phase'] != 0:
            queue.quote('You already have a starting office.')
            return False
        region = select('regions', name=region_name)
        if not region:
            queue.quote('Unknown region: {0}'.format(region_name))
            return False
        offices_per_region = util.get_offices_per_region(cursor)
        if offices_per_region[region['id']] != min(offices_per_region.values()):
            queue.quote('You must select an office in a region with the least offices')
            return False
        util.give_offices(cursor, player['id'], region['id'], 1, 1)
        cursor.execute('UPDATE players SET phase=1 WHERE id=?', (player['id'],))
        queue.quote('You now have an office in {0}'.format(region['name']))
        return True
    
    @action('Buy {quantity} {item_name} from {region_name}')
    def buy_item(queue, username, quantity, item_name, region_name):
        player = select('players', name=username)
        if not player or player['phase'] != 1:
            queue.quote('You can only buy items in phase 1')
            return False
        item = select('items', name=item_name)
        if not item:
            queue.quote('Unknown item: {0}'.format(item_name))
            return False
        if not item['buyable']:
            queue.quote('You can\'t buy that item'.format(item_name))
            return False
        region = select('regions', name=region_name)
        if not region:
            queue.quote('Unknown region: {0}'.format(region_name))
            return False
        if not select('offices', player_id=player['id'], region_id=region['id']):
            queue.quote('You can only buy from regions where you have an office')
            return False
        try:
            quantity = int(quantity)
        except ValueError:
            queue.quote('Invalid integer: {0}'.format(quantity))
            return False
        if quantity < 0:
            queue.quote('You can\'t buy negative items')
            return False
        price = util.get_price(cursor, region['id'], item['id'], buying=True)*quantity
        if price > util.get_coins(cursor, player['id']):
            queue.quote('You can\'t afford that')
            return False
        if quantity > util.get_free_capacity(cursor, player['id']):
            queue.quote('You don\'t have enough free capacity to do that')
            return False
        util.give_coins(cursor, player['id'], -price)
        util.give_items(cursor, player['id'], item['id'], quantity)
        queue.quote('You have successfully bought {0} {1} from {2}'.format(quantity, item['name'], region['name']))
        return True
        
    @action('Sell {quantity} {item_name} to {region_name}')
    def sell_item(queue, username, quantity, item_name, region_name):
        player = select('players', name=username)
        if not player or player['phase'] != 2:
            queue.quote('You can only sell items in phase 2')
            return False
        item = select('items', name=item_name)
        if not item:
            queue.quote('Unknown item: {0}'.format(item_name))
            return False
        if not item['buyable']:
            queue.quote('You can\'t sell that item'.format(item_name))
            return False
        region = select('regions', name=region_name)
        if not region:
            queue.quote('Unknown region: {0}'.format(region_name))
            return False
        if not select('offices', player_id=player['id'], region_id=region['id']):
            queue.quote('You can only sell to regions where you have an office')
            return False
        try:
            quantity = int(quantity)
        except ValueError:
            queue.quote('Invalid integer: {0}'.format(quantity))
            return False
        if quantity < 0:
            queue.quote('You can\'t sell negative items')
            return False
        price = util.get_price(cursor, region['id'], item['id'], buying=False)*quantity
        inv_quantity = util.get_inventory_quantity(cursor, player['id'], item['id'])
        if quantity > inv_quantity:
            queue.quote('You don\'t have that many of that item')
            return False
        util.give_coins(cursor, player['id'], price)
        util.give_items(cursor, player['id'], item['id'], -quantity)
        queue.quote('You have successfully sold {0} {1} to {2}'.format(quantity, item['name'], region['name']))
        return True
        
    @action('Lend {quantity} coins to {borrower_name} with {interest} coins interest due turn {turn_number} as {loan_name}')
    def lend(queue, username, quantity, borrower_name, interest, turn_number, loan_name):
        player = select('players', name=username)
        if not player or player['phase'] != 1:
            queue.quote('You can only make loan offers in phase 1')
            return False
        try:
            quantity = int(quantity)
        except ValueError:
            queue.quote('Invalid integer: {0}'.format(quantity))
            return False
        try:
            interest = int(interest)
        except ValueError:
            queue.quote('Invalid integer: {0}'.format(interest))
            return False
        borrower = select('players', name=borrower_name)
        if not borrower:
            queue.quote('Unknown player: {0}'.format(borrower_name))
            return False
        if player['id'] == borrower['id']:
            queue.quote('You can\'t make a loan to yourself')
            return False
        try:
            turn_number = int(turn_number)
        except ValueError:
            queue.quote('{0} is not an integer'.format(turn_number))
            return False
        current_turn = util.get_global(cursor, 'turn_number')
        if current_turn >= turn_number:
            queue.quote('Turn {0} has already started'.format(turn_number))
            return False
        if select('loans', name=loan_name):
            queue.quote('There is already a loan with that name')
            return False
        cursor.execute('INSERT INTO loans (offerer, offeree, coins, interest, due_by, accepted, name) VALUES (?, ?, ?, ?, ?, ?, ?)', 
            (player['id'], borrower['id'], quantity, interest, turn_number, False, loan_name))
        queue.quote('Loan successfully offered')
        return True
    
    @action('Accept loan {loan_name}')
    def accept_loan(queue, username, loan_name):
        player = select('players', name=username)
        if not player or player['phase'] != 1:
            queue.quote('You can only accept loans in phase 1')
            return False
        loan = select('loans', name=loan_name)
        if not loan:
            queue.quote('There is no loan with that name')
            return False
        if loan['accepted']:
            queue.quote('That loan offer has already been accepted')
            return False
        if loan['offeree'] != player['id']:
            queue.quote('That loan offer wasn\'t made to you')
            return False
        lender = select('players', id=loan['offerer'])
        if loan['coins'] > util.get_coins(cursor, lender['id']):
            queue.quote('{0} doesn\'t have enough coins'.format(lender['name']))
            return False
        util.give_coins(cursor, lender['id'], -loan['coins'])
        util.give_coins(cursor, player['id'], loan['coins'])
        cursor.execute('UPDATE loans SET accepted=1 WHERE id=?', (loan['id'],))
        queue.quote('Loan successfully accepted')
        return True
    
    @action('Refuse loan {loan_name}')
    def refuse_loan(queue, username, loan_name):
        player = select('players', name=username)
        if not player:
            queue.quote('You must join the game to do that')
            return False
        loan = select('loans', name=loan_name)
        if not loan:
            queue.quote('There is no loan with that name')
            return False
        if loan['accepted']:
            queue.quote('That loan offer has already been accepted')
            return False
        if loan['offeree'] != player['id']:
            queue.quote('That loan offer wasn\'t made to you')
            return False
        cursor.execute('DELETE FROM loans WHERE id=?', (loan['id'],))
        queue.quote('Loan succesfully refused')
        return True
    
    @action('Cancel loan {loan_name}')
    def cancel_loan(queue, username, loan_name):
        player = select('players', name=username)
        if not player:
            queue.quote('You must join the game to do that')
            return False
        loan = select('loans', name=loan_name)
        if not loan:
            queue.quote('There is no loan with that name')
            return False
        if loan['accepted']:
            queue.quote('That loan offer has already been accepted')
            return False
        if loan['offerer'] != player['id']:
            queue.quote('That loan offer wasn\'t made by you')
            return False
        cursor.execute('DELETE FROM loans WHERE id=?', (loan['id'],))
        queue.quote('Loan succesfully cancelled')
        return True
    
    #@action(r'Trade {items1} for {items2>(?:(?:[0-9]+|an?) .*?(?:, | and |, and )?)*) with {player} as {name}')
    @action('Offer {items_1} for {items_2} to {offeree_name} as {offer_name}')
    def make_offer(queue, username, items_1, items_2, offeree_name, offer_name):
        player = select('players', name=username)
        if not player or player['phase'] != 1:
            queue.quote('You can only make offers in phase 1')
            return False
        offeree = select('players', name=offeree_name)
        if not offeree:
            queue.quote('Unknown player: {0}'.format(offeree_name))
            return False
        if select('offers', name=offer_name):
            queue.quote('There is already an offer with that name')
            return False
        if player['id'] == offeree['id']:
            queue.quote('You can\'t make an offer to yourself')
            return False
        try:
            item_count = util.count_items_str(cursor, items_1)
            item_count_2 = util.count_items_str(cursor, items_2)
        except ValueError as e:
            queue.quote(str(e))
            return False
        item_count.subtract(item_count_2)
        cursor.execute('INSERT INTO offers (offerer, offeree, name) VALUES (?, ?, ?)', (player['id'], offeree['id'], offer_name))
        offer_id = cursor.lastrowid
        for item, quantity in item_count.items():
            cursor.execute('INSERT INTO offer_items (offer_id, item_id, quantity) VALUES (?, ?, ?)', (offer_id, item, quantity))
        queue.quote('Offer successfully made')
        return True
    
    @action('Accept (?:offer )?{offer_name}')
    def accept_offer(queue, username, offer_name):
        player = select('players', name=username)
        if not player or player['phase'] != 1:
            queue.quote('You can only accept offers in phase 1')
            return False
        offer = select('offers', name=offer_name)
        if not offer:
            queue.quote('There is no offer with that name')
            return False
        if offer['offeree'] != player['id']:
            queue.quote('That offer wasn\'t made to you')
            return False
        offerer = select('players', id=offer['offerer'])
        offer_items = select_all('offer_items', offer_id=offer['id'])
        for offer_item in offer_items:
            itempayer = offerer if offer_item['quantity'] >= 0 else player
            inv_quantity = util.get_inventory_quantity(cursor, itempayer['id'], offer_item['item_id'])
            if abs(offer_item['quantity']) > inv_quantity:
                queue.quote('{0} doesn\'t have enough {1}'.format(itempayer['name'], select('items', id=offer_item['item_id'])['name']))
                return False
        capacity = sum(select('items', id=item['item_id'])['capacity']*item['quantity'] for item in offer_items)
        capacityuser = player if capacity >= 0 else offerer
        if capacity > util.get_free_capacity(cursor, capacityuser['id']):
            queue.quote('{0} doesn\'t have enough free capacity'.format(capacityuser['name']))
            return False
        for offer_item in offer_items:
            util.give_items(cursor, offerer['id'], offer_item['item_id'], -offer_item['quantity'])
            util.give_items(cursor, player['id'], offer_item['item_id'], offer_item['quantity'])
        util.delete_offer(cursor, offer['id'])
        queue.quote('Offer successfully completed')
        return True
    
    @action('Refuse (?:offer )?{offer_name}')
    def refuse_offer(queue, username, offer_name):
        player = select('players', name=username)
        if not player:
            queue.quote('You must join the game to do that')
            return False
        offer = select('offers', name=offer_name)
        if not offer:
            queue.quote('There is no offer with that name')
            return False
        if offer['offeree'] != player['id']:
            queue.quote('That offer wasn\'t made to you')
            return False
        util.delete_offer(cursor, offer['id'])
        queue.quote('Offer successfully refused')
        return True
    
    @action('Cancel (?:offer )?{offer_name}')
    def cancel_offer(queue, username, offer_name):
        player = select('players', name=username)
        if not player:
            queue.quote('You must join the game to do that')
            return False
        offer = select('offers', name=offer_name)
        if not offer:
            queue.quote('There is no offer with that name')
            return False
        if offer['offerer'] != player['id']:
            queue.quote('You didn\'t make that offer')
            return False
        util.delete_offer(cursor, offer['id'])
        queue.quote('Offer successfully cancelled')
        return True
        
    @action('Dump {quantity} {item_name}')
    def dump(queue, username, quantity, item_name):
        player = select('players', name=username)
        if not player:
            queue.quote('You must join the game to do that')
            return False
        item = select('items', name=item_name)
        if not item:
            queue.quote('Unknown item: {0}'.format(item_name))
            return False
        try:
            quantity = int(quantity)
        except ValueError:
            queue.quote('Invalid integer: {0}'.format(quantity))
            return False
        if quantity < 0:
            queue.quote('You can\'t dump negative items')
            return False
        inv_quantity = util.get_inventory_quantity(cursor, player['id'], item['id'])
        if quantity > inv_quantity:
            queue.quote('You don\'t have that many of that item')
            return False
        util.give_items(cursor, player['id'], item['id'], -quantity)
        queue.quote('You have successfully dumped {0} {1}'.format(quantity, item['name']))
        return True
        
    @action('Move to phase 2')
    def phase_2(queue, username):
        player = select('players', name=username)
        if not player or player['phase'] != 1:
            queue.quote('You can only do that in phase 1')
            return False
        cursor.execute('UPDATE players SET phase=2 WHERE id=?', (player['id'],))
        offers = select_all('offers', offerer=player['id'])
        for offer in offers:
            util.delete_offer(offer['id'])
        cursor.execute('DELETE FROM loans WHERE offerer=? AND accepted=0', (player['id'],))
        queue.quote('You have moved to phase 2. Your pending offers and loans have been cancelled.')
        return True
    
    @action('Repay loan {loan_name}')
    def repay_loan(queue, username, loan_name):
        player = select('players', name=username)
        if not player or player['phase'] != 1:
            queue.quote('You can only repay loans in phase 1')
            return False
        loan = select('loans', name=loan_name)
        if not loan:
            queue.quote('There is no loan with that name')
            return False
        if not loan['accepted']:
            queue.quote('That loan offer hasn\'t been accepted yet')
            return False
        if loan['offeree'] != player['id']:
            queue.quote('That loan wasn\'t made to you')
            return False
        coins = loan['coins'] + loan['interest']
        if coins > util.get_coins(cursor, player['id']):
            queue.quote('You don\'t have enough coins')
            return False         
        lender = select('players', id=loan['offerer'])
        util.give_coins(cursor, lender['id'], coins)
        util.give_coins(cursor, player['id'], -coins)
        cursor.execute('DELETE FROM loans WHERE id=?', (loan['id'],))
        queue.quote('Loan succesfully repayed')
        return True
    
    @action('Build office in {region_name}')
    def build_office(queue, username, region_name):
        player = select('players', name=username)
        if not player or player['phase'] != 2:
            queue.quote('You can only build offices in phase 2')
            return False
        region = select('regions', name=region_name)
        if not region:
            queue.quote('Unknown region: {0}'.format(region_name))
            return False
        office_price = util.get_office_price(cursor, region['id'])
        if office_price > util.get_coins(cursor, player['id']):
            queue.quote('You can\'t afford that')
            return False
        util.give_coins(cursor, player['id'], -office_price)
        util.give_offices(cursor, player['id'], region['id'], 1, 1)
        queue.quote('Office succesfully built')
        return True
    
    @action('Upgrade(?: level {level})? office in {region_name}')
    def upgrade_office(queue, username, level, region_name):
        player = select('players', name=username)
        if not player or player['phase'] != 2:
            queue.quote('You can only upgrade offices in phase 2')
            return False
        region = select('regions', name=region_name)
        if not region:
            queue.quote('Unknown region: {0}'.format(region_name))
            return False
        if level:
            try:
                level = int(level)
            except ValueError:
                queue.quote('{0} is not an integer'.format(level))
                return False
            office = select('offices', player_id=player['id'], region_id=region['id'], level=level)
            if not office:
                queue.quote('You do not have any level {0} offices in {1}'.format(level, region['name']))
                return False
        else:
            cursor.execute('SELECT * FROM offices WHERE player_id=? AND region_id=? ORDER BY level', (player['id'], region['id']))
            office = cursor.fetchone()
            if not office:
                queue.quote('You do not have any offices in {0}'.format(region['name']))
                return False
        old_level = office['level']+1
        if not select('office_levels', level=old_level+1):
            queue.quote('That office is already at the maximum level')
            return False
        cursor.execute('SELECT item_id, quantity FROM upgrade_prices WHERE level=?', (office['level']+1,))
        upgrade_items = cursor.fetchall()
        for item_id, quantity in upgrade_items:
            inv_item = select('inventories', player_id=player['id'], item_id=item_id)
            if not inv_item or inv_item['quantity'] < quantity:
                queue.quote('You don\'t have enough {0}'.format(select('items', id=item_id)['name']))
                return False
        for item_id, quantity in offer_items:
            util.give_items(cursor, player['id'], item_id, -quantity)
        util.give_offices(cursor, player['id'], region['id'], old_level, -1)
        util.give_offices(cursor, player['id'], region['id'], old_level+1, 1)
        queue.quote('Successfully upgrade office in {0} to level {1}'.format(region['name'], old_level+1))
        return True
    
    @action('Offer {items} to {god_name}')
    def offer_to_god(queue, username, items, god_name):
        powers_start = util.get_param(cursor, 'myth_powers_start')
        if util.get_global(cursor, 'turn_number') < powers_start:
            queue.quote('Myth powers can\'t be used until turn {1}'.format(powers_start))
            return False            
        player = select('players', name=username)
        if not player or player['phase'] != 2:
            queue.quote('You can only offer to gods in phase 2')
            return False
        god = select('gods', name=god_name)
        if not god:
            queue.quote('Unknown god: {0}'.format(god_name))
            return False
        offer_items = util.count_items_str(cursor, items)
        for item_id, quantity in offer_items.items():
            inv_item = select('inventories', player_id=player['id'], item_id=item_id)
            if not inv_item or inv_item['quantity'] < quantity:
                queue.quote('You don\'t have that many {0}'.format(select('items', id=item_id)['name']))
                return False
        for item_id, quantity in offer_items.items():
            util.give_items(cursor, player['id'], item_id, -quantity)
            util.give_myth_items(cursor, player['id'], item_id, god['id'], quantity)
        myth_power = util.get_current_power(cursor, god)
        if myth_power and not myth_power['purchased']:
            power_items = select_all('myth_power_prices', myth_power_id=myth_power['id'])
            myth_offered = util.get_myth_offered(cursor, player['id'], god['id'])
            have_items = True
            for power_item in power_items:
                if power_item['quantity'] > myth_offered[item['id']]:
                    have_items = False
                    break
            if have_items:
                cursor.execute('INSERT INTO unused_myth (player_id, myth_power_id) VALUES (?, ?)', (player['id'], myth_power['id']))
                queue.quote('Successfully offered to {0}. You now have {1}. Make sure to use it before the next turn'.format(god['name'], myth_power['name']))
                return True
        queue.quote('Successfully offered to {0}. No myth power obtained'.format(god['name']))
        return True
    
    @action('Use {myth_power_name}(?: on {target})?')
    def use_power(queue, username, myth_power_name, target):
        player = select('players', name=username)
        if not player or player['phase'] != 2:
            queue.quote('You can only use myth powers in phase 2')
            return False
        cursor.execute('SELECT * FROM myth_powers WHERE id=(SELECT myth_power_id FROM unused_myth WHERE player_id=?) AND name=?', (player['id'], myth_power_name))
        myth_power = cursor.fetchone()
        if not myth_power:
            queue.quote('You don\'t have that myth power to use')
            return False
        event = select('events', id=myth_power['event_id'])
        start_turn = myth_power['delay'] + util.get_global(cursor, 'turn_number') + 1
        cursor.execute('INSERT INTO queued_events (event_id, starts) VALUES (?, ?)', (event['id'], start_turn))
        queued_event_id = cursor.lastrowid
        if event['type'] == 0:
            # Give items event
            cursor.execute('INSERT INTO give_items_event_players (queued_event_id, player_id) VALUES (?, ?)', (queued_event_id, player['id']))
            items_text = util.format_items(cursor, select_all('give_items_event_items', event_id=event['id']))
            message = '{0}: {1} gets {2}'.format(event['name'], username, items_text)
        elif event['type'] in (1, 2):
            # Price change event
            price_change = select('price_change_events', event_id=event['id'])
            buy_change = price_change['buy_change']
            buy_change_text = '{0}% {1}'.format(abs(buy_change), 'increase' if buy_change > 0 else 'decrease')
            sell_change = price_change['sell_change']
            sell_change_text = '{0}% {1}'.format(abs(sell_change), 'increase' if sell_change > 0 else 'decrease')
            end_turn = start_turn + price_change['duration']
            if event['type'] == 1:
                region = select('regions', name=target)
                if not region:
                    queue.quote('Unknown region: {0}'.format(region_name))
                    return False
                cursor.execute('INSERT INTO price_change_event_regions (queued_event_id, region_id) VALUES (?, ?)', (queued_event_id, region['id']))
                message = '{0} in {1}: {2} in buy prices and {3} in sell prices until turn {4}'.format(
                    event['name'], select('regions', id=region['id'])['name'], buy_change_text, sell_change_text, end_turn)
            else:
                items = select_all('price_change_event_items', event_id=event['id'])
                item_names = ', '.join(select('items', id=item['id'])['name'] for item in items)
                message = '{0}: {1} in buy prices and {2} in sell prices for {3} until turn {4}'.format(
                    event['name'], buy_change_text, sell_change_text, item_names, end_turn)
        elif event['type'] == 3:
            pass
        else:
            queue.quote('Internal error: Unknown event type {0}'.format(event['type']))
            return False
        cursor.execute('UPDATE queued_events WHERE id=? SET message=?', (queued_event_id, message))
        cursor.execute('DELETE FROM unused_myth WHERE myth_power_id=? AND player_id=?', (myth_power['id'], player['id']))
        queue.quote('{0} used{1}. It will take effect turn {2}'.format(myth_power['name'], ' on '+target if target else '', start_turn))
        return True
        
    return actions
        
    
        
        
        