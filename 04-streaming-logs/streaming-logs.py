import json
import os
import random
import time
import uuid

from flask import Flask, Response, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

current_dir = os.path.dirname(os.path.abspath(__file__))

PROJECTS = ["frontend", "backend", "mobile-app", "data-service", "auth-service"]
STAGES = ["build", "test", "deploy", "rollback"]
ENVIRONMENTS = ["development", "staging", "production"]
STATUSES = ["SUCCESS", "FAILURE"]


def generate_ci_cd_event():
    return {
        "id": str(uuid.uuid4()),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "project": random.choice(PROJECTS),
        "stage": random.choice(STAGES),
        "environment": random.choice(ENVIRONMENTS),
        "status": random.choice(STATUSES),
        "duration": f"{random.randint(10, 300)}s",
    }


def event_stream():
    while True:
        event = generate_ci_cd_event()
        yield f"data: {json.dumps(event)}\n\n"
        # Genera un evento cada 3 segundos
        time.sleep(3)


@app.route("/stream")
def stream():
    return Response(event_stream(), mimetype="text/event-stream")


@app.route("/")
def index():
    return send_from_directory(current_dir, "index.html")


if __name__ == "__main__":
    app.run(debug=True, threaded=True)
