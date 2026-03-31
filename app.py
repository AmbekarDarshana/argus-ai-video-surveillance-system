# app.py
from flask import Flask, app, session
from config import Config
from pymongo import MongoClient
import logging



def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Database Connection
    try:
        client = MongoClient(app.config['MONGO_URI'])
        app.db = client.get_database()
        app.mongo_client = client
        print(f"Database Connected: {app.db.name}")
    except Exception as e:
        print(f"Database Connection Error: {e}")

    # Logging
    logging.basicConfig(level=logging.INFO)

    # Register ALL Blueprints
    try:
        from routes.auth import bp as auth_bp
        app.register_blueprint(auth_bp)

        from routes.admin import bp as admin_bp
        app.register_blueprint(admin_bp)

        from routes.dashboard import bp as main_bp
        app.register_blueprint(main_bp)

        from routes.video import bp as video_bp
        app.register_blueprint(video_bp)

        from routes.live import live_bp
        app.register_blueprint(live_bp)

        try:
            from routes.anomaly import bp as anomaly_bp
            app.register_blueprint(anomaly_bp, url_prefix='/anomaly')
        except ImportError as e:
            print(f"Skipping anomaly routes: {e}")

        try:
            from routes.subscription import bp as subscription_bp
            app.register_blueprint(subscription_bp)
        except ImportError as e:
            print(f"Skipping subscription routes: {e}")

        try:
            from routes.support import bp as support_bp
            app.register_blueprint(support_bp)
        except ImportError as e:
            print(f"Skipping support routes: {e}")

        try:
            from routes.analytics import bp as analytics_bp
            app.register_blueprint(analytics_bp)
        except ImportError as e:
            print(f"Skipping analytics routes: {e}")

        try:
            from routes.api import bp as api_bp
            app.register_blueprint(api_bp, url_prefix='/api')
        except ImportError as e:
            print(f"Skipping API routes: {e}")

        try:
            from routes.features import bp as features_bp
            app.register_blueprint(features_bp)
        except ImportError as e:
            print(f"Skipping features routes: {e}")

        try:
            from routes.admin import bp as admin_bp
            app.register_blueprint(admin_bp, url_prefix='/admin')
        except ImportError as e:
            print(f"Skipping admin routes: {e}")

    except Exception as e:
        print(f"Error registering blueprints: {e}")
        import traceback
        traceback.print_exc()

    return app