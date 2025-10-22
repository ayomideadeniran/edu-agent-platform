# protocols/knowledge.py

from uagents import Protocol
from uagents import Model

# --- Message Models for the Knowledge Agent Protocol ---

class KnowledgeQuery(Model):
    """
    Message sent by the Tutor Agent to query the Knowledge Agent for
    a student's proficiency level and next lesson topic.
    """
    student_addr: str
    subject: str
    new_level: str | None = None  # Used if the Tutor wants to update the level

class KnowledgeResponse(Model):
    """
    Message sent by the Knowledge Agent back to the Tutor Agent
    containing the student's information.
    """
    student_addr: str
    subject: str
    level: str
    topic: str

# --- Protocol Definition ---

# Initialize the protocol with the name of the protocol file (optional but good practice)
knowledge_protocol_spec = "knowledge"

knowledge_proto = Protocol(name=knowledge_protocol_spec)