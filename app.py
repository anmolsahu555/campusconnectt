import os
from uuid import UUID

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from postgrest import APIError
from supabase import Client, create_client

load_dotenv()

app = Flask(__name__)

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_PUBLISHABLE_KEY")

if not supabase_url or not supabase_key:
    raise RuntimeError(
        "Missing Supabase configuration. Set SUPABASE_URL and "
        "SUPABASE_PUBLISHABLE_KEY in your .env file."
    )

supabase: Client = create_client(supabase_url, supabase_key)


def error(message: str, status: int):
    return jsonify({"error": message}), status


def request_user_id():
    """Read the temporary caller identity used while auth is disabled."""
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        return None, error("X-User-Id header is required while authentication is disabled.", 400)
    try:
        return str(UUID(user_id)), None
    except ValueError:
        return None, error("X-User-Id must be a valid UUID.", 400)


def fetch_event(event_id: str):
    try:
        event = supabase.table("events").select("*").eq("id", event_id).maybe_single().execute()
    except APIError as exc:
        return None, error(exc.message, 502)

    if not event.data:
        return None, error("Event not found.", 404)
    return event.data, None


@app.get("/")
def index():
    return jsonify({"service": "event-registration-api", "routes": "/api/events"})


@app.get("/api/events")
def list_events():
    try:
        response = supabase.table("events").select("*").order("title").execute()
        return jsonify(response.data)
    except APIError as exc:
        return error(exc.message, 502)


@app.get("/api/events/<event_id>")
def get_event(event_id: str):
    try:
        UUID(event_id)
    except ValueError:
        return error("event_id must be a valid UUID.", 400)

    event, failure = fetch_event(event_id)
    return failure or jsonify(event)


@app.post("/api/registrations")
def create_registration():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error("A JSON request body is required.", 400)

    event_id = payload.get("event_id")
    user_id = payload.get("user_id")
    if not event_id or not user_id:
        return error("event_id and user_id are required.", 400)

    try:
        event_id, user_id = str(UUID(event_id)), str(UUID(user_id))
    except ValueError:
        return error("event_id and user_id must be valid UUIDs.", 400)

    event, failure = fetch_event(event_id)
    if failure:
        return failure
    if event.get("status") != "published":
        return error("Registration is unavailable for this event.", 409)

    try:
        existing = (
            supabase.table("registrations")
            .select("id")
            .eq("event_id", event_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if existing.data:
            return error("User is already registered for this event.", 409)

        registrations = (
            supabase.table("registrations").select("id", count="exact").eq("event_id", event_id).execute()
        )
        if registrations.count is not None and registrations.count >= event["capacity"]:
            return error("This event is at capacity.", 409)

        created = (
            supabase.table("registrations")
            .insert({"event_id": event_id, "user_id": user_id})
            .execute()
        )
        return jsonify(created.data[0]), 201
    except APIError as exc:
        # A unique (event_id, user_id) constraint should also exist in the database.
        # PostgREST exposes PostgreSQL unique violations as SQLSTATE 23505.
        if getattr(exc, "code", None) == "23505":
            return error("User is already registered for this event.", 409)
        return error(exc.message, 502)


@app.get("/api/me/registrations")
def my_registrations():
    user_id, failure = request_user_id()
    if failure:
        return failure
    try:
        response = (
            supabase.table("registrations")
            .select("id, created_at, event:events(*)")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return jsonify(response.data)
    except APIError as exc:
        return error(exc.message, 502)


@app.get("/api/events/<event_id>/registrations")
def event_registrations(event_id: str):
    try:
        UUID(event_id)
    except ValueError:
        return error("event_id must be a valid UUID.", 400)

    user_id, failure = request_user_id()
    if failure:
        return failure

    event, failure = fetch_event(event_id)
    if failure:
        return failure
    if event["organizer_id"] != user_id:
        return error("Only the event organizer can view registrations.", 403)

    try:
        response = (
            supabase.table("registrations")
            .select("id, created_at, user:users(id, email, role)")
            .eq("event_id", event_id)
            .order("created_at")
            .execute()
        )
        return jsonify(response.data)
    except APIError as exc:
        return error(exc.message, 502)


@app.errorhandler(404)
def route_not_found(_error):
    return error("Route not found.", 404)


if __name__ == "__main__":
    app.run(debug=True)

