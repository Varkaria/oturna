from re import sub
from flask import Blueprint, render_template, request
from objects import mysql

db = mysql.DB()
stream = Blueprint('stream', __name__)

@stream.route('/bg')
def index():
    songpos = request.args.get('songpos')
    title = request.args.get('t')
    subtitle = request.args.get('s')

    if title:
        title = title
    else:
        title = ''
    
    if subtitle:
        subtitle = subtitle
    else:
        subtitle = ''

    if songpos not in ['left', 'right', 'center']:
        return 'wrong value in args man'

    return render_template('stream/background.html', songpos=songpos, title=title, subtitle=subtitle)

@stream.route('/greeting_cm')
def greeting_cm():
    return render_template('stream/greeting_cm.html')

@stream.route('/greeting_daniel')
def greeting_daniel():
    return render_template('stream/greeting_daniel.html')

@stream.route('/showcase')
def m_showcase():
    return render_template('stream/showcase.html')