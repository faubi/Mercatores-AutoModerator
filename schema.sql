/*********************************\
*             Dynamic             *
\*********************************/

CREATE TABLE globals (
    forum_username text,
    forum_password text,
    thread_id int,
    last_turn_date text,
    turn_number int,
    success_point int
);

CREATE TABLE players (
    id integer primary key,
    name text COLLATE nocase,
    phase int
);

CREATE TABLE offices (
    player_id int,
    region_id int,
    level int,
    quantity int
);

CREATE TABLE inventories (
    player_id int,
    item_id int,
    quantity int
);

CREATE TABLE offers (
    id integer primary key,
    offerer int,
    offeree int,
    name text COLLATE nocase
);

CREATE TABLE offer_items (
    offer_id int,
    item_id int,
    quantity int
);

CREATE TABLE loans (
    id integer primary key,
    offerer int,
    offeree int,
    coins int,
    interest int,
    due_by int,
    accepted int,
    name text COLLATE nocase
);

CREATE TABLE myth_offered (
    player_id int,
    item_id int,
    god_id int,
    quantity int
);

CREATE TABLE price_changes (
    region_id int,
    item_id int,
    buy_change int,
    sell_change int,
    ends int
);

CREATE TABLE available_myth (
    myth_power_id int,
    purchased int
);

CREATE TABLE times_powers_purchased (
    myth_power_id int,
    times int
);

CREATE TABLE unused_myth (
    myth_power_id int,
    player_id int
);

CREATE TABLE queued_events (
    id integer primary key,
    event_id int,
    message text,
    starts int
);

CREATE TABLE price_change_event_regions (
    queued_event_id int,
    region_id int
);

CREATE TABLE give_items_event_players (
    queued_event_id int,
    player_id int
);

CREATE TABLE current_events (
    message text,
    ends int
);

CREATE TABLE turn_changes (
    post_number int
);

CREATE TABLE posts (
    post_number int,
    author text,
    html text COLLATE nocase
);

/*********************************\
*             Static              *
\*********************************/

CREATE TABLE params (
    days_per_turn int,
    starting_coins int,
    myth_powers_start int,
    base_office_price int,
    office_multiplier int,
    coins_id int,
    roma_id int
);


CREATE TABLE regions (
    id integer primary key,
    name text COLLATE nocase
);

CREATE TABLE items (
    id integer primary key,
    capacity int,
    name text COLLATE nocase,
    buyable int
);

CREATE TABLE prices (
    region_id int,
    item_id int,
    buy_price int,
    sell_price int
);

CREATE TABLE gods (
    id integer primary key,
    name text COLLATE nocase
);

CREATE TABLE myth_powers (
    id integer primary key,
    god_id int,
    name text COLLATE nocase,
    description text,
    event_id int,
    delay int
);

CREATE TABLE myth_power_prices (
    myth_power_id int,
    item_id int,
    quantity int
);

-- Event types: 
-- give items (0);
-- price change (1);
CREATE TABLE "events" (
    id integer primary key,
    event_type int,
    name text
);

CREATE TABLE price_change_events (
    event_id int,
    buy_change int,
    sell_change int,
    duration int
);

CREATE TABLE price_change_event_items (
    event_id int,
    item_id int
);

-- lower priority is given first
CREATE TABLE give_items_event_items (
    event_id int,
    item_id int,
    quantity int,
    priority int
);

CREATE TABLE upgrade_prices (
    level int,
    item_id int,
    quantity int
);

CREATE TABLE office_levels (
    level int,
    capacity int
);