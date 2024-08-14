import os
import random
import threading
import time
import uuid

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Simular instancias EC2
instances = {}


def simulate_ec2_launch(instance_id):
    states = ["pending", "pending", "pending", "running"]
    for state in states:
        instances[instance_id]["status"] = state
          # Simular tiempo tomado por cada stage de deploy EC2
        time.sleep(5)


@app.route("/launch_ec2", methods=["POST"])
def launch_ec2():
    instance_id = str(uuid.uuid4())
    instances[instance_id] = {"status": "pending", "ip_address": None}
    threading.Thread(target=simulate_ec2_launch, args=(instance_id,)).start()
    return jsonify({"instance_id": instance_id})


@app.route("/instance_status/<instance_id>", methods=["GET"])
def instance_status(instance_id):
    if instance_id not in instances:
        return jsonify({"error": "Instance not found"}), 404

    instance = instances[instance_id]
    if instance["status"] == "running" and instance["ip_address"] is None:
        instance["ip_address"] = f"192.168.0.{random.randint(1, 255)}"

    return jsonify({"status": instance["status"], "ip_address": instance["ip_address"]})


@app.route("/")
def serve_html():
    return send_from_directory(".", "index.html")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
