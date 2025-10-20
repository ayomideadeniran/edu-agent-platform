from uagents_core.models import Model

# KnowledgeQuery is sent from Tutor Agent to Knowledge Agent
class KnowledgeQuery(Model):
    """
    Message sent to the Knowledge Agent to request student status for a subject.
    """
    student_address: str
    subject: str
    query: str # The text of the student's message (e.g., "I think my level is advanced now.")

# KnowledgeResponse is sent from Knowledge Agent back to Tutor Agent
class KnowledgeResponse(Model):
    """
    Message sent from the Knowledge Agent back to the Tutor Agent with personalized data.
    """
    student_address: str
    # 'result' is the dictionary containing the personalized data (level, topic, etc.)
    result: dict