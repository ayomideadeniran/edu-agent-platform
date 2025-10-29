import requests
from flask import Flask, render_template, request, jsonify
from datetime import datetime

# --- CONFIGURATION ---
# The Student Agent's external endpoint
# Earlier versions posted to /submit which the ASGI server treats as the
# uAgents envelope path. The Student Agent exposes a REST handler at /ui, so
# use that for the Flask -> Student REST integration.
STUDENT_AGENT_SUBMIT_ENDPOINT = "http://127.0.0.1:8000/ui"
STUDENT_AGENT_RECENT_ENDPOINT = "http://127.0.0.1:8000/recent_outputs"

app = Flask(__name__)


@app.route('/recent_fetch', methods=['GET', 'POST'])
def recent_fetch():
    """Proxy endpoint that fetches recent outputs from the Student Agent and returns them to the browser.

    The Student Agent exposes `/recent_outputs` which accepts an empty POST and returns
    the recent outputs. We forward that here to avoid cross-origin or direct client
    calls to the agent port.
    """
    try:
        resp = requests.post(STUDENT_AGENT_RECENT_ENDPOINT, json={})
        try:
            body = resp.json()
        except Exception:
            body = {"outputs": resp.text}
        return jsonify(body)
    except Exception as e:
        app.logger.exception(f"recent_fetch: failed to fetch recent outputs: {e}")
        return jsonify({"outputs": []}), 500

@app.route('/')
def index():
    """Renders the main simple UI page."""
    return render_template('index.html')


# In app.py



@app.route('/submit_input', methods=['POST'])
def submit_input():
    """Captures input from the web form or JSON and sends it to the Student Agent as JSON."""
    # Robustly accept JSON and form submissions and try raw body as fallback.
    user_input = None
    try:
        data = request.get_json(silent=True)
        app.logger.debug(f"submit_input: parsed JSON -> {data}")
        if data and isinstance(data, dict):
            user_input = data.get('user_input') or data.get('text')
    except Exception as e:
        app.logger.debug(f"submit_input: request.get_json failed: {e}")

    # Fallback to form/query params
    if not user_input:
        user_input = request.form.get('user_input') or request.form.get('text') or request.values.get('user_input') or request.values.get('text')

    # Last resort: raw body parsing
    if not user_input:
        try:
            raw = request.get_data(as_text=True)
            app.logger.debug(f"submit_input: raw body -> {raw}")
            if raw:
                import json as _json
                try:
                    parsed = _json.loads(raw)
                    if isinstance(parsed, dict):
                        user_input = parsed.get('user_input') or parsed.get('text')
                except Exception:
                    # If raw isn't JSON, treat it as plain text input
                    user_input = raw.strip()
        except Exception as e:
            app.logger.debug(f"submit_input: failed to read raw body: {e}")

    if not user_input or not str(user_input).strip():
        app.logger.warning(f"submit_input: empty input received. headers={dict(request.headers)}")
        return jsonify({"status": "error", "message": "Input cannot be empty."}), 400

    try:
        # Send both keys to downstream so the Student Agent accepts either schema
        payload = {"text": user_input, "user_input": user_input}
        app.logger.info(f"Sending payload to student agent: {payload}")

        response = requests.post(
            STUDENT_AGENT_SUBMIT_ENDPOINT,
            json=payload,
            headers={'Content-Type': 'application/json'}
        )

        # Parse agent response body (if any) and include it in the UI response so
        # the user can see the agent's immediate acknowledgement or echo.
        agent_body = None
        try:
            agent_body = response.json()
        except Exception:
            try:
                agent_body = response.text
            except Exception:
                agent_body = None

        if response.status_code == 200:
            # Try to fetch recent outputs from the Student Agent so we can show
            # any important tutor responses that were printed to the student's
            # terminal (these are captured by the agent and exposed via
            # /recent_outputs).
            recent = None
            try:
                r = requests.post(STUDENT_AGENT_RECENT_ENDPOINT, json={})
                try:
                    recent_body = r.json()
                    recent = recent_body.get('outputs') if isinstance(recent_body, dict) else recent_body
                except Exception:
                    recent = r.text
            except Exception:
                recent = None

            return jsonify({
                "status": "success",
                "message": f"Input sent to Agent (Status 200 OK).",
                "agent_response": agent_body,
                "recent_outputs": recent,
            })
        else:
            agent_body = None
            try:
                agent_body = response.text
            except Exception:
                agent_body = '<unreadable response body>'
            return jsonify({
                "status": "error",
                "message": f"Agent rejected the input (Status {response.status_code}). Check student_agent logs.",
                "agent_response": agent_body,
                "recent_outputs": None
            }), response.status_code

    except requests.exceptions.ConnectionError:
        return jsonify({
            "status": "error",
            "message": "Error: Student Agent is not running or endpoint is incorrect (check port 8000)."
        }), 503
    except Exception as e:
        app.logger.exception(f"submit_input: unexpected error: {e}")
        return jsonify({"status": "error", "message": f"An unexpected error occurred: {e}"}), 500
if __name__ == '__main__':
    # Run the Flask app on a different port than the agents (e.g., 5000)
    app.run(port=5000, debug=True)