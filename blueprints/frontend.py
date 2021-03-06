from flask import Blueprint, jsonify, request, render_template, send_file
from objects import mysql
import markdown2
import os

db = mysql.DB()
frontend = Blueprint('frontend', __name__)

@frontend.route('/')
def index():
    return render_template('index.html')

@frontend.route('/rules/')
def rules():
    markdown = markdown2.markdown_path('docs/rules.md')
    return render_template('rules.html', doc=markdown)

@frontend.route('/schedule/')
@frontend.route('/schedule/<round_id>')
def schedule(round_id=db.current_round['id']):
    return render_template('schedule.html', matchs=db.get_matchs(round_id), round_id=round_id)

@frontend.route('/matchs/<match_id>')
def matchs(match=None):
    return render_template('matchs.html', match=match)

@frontend.route('/registeredlist/')
def registeredlist():
    return render_template('registeredlist.html', players=db.get_players())

@frontend.route('/player/<user_id>')
def player(user_id=None):
    return render_template('player.html', user=user_id)

@frontend.route('/mappools/')
@frontend.route('/mappools/<pool_id>')
def mappools(pool_id=db.current_round['id']):
    mappool = db.get_mappool(pool_id)
    if request.args.get('json'): return jsonify(mappool)
    return render_template('mappools.html', mappool=mappool, pool_id=pool_id)

@frontend.route('/staff/')
def staff():
    return render_template('staff.html', staff=db.get_staff())

@frontend.route("/team_flag/<int:uid>")
def serveAvatar(uid):
    # Check if avatar exists
    if os.path.isfile("{}/{}.jpg".format('.data/team_pics', uid)):
        avatarid = uid
    else:
        avatarid = -1

    # Serve actual avatar or default one
    return send_file("{}/{}.jpg".format('.data/team_pics', avatarid))