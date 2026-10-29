from flask import Flask, request, jsonify
from pymongo import MongoClient
from datetime import datetime, timezone
import os

app = Flask(__name__)

MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
db = client.get_database(os.environ.get("MONGO_DB", "flask_db"))
collection = db.data

@app.get("/")
def index():
    return f"Welcome to the Flask app! The current time is: {datetime.now(timezone.utc).isoformat()}"

@app.route("/data", methods=["GET", "POST"])
def data():
    if request.method == "POST":
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Send a JSON object in the request body"}), 400
        try:
            collection.insert_one(payload)
            return jsonify({"status": "Data inserted"}), 201
        except Exception:
            app.logger.exception("MongoDB insert failed")
            return jsonify({"error": "Database operation failed"}), 503
    try:
        documents = list(collection.find({}, {"_id": 0}))
        return jsonify(documents), 200
    except Exception:
        app.logger.exception("MongoDB read failed")
        return jsonify({"error": "Database operation failed"}), 503

@app.get("/health")
def health():
    try:
        client.admin.command("ping")
        return jsonify({"status": "ok"}), 200
    except Exception:
        return jsonify({"status": "database_unavailable"}), 503

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
