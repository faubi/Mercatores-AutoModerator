import datetime, dateutil.parser, re
from collections import Counter

class Selector:
    
    def __init__(self, cursor):
        self.cursor = cursor
        
    def select(self, table, **kwargs):
        return select(self.cursor, table, **kwargs)
        
    def select_all(self, table, **kwargs):
        return select_all(self.cursor, table, **kwargs)
    
class ActionError(Exception):
    pass
    
def exec_select(cursor, table, kwargs):
    predicates = list(kwargs.items())
    selection = 'SELECT * FROM "{0}"'.format(table)
    where = ''
    if predicates:
        where = ' WHERE' + ' AND '.join('"{0}"=?'.format(x[0]) for x in predicates)
    cursor.execute(selection+where, tuple(x[1] for x in predicates))
        
def select(cursor, table, **kwargs):
    exec_select(cursor, table, kwargs)
    return cursor.fetchone()
        
def select_all(cursor, table, **kwargs):
    exec_select(cursor, table, kwargs)
    return cursor.fetchall()

def get_deadline(cursor):
    last_turn_date = dateutil.parser.parse(get_global(cursor, 'last_turn_date'))
    return last_turn_date + datetime.timedelta(days=get_param(cursor, 'days_per_turn'))
    
def set_last_turn_date(cursor, date):
    cursor.execute('UPDATE globals SET last_turn_date=?', (date.isoformat(),))
    
def update_last_turn_date(cursor):
    set_last_turn_date(cursor, get_deadline(cursor))
    
def check_new_turn(cursor):
    return datetime.datetime.now() > get_deadline(cursor)

def get_offices_per_region(cursor):
    offices = select_all(cursor, 'offices')
    totals = Counter()
    for office in offices:
        totals[office['region_id']] += office['quantity']
    for region in select_all(cursor, 'regions'):
        if not region['id'] in totals:
            totals[region['id']] = 0
    return totals

def get_base_price(cursor, region, item, buying):
    return select(cursor, 'prices', region_id=region, item_id=item)['buy_price' if buying else 'sell_price']

def get_price(cursor, region, item, buying):
    base_price = get_base_price(cursor, region, item, buying)
    multipliers = select_all(cursor, 'price_changes', region_id=region, item_id=item)
    total_multiplier = 1
    for multiplier in multipliers:
        total_multiplier *= 1+multiplier['buy_change' if buying else 'sell_change']/100
    return int(base_price*total_multiplier + 0.5)
    

def get_used_capacity(cursor, player_id):
    cursor.execute('SELECT SUM((SELECT capacity FROM items WHERE id=inventories.item_id)*quantity) FROM inventories WHERE player_id=?', (player_id,))
    return cursor.fetchone()[0]

def get_total_capacity(cursor, player_id):
    cursor.execute('SELECT SUM((SELECT capacity FROM office_levels WHERE level=offices.level)*quantity) FROM offices WHERE player_id=?', (player_id,))
    return cursor.fetchone()[0]

def get_free_capacity(cursor, player_id):
    return get_total_capacity(cursor, player_id) - get_used_capacity(cursor, player_id)

def give_items(cursor, player_id, item_id, quantity):
    if select(cursor, 'inventories', player_id=player_id, item_id=item_id):            
        cursor.execute('UPDATE inventories SET quantity=quantity+? WHERE player_id=? AND item_id=?', (quantity, player_id, item_id))
    else:
        cursor.execute('INSERT INTO inventories (quantity, player_id, item_id) VALUES (?, ?, ?)', (quantity, player_id, item_id))

def get_inventory(cursor, player_id):
    items = select_all(cursor, 'inventories', player_id=player_id)
    item_counter = Counter()
    for item in items:
        item_counter[item['item_id']] = item['quantity']        
    return item_counter

def get_inventory_quantity(cursor, player_id, item_id):
    item = select(cursor, 'inventories', player_id=player_id, item_id=item_id)
    if item:
        return item['quantity']
    else:
        return 0

def get_myth_offered(cursor, player_id, god_id):
    items = select_all(cursor, 'myth_offered', player_id=player_id, god_id=god_id)
    item_counter = Counter()
    for item in items:
        item_counter[item['id']] = item['quantity']
    return item_counter

def get_coins(cursor, player_id):
    coins_id = get_param(cursor, 'coins_id')
    return get_inventory(cursor, player_id)[coins_id]

def give_myth_items(cursor, player_id, item_id, god_id, quantity):
    if select(cursor, 'myth_offered', player_id=player_id, item_id=item_id, god_id=god_id):            
        cursor.execute('UPDATE myth_offered SET quantity=quantity+? WHERE player_id=? AND item_id=? AND god_id=?', (quantity, player_id, item_id, god_id))
    else:
        cursor.execute('INSERT INTO myth_offered (quantity, player_id, item_id, god_id) VALUES (?, ?, ?, ?)', (quantity, player_id, item_id, god_id))

