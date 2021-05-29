from config import Config
from pymysql.err import *
from blueprints.api import getdata
from flask import Blueprint, render_template, redirect, url_for, flash, session, request, jsonify
from logger import log
from flag import Staff, Mods
from rich.console import Console
from functools import wraps
import osuapi, mysql, json, re, requests

tourney = Blueprint('tourney', __name__)
db = mysql.DB()
console = Console()

def get(table_name: str, id: str):
    data = getdata(table_name, id).get_data()
    return json.loads(data).get('data', None)

def dict_cmp(a: dict, b: dict):
    cmp = a.items() - b.items()
    return dict(cmp)

def conv(x):
    def c(d):
        try:
            return eval(d)
        except Exception:
            return d

    if type(x) == dict:
        for y in x:
            x[y] = c(x[y])
        return x
    elif type(x) == list:
        return [c(a) for a in x]

@tourney.context_processor
def context():
    if session == {}:
        user = None
    else:
        user = get('view_staff', str(session['id']))

    return dict(
        cur_user=user,
        rounds=db.query_all("select * from round"),
    )

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        console.log(dict(session))
        if session == {}:
            return redirect(url_for('tourney.gologin'))
        return f(*args, **kwargs)
    return decorated_function


def need_privilege(privilege: Staff):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = db.get_staff(user_id=session['user_id'])
            if user == None:
                return redirect(url_for('tourney.gologin'))
            user_privilege = Staff(user['privileges'])
            if privilege not in user_privilege:
                flash(f'你沒有 {privilege.name} 權限!', 'danger')
                return redirect(url_for('tourney.dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def check_privilege(id, privilege: Staff):
    user = db.get_staff(staff_id=id)
    user_privilege = Staff(user['privileges'])
    return bool(privilege in user_privilege)

@tourney.route('/base')
def base():
    return render_template('/manager/base.html')

@tourney.route('/')
@login_required
def dashboard():
    return render_template('manager/dashboard.html')


@tourney.route('/login')
def gologin():
    return render_template('manager/auth.html')


def login(user):
    session.clear()
    session.permanent = True
    session['id'] = user['id']
    session['user_id'] = user['user_id']
    session['username'] = user['username']


@tourney.route('/callback')
def callback():
    if request.args.get('state') == 'login':
        u = osuapi.get_token(request.args['code'])
        try:
            user = osuapi.get2(u['access_token'], me='')
            sql = db.get_staff(user_id=user['id'])
            if sql:
                login(sql)
                return redirect(url_for('tourney.dashboard'))
            else:
                flash('It seems that you are not a staff, please go back.')
                log.debug(user)
                return redirect(url_for('index'))
        except Exception as e:
            log.exception(e)
    return redirect(url_for('index'))


@tourney.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@tourney.route('/schedule/')
@login_required
def matchs():
    teams = db.query_all('select * from team')
    if check_privilege(session['id'], Staff.ADMIN): isadmin = True
    else: isadmin = False

    staffs = {}
    for s in get('view_staff', '*'):
        for a in str(Staff(s['privileges']))[6:].split('|'):
            if not staffs.get(a):
                staffs[a] = []
            staffs[a].append(s)

    return render_template('manager/schedule.html', matchs=db.get_matchs(), isadmin=isadmin, teams=teams, staffs=staffs)

@tourney.route('/schedule/match/', methods=['POST'])
@login_required
@need_privilege(Staff.ADMIN)
def matchs_add():
    round_id = int(request.form['round'])
    code = request.form['code']
    team1_id = int(request.form['team1'])
    team2_id = int(request.form['team2'])
    date = request.form['date']
    loser = int(request.form.get('loser', 0))

    try:
        db.query('Insert into `match` (`round_id`, `code`, `team1`, `team2`, `date`, `loser`) values (%s, %s, %s, %s, %s, %s)', (round_id, code, team1_id, team2_id, date, loser))
        flash('%s added successfully' % code, 'success')
        return redirect(url_for('tourney.matchs'))
    except Exception as e:
        flash(e, 'danger')
        return redirect(url_for('tourney.matchs'))

@tourney.route('/schedule/match/<id>/update', methods=['POST'])
@login_required
@need_privilege(Staff.ADMIN)
def match_update(id):
    match: dict = get('match', id)
    match.pop('id')
    cmatch = dict(
        code = request.form.get('code'),
        round_id = request.form.get('round_id', type=int),
        team1 = request.form.get('team1', type=int),
        team1_score = request.form.get('team1_score', type=int),
        team2 = request.form.get('team2', type=int),
        team2_score = request.form.get('team2_score', type=int),
        date = request.form.get('date'),
        referee = request.form.get('referee', None, type=int),
        streamer = request.form.get('streamer', None, type=int),
        commentator = request.form.get('commentator', None, type=int),
        commentator2 = request.form.get('commentator2', None, type=int),
        mp_link = request.form.get('mp_link'),
        video_link = request.form.get('video_link'),
        stats = request.form.get('stats', type=int),
        loser = request.form.get('loser', 0, type=int),
        note = request.form.get('note'),
    )

    try:
        db.update('match', ('id', id), **dict_cmp(cmatch,match))
        flash('MathId: %s updated' % id, 'success')
        return redirect(url_for('tourney.matchs'))
    except IntegrityError as e:
        if e.args[0] == 1062 and re.match(r"Duplicate entry '(.+)' for key 'code'",e.args[1]):
            flash('You have to modify code already exists', 'danger')
        else:
            flash(e, 'danger')
        return redirect(url_for('tourney.matchs'))
    except Exception as e:
        flash(e, 'danger')
        return redirect(url_for('tourney.matchs'))

@tourney.route('/schedule/match/<id>/delete', methods=['POST'])
@login_required
@need_privilege(Staff.ADMIN)
def match_delete(id):
    try:
        db.query("DELETE FROM `match` WHERE id = %s;", [id])
        flash('MathId: %s deleted' % id, 'success')
        return redirect(url_for('tourney.matchs'))
    except Exception as e:
        flash(e, 'danger')
        return redirect(url_for('tourney.matchs'))

@tourney.route('/schedule/job', methods=['POST'])
@login_required
def matchs_job():
    mid = int(request.form['id'])
    uid = session['id']
    job = request.form['job']
    action = request.form['action']
    match = db.query_one("select * from `match` where id = %s", [mid])

    def update(id, privilege: Staff, ctx, args=None, success_msg=''):
        if check_privilege(id, privilege):
            try:
                db.query(ctx, args)
                flash(success_msg,'success')
            except Exception as e:
                flash(e, 'danger')
            finally:
                return redirect(url_for('tourney.matchs'))
        else:
            flash('you have not %s Authority' % privilege.name, 'danger')
            return redirect(url_for('tourney.matchs'))

    if match:
        if match['stats'] == 0:
            update_query = "Update `match` Set $x Where id = %d" % mid
            privilege = Staff.STAFF
            if action == 'get':
                success_msg = ''
                if job == 'ref':
                    update_query = update_query.replace('$x', 'referee = %d' % uid)
                    success_msg='You have next time %d Referee work' % mid
                    privilege = Staff.REFEREE
                elif job == 'stream':
                    update_query = update_query.replace('$x', 'streamer = %d' % uid)
                    success_msg='You have next time %d Live work' % mid
                    privilege = Staff.STREAMER
                elif job == 'comm':
                    if match['commentator']:
                        update_query = update_query.replace('$x', 'commentator2 = %d' % uid)
                        success_msg='You have next time %d Review work' % mid
                        privilege = Staff.COMMENTATOR
                    elif match['commentator'] and match['commentator2']:
                        flash('The scene has already depressed more!', 'danger')
                        return redirect(url_for('tourney.matchs'))
                    else:
                        update_query = update_query.replace('$x', 'commentator = %d' % uid)
                        success_msg='You have next time %d Review work' % mid
                        privilege = Staff.COMMENTATOR
                else:
                    flash('job Value "%s" Not a valid value' % job, 'danger')
                    return redirect(url_for('tourney.matchs'))
                return update(uid, privilege, update_query, success_msg=success_msg)
            elif action == 'remove':
                success_msg = ''
                privilege = Staff.STAFF
                if job == 'ref' and match['referee'] == uid:
                    success_msg = 'You have already released %d Referee work' % mid
                    update_query = update_query.replace('$x', 'referee = NULL')
                    privilege = Staff.REFEREE
                elif job == 'stream' and match['streamer'] == uid:
                    success_msg = 'You have already released %d Live work' % mid
                    update_query = update_query.replace('$x', 'streamer = NULL')
                    privilege = Staff.STREAMER
                elif job == 'comm':
                    if match['commentator'] == uid:
                        update_query = update_query.replace('$x', 'commentator = NULL')
                    elif match['commentator2'] == uid:
                        update_query = update_query.replace('$x', 'commentator2 = NULL')
                    success_msg = 'You have already released %d Review work' % mid
                    privilege = Staff.COMMENTATOR
                else:
                    if job not in ('ref', 'stream', 'comm'):
                        flash('job Value "%s" Not a valid value' % job, 'danger')
                        return redirect(url_for('tourney.matchs'))
                    else:
                        flash('You have not taken the work of this', 'danger')
                        return redirect(url_for('tourney.matchs'))
                        
                return update(uid, privilege, update_query, success_msg=success_msg)
            else:
                flash('action Value "%s" Not a valid value' % action, 'danger')
                return redirect(url_for('tourney.matchs'))
        else:
            flash('match_id: %d The transformation has ended!' % mid, 'danger')
            return redirect(url_for('tourney.matchs'))
    else:
        flash("match_id: %d Can't find the corresponding scene!" % mid, 'danger')
        return redirect(url_for('tourney.matchs'))

@tourney.route('/team/')
@login_required
def teams():
    teams = db.query_one("SELECT JSON_ARRAYAGG(json) json FROM json_team")['json']

    return render_template('manager/team.html', teams=json.loads(teams))

@tourney.route('/team/<team_id>/update', methods=['POST'])
@login_required
def team_update(team_id):
    s_team = db.query_one("SELECT id, full_name, flag_name, acronym FROM team WHERE id = %s", (team_id,))
    s_leader = db.query_one("SELECT user_id, COUNT(*) AS bool FROM player WHERE team = %s AND leader = 1", (team_id,))["user_id"]
    s_players = json.loads(db.query_one("SELECT JSON_ARRAYAGG(user_id) playsers FROM player WHERE team = %s", (team_id,))["playsers"])
    c_team = dict(
        id=int(team_id),
        full_name=request.form.get('full_name'),
        flag_name="{}.{}".format(request.form.get('flag_type'),request.form.get('flag_name')),
        acronym=request.form.get('acronym')
    )
    c_leader = request.form.get("leader", type=int)
    c_players = request.form.getlist("player[]", int)

    try:
        # Check update Team basic message
        diff_var = dict_cmp(c_team, s_team)
        if diff_var:
            db.update('team', ('id', team_id), **diff_var)

        # Check update Teamleader
        diff_leader = {c_leader}-{s_leader}
        new_leader = None
        if diff_leader:
            new_leader = list(diff_leader)[0]
            db.query("UPDATE player SET leader = 1 WHERE team = %s AND user_id = %s", (team_id, new_leader))

        # Check for TeamPlayers
        diff_players = set(c_players) ^ set(s_players)
        if diff_players:
            for player in diff_players:
                if player not in s_players:
                    args = {'k': Config.OSU_API_KEY, 'u': player}
                    player_info = conv(requests.get('https://osu.ppy.sh/api/get_user', args).json()[0])
                    player_bp1 = conv(requests.get('https://osu.ppy.sh/api/get_user_best', args|{'limit': 1}).json()[0])
                    leader = 1 if new_leader == player_info["user_id"] else 0
                    db.query(
                        "INSERT INTO player (user_id, username, team, info, bp1, leader) VALUES (%s, %s, %s, %s, %s, %s)",
                        (player_info["user_id"], player_info["username"], team_id, json.dumps(player_info), json.dumps(player_bp1), leader))
                else: 
                    db.query("DELETE FROM player WHERE team = %s AND user_id = %s", (team_id, player))

        flash('TeamID: {} updated'.format(team_id), 'success')
        return redirect(url_for('tourney.teams'))
    except Exception as e:
        flash('An error occurred: {}'.format(e.args), 'danger')
        return redirect(url_for('tourney.teams'))


@tourney.route('/team/<id>/delete', methods=['POST'])
@login_required
def team_delete(id):
    try:
        db.query("DELETE FROM `team` WHERE id = %s;", [id])
        flash('TeamID: {} deleted'.format(id), 'success')
        return redirect(url_for('tourney.teams'))
    except Exception as e:
        flash('An error occurred: {}'.format(e.args), 'danger')
        return redirect(url_for('tourney.teams'))


@tourney.route('/team/<id>/players/add', methods=['POST'])
@login_required
def team_players_add(id):
    return '', 200

@tourney.route('/team/<id>/players/<uid>/delete', methods=['POST'])
@login_required
def team_players_update(id, uid):
    return '', 200

@tourney.route('/team/<id>/players/<uid>/update', methods=['POST'])
@login_required
def team_players_delete(id):
    return '', 200

@tourney.route('/rounds/', methods=['GET', 'POST'])
@login_required
@need_privilege(Staff.ADMIN)
def rounds():
    if request.method == 'GET':
        pool_group_count = db.query_all("""
            SELECT m.round_id, m.`mods`, COUNT(m.`mods`) 'count', g.badge_color
            FROM mappool m
            LEFT JOIN map_group g ON g.`name` = m.`mods`
            GROUP BY m.round_id, m.`mods`
            ORDER BY FIELD(m.`mods`, 'TB', 'EZ', 'Roll', 'DT', 'HR', 'HD', 'NM', 'FM') DESC""")
        rounds=get('round','*')

        for p in pool_group_count:
            for r in rounds:
                if not r.get('pool_overview'):
                    r['pool_overview'] = []
                if r['id'] == p['round_id']:
                    r['pool_overview'].append({'group': p['mods'], 'count': p['count'], 'badge_color': p['badge_color']})

        return render_template('manager/rounds.html', rounds=rounds)
    elif request.method == 'POST':
        values = (
            request.form.get('name', type=str),
            request.form.get('description', None, str),
            request.form.get('best_of', type=int),
            request.form.get('start_date', type=str)
        )
        try:
            db.query("INSERT INTO `round` (name, description, best_of, start_date) VALUES (%s, %s, %s, %s)", values)
            flash('Round: {} added successfully'.format(values[0]), 'success')
            return redirect(url_for('tourney.rounds'))
        except Exception as e:
            flash('An error occurred: {}'.format(e.args), 'danger')
            return redirect(url_for('tourney.rounds'))

@tourney.route('/rounds/<round_id>/update', methods=['POST'])
@login_required
@need_privilege(Staff.ADMIN)
def rounds_update(round_id):
    s_round = get('round', round_id)
    c_round = dict(
        id=request.form.get('id', type=int),
        name=request.form.get('name', type=str),
        description=request.form.get('description', None, str),
        best_of=request.form.get('best_of', type=int),
        start_date=request.form.get('start_date', None, str),
        pool_publish=request.form.get('pool_publish', 0, int)
    )

    try:
        db.update('round', ('id', round_id), **dict_cmp(c_round, s_round))
        flash('RoundID: {} updated'.format(round_id), 'success')
        return redirect(url_for('tourney.rounds'))
    except Exception as e:
        flash('An error occurred: {}'.format(e.args), 'danger')
        return redirect(url_for('tourney.rounds'))

@tourney.route('/rounds/<round_id>/delete', methods=['POST'])
@login_required
@need_privilege(Staff.ADMIN)
def rounds_delete(round_id):
    try:
        db.query("DELETE FROM `round` WHERE id = %s;", [round_id])
        flash('RoundID: {} deleted'.format(round_id), 'success')
        return redirect(url_for('tourney.rounds'))
    except Exception as e:
        flash('An error occurred: {}'.format(e.args), 'danger')
        return redirect(url_for('tourney.rounds'))

@tourney.route('/staff/', methods=['GET', 'POST'])
@login_required
@need_privilege(Staff.ADMIN)
def staff():
    if request.method == 'POST':
        try:
            console.log(dict(request.form))
            postype = request.form['type']
            user_id = int(request.form['id'])
            if postype in ('add', 'update'):
                group = int(request.form['group'])
                privileges = int(request.form['privileges'])
                username = osuapi.get(osuapi.V1Path.get_user, u=user_id)[0]['username']
                if postype == 'add':
                    if db.query_one("Select user_id from staff where user_id = %s", (user_id,)) == None:
                        db.query("Insert into staff (user_id, username, group_id, privileges) Values (%s, %s, %s, %s)", (user_id, username, group, privileges))
                    else:
                        db.query("Update staff Set group_id = %s, privileges = %s, username = %s, active = 1 Where user_id = %s", (group, privileges, username, user_id))
                elif postype == 'update':
                    db.query("Update staff Set group_id = %s, privileges = %s, username = %s Where user_id = %s", (group, privileges, username, user_id))
            elif postype == 'disable':
                db.query("Update staff Set active = 0 Where user_id = %s", (user_id,))
            elif postype == 'enable':
                db.query("Update staff Set active = 1 Where user_id = %s", (user_id,))
        except Exception as e:
            flash(e.args[0], 'danger')
            log.exception(e)
        finally:
            return redirect(url_for('tourney.staff'))

    return render_template('manager/staff.html', staff=get('view_staff', '*'))


@tourney.route('/settings/', methods=['GET', 'POST'])
@login_required
@need_privilege(Staff.HOST)
def settings():
    if request.method == 'POST':
        if request.form:
            update_text = ''
            for k, v in request.form.items():
                if v.isdigit():
                    update_text += f"{k}={v},"
                else:
                    update_text += f"{k}='{v}',"
            
            db.query(f"UPDATE tourney SET {update_text[:-1]} WHERE id = 1")
            flash('Save Success', 'success')
            return redirect(url_for('tourney.settings'))
    return render_template('manager/settings.html', settings=db.query_one('select * from tourney where id = 1'))

# view
@tourney.route('/mappool/', defaults={'round_id': '1'})
@tourney.route('/mappool/<round_id>')
@login_required
@need_privilege(Staff.MAPPOOLER)
def mappool(round_id):
    mappool = db.query("SELECT JSON_ARRAYAGG(json) json FROM json_mappool WHERE round_id = %s GROUP BY round_id", round_id)
    
    sortorder={"FM":0, "HD":1, "HR":2, "DT":3, "NM":5, "Roll":6, "EZ":7, "FL":8, "TB":9}
    mappool = sorted(json.loads(mappool['json']), key=lambda k: sortorder.get(k['mods'],999)) if mappool is not None else []
    group_info = db.query_all("SELECT * FROM map_group")
    return render_template('manager/mappool.html', mappool=mappool, map_groups=group_info)

# action
@tourney.route('/mappool/<round>/add', methods=['POST'])
@login_required
@need_privilege(Staff.MAPPOOLER)
def mappool_add(round):
    try:
        # Request.form gets the message obtained
        beatmap_id:str = request.form['id']     # 图 谱 i
        if not beatmap_id.isdigit(): 
            raise ValueError('beatmap_id Must be a number')
        group = request.form['mods']           # MODS
        note = request.form.get('note',None)    # Note

        # SESSION gets the message
        poster = int(session['id'])          # Nominator ID

        # SQL's message
        round_info = db.query_one('select * from round where id = %s', (round,)) # Round information
        if round_info['pool_publish'] == 1:
            raise Exception('This phase of the pool has been announced and cannot be changed!')

        modcount = db.query_one('SELECT mods, COUNT(*) AS `count` FROM mappool WHERE round_id = 1 and mods = %s', (group,)) # Take the group count
        mods = db.query_one("SELECT enabled_mods FROM map_group WHERE name = %s", (group,))
        # Judging whether it will change the difficulty MODS
        if mods['enabled_mods'] in ('TB', 'FM') :
            request_mods = 0
        elif Mods(int(mods['enabled_mods'])) in (Mods.Easy | Mods.HalfTime | Mods.HardRock | Mods.DoubleTime | Mods.Nightcore):
            request_mods = mods['enabled_mods']
        else : 
            request_mods = 0

        # API's message
        beatmap = osuapi.get(osuapi.V1Path.get_beatmaps, b=request.form['id'], m=0, mods=request_mods)[0]
        # Convert the API's data into the correct type
        for k in beatmap:
            beatmap[k] = osuapi.todata(beatmap[k])

        # debug
        log.debug(dict(request.form))
        # The map is inserted into SQL
        db.query('insert into `mappool` (`round_id`, `beatmap_id`, `code`, `mods`, `info`, `note`, `nominator`) values (%s, %s, %s, %s, %s, %s, %s)',
            (int(round), int(beatmap_id), modcount['count']+1, group, json.dumps(beatmap), note, poster))
            
        # Successful message
        info = '%s - %s [%s] (%s) Has been added %s' % (beatmap['artist'], beatmap['title'], beatmap['version'], group, round_info['name'])
        flash(info, 'success')
    except Exception as e:
        flash(e.args[0], 'danger')
        log.exception(e)
    finally:
        return redirect(url_for('tourney.mappool', round_id=round))
            
@tourney.route('/mappool/<round>/update', methods=['POST'])
@login_required
@need_privilege(Staff.MAPPOOLER)
def mappool_update(round):
    try:
        cm = request.form.to_dict()
        id = cm['id']; cm.pop('id')
        sm = db.query_one("select mods, note from mappool where round_id = %s and id = %s", (round, id))

        db.update('mappool', ('id', id), **dict_cmp(cm, sm))
        flash('success', 'success')
    except Exception as e:
        flash(e.args, 'danger')
        log.exception(e)
    finally:
        return redirect(url_for('tourney.mappool', round_id=round))

@tourney.route('/mappool/<round>/<id>/del', methods=['POST'])
@login_required
@need_privilege(Staff.MAPPOOLER)
def mappool_del(id, round):
    try:
        db.query("delete from `mappool` where id = %s", [id]) # for notpeople : ไม่ใส่ varible หล่ะ :anger:
        flash('Remove Success :happy:', 'success')
    except Exception as e:
        flash(e.args[0], 'danger')
        log.exception(e)
    finally:
        return redirect(url_for('tourney.mappool', round_id=round))