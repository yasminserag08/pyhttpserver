from flask import Flask, jsonify

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "<h1>Hello from Flask!</h1>\n"

@flask_app.route('/api/status')
def status():
    return jsonify({
        "status": "online",
        "framework": "Flask"
    })

# Expose the standard WSGI callable interface for my server instead of using flask run
app = flask_app.wsgi_app