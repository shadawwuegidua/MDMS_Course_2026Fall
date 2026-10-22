"""MongoDB connection, collection validation and indexes."""

import json
from pathlib import Path

from flask import current_app
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import CollectionInvalid


def init_db(app):
    client = MongoClient(
        app.config["MONGO_URI"], serverSelectionTimeoutMS=5000, tz_aware=True
    )
    try:
        client.admin.command("ping")
        database = client[app.config["MONGO_DB"]]
        schema_path = Path(__file__).with_name("schema.json")
        schemas = json.loads(schema_path.read_text(encoding="utf-8"))
        existing = set(database.list_collection_names())
        for name, schema in schemas.items():
            if name not in existing:
                try:
                    database.create_collection(
                        name, validator={"$jsonSchema": schema},
                        validationLevel="strict", validationAction="error",
                    )
                except CollectionInvalid:
                    # Another process may have initialized the collection.
                    pass

        database.users.create_index(
            "username", unique=True, name="unique_username"
        )
        database.surveys.create_index(
            [("owner_id", ASCENDING), ("created_at", DESCENDING)],
            name="owner_surveys",
        )
        database.responses.create_index(
            [("survey_id", ASCENDING), ("submitted_at", DESCENDING)],
            name="survey_responses",
        )
        database.responses.create_index(
            [("survey_id", ASCENDING), ("respondent_id", ASCENDING)],
            unique=True, partialFilterExpression={"single_submission": True},
            name="one_response_per_user_when_required",
        )
    except Exception:
        client.close()
        raise

    app.extensions["mongo_client"] = client
    app.extensions["db"] = database


def get_db():
    return current_app.extensions["db"]