def give_coins(cursor, player_id, quantity):
    coins_id = get_param(cursor, 'coins_id')
    give_items(cursor, player_id, coins_id, quantity)

def delete_offer(cursor, offer_id):
    cursor.execute('DELETE FROM offers WHERE id=?', (offer_id,))
    cursor.execute('DELETE FROM offer_items WHERE offer_id=?', (offer_id,))

def get_global(cursor, name):
    cursor.execute('SELECT {0} FROM globals'.format(name))
    return cursor.fetchone()[0]

def get_param(cursor, name):
    cursor.execute('SELECT {0} FROM params'.format(name))
    return cursor.fetchone()[0]

def get_office_price(cursor, region_id):
    cursor.execute('SELECT COUNT(*) FROM offices WHERE region_id=?', (region_id,))
    office_count = cursor.fetchone()[0]
    return get_param(cursor, 'base_office_price') * get_param(cursor, 'office_multiplier') ** office_count

def give_offices(cursor, player_id, region_id, level, quantity):
    if select(cursor, 'offices', player_id=player_id, region_id=region_id, level=level):
        cursor.execute('UPDATE offices SET quantity=quantity+? WHERE player_id=? AND region_id=? AND level=?', (quantity, player_id, region_id, level))
        cursor.execute('DELETE FROM offices WHERE quantity=0 AND player_id=? AND region_id=? AND level=?', (player_id, region_id, level))
    else:
        cursor.execute('INSERT INTO offices (quantity, player_id, region_id, level) VALUES (?, ?, ?, ?)', (quantity, player_id, region_id, level))
        
def cleanup(cursor):
    cursor.execute('DELETE FROM inventories WHERE quantity <= 0')
    cursor.execute('DELETE FROM offices WHERE quantity <= 0')
    cursor.execute('DELETE FROM offer_items WHERE quantity <= 0')
    cursor.execute('DELETE FROM myth_offered WHERE quantity <= 0')
        
def get_post_count(cursor):
    cursor.execute('SELECT COUNT(*) FROM posts')
    return cursor.fetchone()[0]

def parse_items(items_str):
    if items_str.lower() == 'nothing':
        return []
    item_list = re.split(r'\s*(?:,\s*and|and|,)\s*', items_str)
    for index, item in enumerate(item_list):
        item_match = re.match('(-?[0-9]+)\s+(.*)', item)
        if not item_match:
            raise ValueError('Unable to parse "{0}"'.format(item)+' as {quantity} {item}')
        item_list[index] = item_match.groups()
    return item_list

def count_items(cursor, item_list):
    items = Counter()
    for quantity, item in item_list:
        if quantity.lower() in ('nothing', 'none', 'no'):
            quantity = 0
        else:
            quantity = int(quantity)
        if quantity < 0:
            raise ValueError('Quantity cannot be negative')
        itemrow = select(cursor, 'items', name=item)
        if not itemrow:
            raise ValueError('Unknown item: {0}'.format(item))
        items[itemrow['id']] += quantity
    return items
    
def count_items_str(cursor, items_str):
    return count_items(cursor, parse_items(items_str))
    
def get_current_power(cursor, god):
    cursor.execute('SELECT mp.* FROM myth_powers AS mp INNER JOIN available_myth AS am ON mp.id=am.myth_power_id WHERE mp.god_id=?', (god,))
    return cursor.fetchone()
    
def format_items(cursor, items):
    item_text = []
    for item in items:
        item_name = select(cursor, 'items', id=item['item_id'])['name']
        item_text.append('{0} {1}'.format(item['quantity'], item_name))
    return ', '.join(item_text)

def bbcode_list(elements):
    elements = list(elements)
    if not elements:
        return ''
    return '[list]' + '\n'.join('[*]'+element+'[/*]' for element in elements) + '[/list]'

def text_table(table, dividers=(), sep=' | '):
    columns = max(len(row) for row in table)
    column_widths = [max(len(row[i]) for row in table) for i in range(columns)]
    lines = [sep.join(value.ljust(column_widths[i]) for i, value in enumerate(row)) for row in table]
    if dividers:
        divider = '-' * (len(sep)*(columns-1) + sum(column_widths))
        for i, line_number in enumerate(dividers):
            lines.insert(line_number+i, divider)
    return '\n'.join(lines)
    
def get_player(cursor, name, phase=None):
    player = select(cursor, 'players', name=name)
    if not player:
        raise ActionError('You must join the game to do that')
    if phase != 0 and player['phase'] == 0:
        raise ActionError('You must claim a starting office first')
    if phase and player['phase'] != phase:
        raise ActionError('You can only do that in phase {0}'.format(phase))
    return player
    
def get_region(cursor, name):
    region = select(cursor, 'regions', name=name)
    if not region:
        raise ActionError('Unknown region: {0}'.format(name))
    return region
    
def get_item(cursor, name):
    item = select(cursor, 'items', name=name)
    if not item:
        raise ActionError('Unknown item: {0}'.format(name))
    return item
    
    
    
    
    
    
    