from uagents_core.models import Model

# Model used by the Student Agent to request a question from the Tutor Agent
class KnowledgeQuery(Model):
    subject: str
    level: str
    # Optional address of the original requester (Student Agent). Tutor sets this so
    # the Knowledge Agent can include it in the response for relaying.
    reply_to: str = ""

# Model used by the Knowledge Agent to send the result back to the Tutor Agent
class KnowledgeResponse(Model):
    subject: str
    level: str   # <--- FIX: This is the missing field!
    topic: str
    question: str
    answer: str
    explanation: str
    # Optional address indicating which student the tutor should relay this response to.
    reply_to: str = ""