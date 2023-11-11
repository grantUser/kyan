from waitress import serve

from kyan import create_app

app = create_app()

if app.config["DEBUG"]:
    from werkzeug.debug import DebuggedApplication

    app.wsgi_app = DebuggedApplication(app.wsgi_app, True)

if __name__ == "__main__":
    serve(
        app,
        host="localhost",
        port=5000,
        threads=16,
    )
