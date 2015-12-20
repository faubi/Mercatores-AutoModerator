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
    
    ActionError = util.ActionError
            
    @action('(?:Join|/in)')
    def join(queue, username):
        if select('players', name=username):
            raise ActionError('You cannot join because you are already playing!')
        else:
            cursor.execute('INSERT INTO players (name, phase) VALUES (?, 0)', (username,))
            player_id = cursor.lastrowid
            util.give_coins(cursor, player_id, util.get_param(cursor, 'starting_coins'))
            roma_id = util.get_param(cursor, 'roma_id')
            util.give_offices(cursor, player_id, roma_id, 1, 1)
            region_name = select('regions', id=roma_id)['name']
            raise ActionError('You have successfully joined the game and have been given an office in {0}. Choose a region for your second office to begin.'.format(region_name))
            
    @action('Take office in {region_name}')
    def take_office(queue, username, region_name):
        player = util.get_player(cursor, username, phase=0)
        region = util.get_region(cursor, region_name)
        offices_per_region = util.get_offices_per_region(cursor)
        if offices_per_region[region['id']] != min(offices_per_region.values()):
            raise ActionError('You must select an office in a region with the least offices')
        util.give_offices(cursor, player['id'], region['id'], 1, 1)
        cursor.execute('UPDATE players SET phase=1 WHERE id=?', (player['id'],))
        return 'You now have an office in {0}'.format(region['name'])
    
    @action('Buy {quantity} {item_name} (?:in|from) {region_name}')
    def buy_item(queue, username, quantity, item_name, region_name):
        player = util.get_player(cursor, username, phase=1)
        item = util.get_item(cursor, item_name)
        if not item['buyable']:
            raise ActionError('You can\'t buy that item'.format(item_name))
        region = util.get_region(cursor, region_name)
        if not select('offices', player_id=player['id'], region_id=region['id']):
            raise ActionError('You can only buy from regions where you have an office')
        try:
            quantity = int(quantity)
        except ValueError:
            raise ActionError('Invalid integer: {0}'.format(quantity))
        if quantity < 0:
            raise ActionError('You can\'t buy negative items')
        price = util.get_price(cursor, region['id'], item['id'], buying=True)*quantity
        if price > util.get_coins(cursor, player['id']):
            raise ActionError('You can\'t afford that')
        if quantity > util.get_free_capacity(cursor, player['id']):
            raise ActionError('You don\'t have enough free capacity to do that')
        util.give_coins(cursor, player['id'], -price)
        util.give_items(cursor, player['id'], item['id'], quantity)
        return 'You have successfully bought {0} {1} from {2}'.format(quantity, item['name'], region['name'])
        
    @action('Sell {quantity} {item_name} (?:in|to) {region_name}')
    def sell_item(queue, username, quantity, item_name, region_name):
        player = util.get_player(cursor, username, phase=2)
        item = util.get_item(cursor, item_name)
        if not item['buyable']:
            raise ActionError('You can\'t sell that item'.format(item_name))
        region = util.get_region(cursor, region_name)
        if not select('offices', player_id=player['id'], region_id=region['id']):
            raise ActionError('You can only sell to regions where you have an office')
        try:
            quantity = int(quantity)
        except ValueError:
            raise ActionError('Invalid integer: {0}'.format(quantity))
        if quantity < 0:
            raise ActionError('You can\'t sell negative items')
        price = util.get_price(cursor, region['id'], item['id'], buying=False)*quantity
        inv_quantity = util.get_inventory_quantity(cursor, player['id'], item['id'])
        if quantity > inv_quantity:
            raise ActionError('You don\'t have that many of that item')
        util.give_coins(cursor, player['id'], price)
        util.give_items(cursor, player['id'], item['id'], -quantity)
        return 'You have successfully sold {0} {1} to {2}'.format(quantity, item['name'], region['name'])
        
    @action('Lend {quantity} coins to {borrower_name} with {interest} coins interest due turn {turn_number} as {loan_name}')
    def lend(queue, username, quantity, borrower_name, interest, turn_number, loan_name):
        player = util.get_player(cursor, username, phase=1)
        try:
            quantity = int(quantity)
        except ValueError:
            raise ActionError('Invalid integer: {0}'.format(quantity))
        try:
            interest = int(interest)
        except ValueError:
            raise ActionError('Invalid integer: {0}'.format(interest))
        if quantity < 0 or interest < 0:
            raise ActionError('Loan amount and interest can\'t be negative')
        borrower = select('players', name=borrower_name)
        if not borrower:
            raise ActionError('Unknown player: {0}'.format(borrower_name))
        if player['id'] == borrower['id']:
            raise ActionError('You can\'t make a loan to yourself')
        try:
            turn_number = int(turn_number)
        except ValueError:
            raise ActionError('{0} is not an integer'.format(turn_number))
        current_turn = util.get_global(cursor, 'turn_number')
        if current_turn >= turn_number:
            raise ActionError('Turn {0} has already started'.format(turn_number))
        if select('loans', name=loan_name):
            raise ActionError('There is already a loan with that name')
        cursor.execute('INSERT INTO loans (offerer, offeree, coins, interest, due_by, accepted, name) VALUES (?, ?, ?, ?, ?, ?, ?)', 
            (player['id'], borrower['id'], quantity, interest, turn_number, False, loan_name))
        return 'Loan successfully offered'
    
    @action('Accept loan {loan_name}')
    def accept_loan(queue, username, loan_name):
        player = util.get_player(cursor, username, phase=1)
        loan = select('loans', name=loan_name)
        if not loan:
            raise ActionError('There is no loan with that name')
        if loan['accepted']:
            raise ActionError('That loan offer has already been accepted')
        if loan['offeree'] != player['id']:
            raise ActionError('That loan offer wasn\'t made to you')
        lender = select('players', id=loan['offerer'])
        if loan['coins'] > util.get_coins(cursor, lender['id']):
            raise ActionError('{0} doesn\'t have enough coins'.format(lender['name']))
        util.give_coins(cursor, lender['id'], -loan['coins'])
        util.give_coins(cursor, player['id'], loan['coins'])
        cursor.execute('UPDATE loans SET accepted=1 WHERE id=?', (loan['id'],))
        return 'Loan successfully accepted'
    
    @action('Refuse loan {loan_name}')
    def refuse_loan(queue, username, loan_name):
        player = util.get_player(cursor, username)
        loan = select('loans', name=loan_name)
        if not loan:
            raise ActionError('There is no loan with that name')
        if loan['accepted']:
            raise ActionError('That loan offer has already been accepted')
        if loan['offeree'] != player['id']:
            raise ActionError('That loan offer wasn\'t made to you')
        cursor.execute('DELETE FROM loans WHERE id=?', (loan['id'],))
        return 'Loan succesfully refused'
    
    @action('Cancel loan {loan_name}')
    def cancel_loan(queue, username, loan_name):
        player = util.get_player(cursor, username)
        loan = select('loans', name=loan_name)
        if not loan:
            raise ActionError('There is no loan with that name')
        if loan['accepted']:
            raise ActionError('That loan offer has already been accepted')
        if loan['offerer'] != player['id']:
            raise ActionError('That loan offer wasn\'t made by you')
        cursor.execute('DELETE FROM loans WHERE id=?', (loan['id'],))
        raise ActionError('Loan succesfully cancelled')
    
    #@action(r'Trade {items1} for {items2>(?:(?:[0-9]+|an?) .*?(?:, | and |, and )?)*) with {player} as {name}')
    @action('Offer {items_1} for {items_2} to {offeree_name} as {offer_name}')
    def make_offer(queue, username, items_1, items_2, offeree_name, offer_name):
        player = util.get_player(cursor, username, phase=1)
        offeree = select('players', name=offeree_name)
        if not offeree:
            raise ActionError('Unknown player: {0}'.format(offeree_name))
        if select('offers', name=offer_name):
            raise ActionError('There is already an offer with that name')
        if player['id'] == offeree['id']:
            raise ActionError('You can\'t make an offer to yourself')
        try:
            item_count = util.count_items_str(cursor, items_1)
            item_count_2 = util.count_items_str(cursor, items_2)
        except ValueError as e:
            raise ActionError(str(e))
        item_count.subtract(item_count_2)
        cursor.execute('INSERT INTO offers (offerer, offeree, name) VALUES (?, ?, ?)', (player['id'], offeree['id'], offer_name))
        offer_id = cursor.lastrowid
        for item, quantity in item_count.items():
            cursor.execute('INSERT INTO offer_items (offer_id, item_id, quantity) VALUES (?, ?, ?)', (offer_id, item, quantity))
        return 'Offer successfully made'
    
    @action('Accept (?:offer )?{offer_name}')
    def accept_offer(queue, username, offer_name):
        player = util.get_player(cursor, username, phase=1)
        offer = select('offers', name=offer_name)
        if not offer:
            raise ActionError('There is no offer with that name')
        if offer['offeree'] != player['id']:
            raise ActionError('That offer wasn\'t made to you')
        offerer = select('players', id=offer['offerer'])
        offer_items = select_all('offer_items', offer_id=offer['id'])
        for offer_item in offer_items:
            itempayer = offerer if offer_item['quantity'] >= 0 else player
            inv_quantity = util.get_inventory_quantity(cursor, itempayer['id'], offer_item['item_id'])
            if abs(offer_item['quantity']) > inv_quantity:
                raise ActionError('{0} doesn\'t have enough {1}'.format(itempayer['name'], select('items', id=offer_item['item_id'])['name']))
        capacity = sum(select('items', id=item['item_id'])['capacity']*item['quantity'] for item in offer_items)
        capacityuser = player if capacity >= 0 else offerer
        if capacity > util.get_free_capacity(cursor, capacityuser['id']):
            raise ActionError('{0} doesn\'t have enough free capacity'.format(capacityuser['name']))
        for offer_item in offer_items:
            util.give_items(cursor, offerer['id'], offer_item['item_id'], -offer_item['quantity'])
            util.give_items(cursor, player['id'], offer_item['item_id'], offer_item['quantity'])
        util.delete_offer(cursor, offer['id'])
        return 'Offer successfully completed'
    
    @action('Refuse (?:offer )?{offer_name}')
    def refuse_offer(queue, username, offer_name):
        player = util.get_player(cursor, username)
        offer = select('offers', name=offer_name)
        if not offer:
            raise ActionError('There is no offer with that name')
        if offer['offeree'] != player['id']:
            raise ActionError('That offer wasn\'t made to you')
        util.delete_offer(cursor, offer['id'])
        return 'Offer successfully refused'
    
    @action('Cancel (?:offer )?{offer_name}')
    def cancel_offer(queue, username, offer_name):
        player = util.get_player(cursor, username)
        offer = select('offers', name=offer_name)
        if not offer:
            raise ActionError('There is no offer with that name')
        if offer['offerer'] != player['id']:
            raise ActionError('You didn\'t make that offer')
        util.delete_offer(cursor, offer['id'])
        return 'Offer successfully cancelled'
        
    @action('Dump {quantity} {item_name}')
    def dump(queue, username, quantity, item_name):
        player = util.get_player(cursor, username)
        item = util.get_item(cursor, item_name)
        try:
            quantity = int(quantity)
        except ValueError:
            raise ActionError('Invalid integer: {0}'.format(quantity))
        if quantity < 0:
            raise ActionError('You can\'t dump negative items')
        inv_quantity = util.get_inventory_quantity(cursor, player['id'], item['id'])
        if quantity > inv_quantity:
            raise ActionError('You don\'t have that many of that item')
        util.give_items(cursor, player['id'], item['id'], -quantity)
        return 'You have successfully dumped {0} {1}'.format(quantity, item['name'])
        
    @action('(?:Move to|Enter) phase 2')
    def phase_2(queue, username):
        player = util.get_player(cursor, username, phase=1)
        cursor.execute('UPDATE players SET phase=2 WHERE id=?', (player['id'],))
        offers = select_all('offers', offerer=player['id'])
        for offer in offers:
            util.delete_offer(cursor, offer['id'])
        cursor.execute('DELETE FROM loans WHERE offerer=? AND accepted=0', (player['id'],))
        return 'You have moved to phase 2. Your pending offers and loans have been cancelled.'
    
    @action('Repay loan {loan_name}')
    def repay_loan(queue, username, loan_name):
        player = util.get_player(cursor, username, phase=1)
        loan = select('loans', name=loan_name)
        if not loan:
            raise ActionError('There is no loan with that name')
        if not loan['accepted']:
            raise ActionError('That loan offer hasn\'t been accepted yet')
        if loan['offeree'] != player['id']:
            raise ActionError('That loan wasn\'t made to you')
        coins = loan['coins'] + loan['interest']
        if coins > util.get_coins(cursor, player['id']):
            raise ActionError('You don\'t have enough coins')
            return False         
        lender = select('players', id=loan['offerer'])
        util.give_coins(cursor, lender['id'], coins)
        util.give_coins(cursor, player['id'], -coins)
        cursor.execute('DELETE FROM loans WHERE id=?', (loan['id'],))
        return 'Loan succesfully repayed'
    
    @action('Build office in {region_name}')
    def build_office(queue, username, region_name):
        player = util.get_player(cursor, username, phase=2)
        region = util.get_region(cursor, region_name)
        office_price = util.get_office_price(cursor, region['id'])
        if office_price > util.get_coins(cursor, player['id']):
            raise ActionError('You can\'t afford that')
        util.give_coins(cursor, player['id'], -office_price)
        util.give_offices(cursor, player['id'], region['id'], 1, 1)
        return 'Office succesfully built'
    
    @action('Upgrade(?: level {level})? office in {region_name}')
    def upgrade_office(queue, username, level, region_name):
        player = util.get_player(cursor, username, phase=2)
        region = util.get_region(cursor, region_name)
        if level:
            try:
                level = int(level)
            except ValueError:
                raise ActionError('{0} is not an integer'.format(level))
            office = select('offices', player_id=player['id'], region_id=region['id'], level=level)
            if not office:
                raise ActionError('You do not have any level {0} offices in {1}'.format(level, region['name']))
        else:
            cursor.execute('SELECT * FROM offices WHERE player_id=? AND region_id=? ORDER BY level', (player['id'], region['id']))
            office = cursor.fetchone()
            if not office:
                raise ActionError('You do not have any offices in {0}'.format(region['name']))
        old_level = office['level']
        if not select('office_levels', level=old_level+1):
            raise ActionError('That office is already at the maximum level')
        cursor.execute('SELECT item_id, quantity FROM upgrade_prices WHERE level=?', (office['level']+1,))
        upgrade_items = cursor.fetchall()
        for item_id, quantity in upgrade_items:
            inv_item = select('inventories', player_id=player['id'], item_id=item_id)
            if not inv_item or inv_item['quantity'] < quantity:
                raise ActionError('You don\'t have enough {0}'.format(select('items', id=item_id)['name']))
        for item_id, quantity in upgrade_items:
            util.give_items(cursor, player['id'], item_id, -quantity)
        util.give_offices(cursor, player['id'], region['id'], old_level, -1)
        util.give_offices(cursor, player['id'], region['id'], old_level+1, 1)
        raise ActionError('Successfully upgrade office in {0} to level {1}'.format(region['name'], old_level+1))
    
    @action('Offer {items} to {god_name}')
    def offer_to_god(queue, username, items, god_name):
        powers_start = util.get_param(cursor, 'myth_powers_start')
        if util.get_global(cursor, 'turn_number') < powers_start:
            raise ActionError('Myth powers can\'t be used until turn {1}'.format(powers_start))
            return False            
        player = util.get_player(cursor, username, phase=2)
        god = select('gods', name=god_name)
        if not god:
            raise ActionError('Unknown god: {0}'.format(god_name))
        try:
            offer_items = util.count_items_str(cursor, items)
        except ValueError as e:
            raise ActionError(str(e))
            return False            
        for item_id, quantity in offer_items.items():
            if util.get_inventory_quantity(cursor, player['id'], item_id) < quantity:
                raise ActionError('You don\'t have that many {0}'.format(select('items', id=item_id)['name']))
        for item_id, quantity in offer_items.items():
            util.give_items(cursor, player['id'], item_id, -quantity)
            util.give_myth_items(cursor, player['id'], item_id, god['id'], quantity)
        myth_power = util.get_current_power(cursor, god['id'])
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
                return 'Successfully offered to {0}. You now have {1}. Make sure to use it before the next turn'.format(
                    god['name'], myth_power['name'])
        return 'Successfully offered to {0}. No myth power obtained'.format(god['name'])
    
    @action('Use {myth_power_name}(?: on {target})?')
    def use_power(queue, username, myth_power_name, target):
        player = util.get_player(cursor, username, phase=2)
        cursor.execute('SELECT * FROM myth_powers WHERE id=(SELECT myth_power_id FROM unused_myth WHERE player_id=?) '
            'AND name=?', (player['id'], myth_power_name))
        myth_power = cursor.fetchone()
        if not myth_power:
            raise ActionError('You don\'t have that myth power to use')
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
                    raise ActionError('Unknown region: {0}'.format(region_name))
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
            raise ActionError('Internal error: Unknown event type {0}'.format(event['type']))
        cursor.execute('UPDATE queued_events WHERE id=? SET message=?', (queued_event_id, message))
        cursor.execute('DELETE FROM unused_myth WHERE myth_power_id=? AND player_id=?', (myth_power['id'], player['id']))
        return '{0} used {1}. It will take effect turn {2}'.format(myth_power['name'], ' on '+target if target else '', start_turn)
    
    @action('Do nothing')
    def use_power(queue, username):
        return 'Successfully did nothing'
        
    return actions
        
    
        
        
        