import os
from flask import Flask
from app.config import Config
from app.db import init_db, close_db, get_db
from app.routes import bp
from app import init_csrf_and_security
from pathlib import Path
from werkzeug.security import generate_password_hash

def create_app():
    app=Flask(__name__); app.config.from_object(Config); init_csrf_and_security(app); app.register_blueprint(bp); app.teardown_appcontext(close_db)
    Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True,exist_ok=True); Path(app.config['DATABASE']).parent.mkdir(parents=True,exist_ok=True)
    with app.app_context():
        init_db(); db=get_db()
        if not db.execute('SELECT 1 FROM users WHERE username=?',('admin',)).fetchone():
            db.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)',('admin',generate_password_hash('Admin@123'),'Admin')); db.commit()
    return app
app=create_app()
if __name__ == '__main__':
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug)
