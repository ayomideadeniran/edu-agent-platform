from uagents import Model

# --- Knowledge Models ---

# Model used by the Student Agent to request a question from the Tutor Agent
class KnowledgeQuery(Model):
    subject: str
    level: str
    # Optional address of the original requester (Student Agent).
    reply_to: str = ""

# Model used by the Knowledge Agent to send the result back to the Tutor Agent
class KnowledgeResponse(Model):
    subject: str
    level: str
    topic: str
    question: str
    answer: str
    explanation: str
    # Optional address indicating which student the tutor should relay this response to.
    reply_to: str = ""


# --- NEW AI ASSESSMENT MODELS ---

class AssessmentRequest(Model):
    """
    Message sent from the Tutor Agent to the AI Assessment Agent
    containing the user's free-form challenges.
    """
    user_challenges: str

class AssessmentResponse(Model):
    """
    Structured recommendation returned from the AI Assessment Agent
    to the Tutor Agent.
    """
    recommendation_subject: str
    recommendation_level: str
    analysis_summary: str
    # Note: We rely on the Tutor Agent's PENDING_ASSESSMENT_SENDER state 
    # instead of a reply_to field here, as implemented in tutor_agent.py.
