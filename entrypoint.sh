#!/bin/bash

# --- Start all Agents in the background ---

# Start Knowledge Agent
python src/knowledge_agent.py &

# Start AI Assessment Agent
python src/ai_assessment_agent.py &

# Start Tutor Agent
python src/tutor_agent.py &

# Start Student Agent
python src/student_agent.py &

# Wait a moment for agents to start up and register on Agentverse
sleep 15


export PYTHONPATH=$PYTHONPATH:.

# --- Start the Flask App (Web Server) using Gunicorn ---
# Gunicorn is used instead of 'python app.py' for production reliability
# Replace 'app:app' with the appropriate module:instance reference for your Flask app
exec gunicorn --bind 0.0.0.0:5000 app:app