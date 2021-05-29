from config import Config
from flag import Staff
from flask.json import JSONEncoder
from flask import Flask, render_template, send_from_directory, jsonify, request
from blueprints import tourney, api
from datetime import datetime
import re, os, mysql, osuapi

class CustomJSONEncoder(JSONEncoder):
    def default(self, obj):
        try:
            if isinstance(obj, datetime):
                return obj.isoformat()
            iterable = iter(obj)
        except TypeError:
            pass
        else:
            return list(iterable)
        return JSONEncoder.default(self, obj)

sql = mysql.DB()
app = Flask(__name__, instance_relative_config=True)
app.config.from_object(Config)
app.register_blueprint(tourney, url_prefix='/manager')
app.register_blueprint(api, url_prefix='/api')
app.json_encoder = CustomJSONEncoder

@app.route('/favicon.ico')
def faviconico():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.context_processor
def rounds():
    return dict(active_rounds=sql.active_rounds)

@app.context_processor
def current_round():
    return dict(current_round=sql.current_round)

@app.context_processor
def tourney_info():
    return dict(tourney=sql.tourney)

@app.context_processor
def authorize():
    return dict(authorize=osuapi.authorize('login','identify'))

@app.route('/')
def index():
    return render_template('index.html')
    
@app.route('/info/')
def info():
    return render_template('info.html')

@app.route('/rules/')
def rules():
    return render_template('rules.html')

@app.route('/schedule/')
@app.route('/schedule/<round_id>')
def schedule(round_id=sql.current_round['id']):
    return render_template('schedule.html', matchs=sql.get_matchs(round_id), round_id=round_id)

@app.route('/matchs/<match_id>')
def matchs(match=None):
    return render_template('matchs.html', match=match)

@app.route('/registeredlist/')
def registeredlist():
    return render_template('registeredlist.html', players=sql.get_players())


@app.route('/player/<user_id>')
def player(user_id=None):
    return render_template('player.html', user=user_id)

# @app.route('/teams/')
# @app.route('/teams/<team_id>')
# def teams(team=None):
#     return render_template('teams.html', team=team)

@app.route('/mappools/')
@app.route('/mappools/<pool_id>')
def mappools(pool_id=sql.current_round['id']):
    mappool = sql.get_mappool(pool_id)
    if request.args.get('json'): return jsonify(mappool)
    return render_template('mappools.html', mappool=mappool, pool_id=pool_id)

@app.route('/staff/')
def staff():
    return render_template('staff.html', staff=sql.get_staff())
    
@app.template_filter('num')
def num_filter(num):
    if type(num) == int:
        return f'{num:,}'
    remain_amount = '%0.2f' % (num * 100 / 100.0)
    remain_amount_format =re.sub(r"(\d)(?=(\d\d\d)+(?!\d))", r"\1,", remain_amount)
    return remain_amount_format

@app.template_filter('floatfix')
def num_filter(num):
    remain_amount = '%0.2f' % (float(num))
    remain_amount_format =re.sub(r"(\d)(?=(\d\d\d)+(?!\d))", r"\1,", remain_amount)
    return remain_amount_format

@app.template_filter('timef')
def timef(num):
    return '%d:%02d' % (num//60, num%60)

@app.template_filter('datetime')
def dtf(date_time: datetime, sep='T', timespec='auto'):
    return date_time.isoformat(sep, timespec)

@app.template_filter('strdtf')
def strdtf(str_dt: str, sep='T', timespec='auto'):
    return datetime.fromisoformat(str_dt).isoformat(sep, timespec)

@app.template_filter('flag_url')
def flag_url(flag_name: str):
    flag_name = flag_name.split('.')
    if flag_name[0] == 'avatar':
        return f'https://a.ppy.sh/{flag_name[1]}'
    elif flag_name[0] == 'local':
        return f'/static/teams/flags/{flag_name[1]}'
    elif flag_name[0] == 'url':
        return flag_name[1]

@app.template_filter('privilege')
def privilege(num):
    return str(Staff(num))[6:].replace('|', ', ')

@app.errorhandler(404)
def page_not_foubd(error):
    return error

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000))
    )
