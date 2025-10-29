# Use a Python base image suitable for uAgents
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED 1
ENV FLASK_APP app.py

# Create the working directory
WORKDIR /usr/src/app

# Copy requirement files and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire source code into the container
COPY . .

# Expose ports for the Flask app and agents (adjust based on your agent ports)
EXPOSE 5000 8000 8001 8002 8003

# ... (after COPY . .)
# Make the entrypoint script executable
RUN chmod +x /usr/src/app/entrypoint.sh

# The default command when the container starts
# We use a wrapper script (entrypoint.sh) to start all agents and the Flask app
CMD ["/usr/src/app/entrypoint.sh"]


