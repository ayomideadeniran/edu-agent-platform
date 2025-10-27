from uagents import Model
# --- LINE 3 HAS BEEN REMOVED: from uagents.protocols.experimental.chat import Content # This line caused the error

# --- Knowledge Models ---

# Model used by the Student Agent to request a question from the Tutor Agent
class KnowledgeQuery(Model):
    subject: str
    level: str
    reply_to: str = ""

# Model used by the Knowledge Agent to send the result back to the Tutor Agent
class KnowledgeResponse(Model):
    subject: str
    level: str
    topic: str
    question: str
    answer: str
    explanation: str
    reply_to: str = ""


# --- NEW AI ASSESSMENT MODELS ---

class AssessmentRequest(Model):
    user_challenges: str

class AssessmentResponse(Model):
    recommendation_subject: str
    recommendation_level: str
    analysis_summary: str


# --- NEW CHAT PROTOCOL CONTENT MODELS (Now inheriting directly from Model) ---

class AssessmentRequestContent(Model): # 🚀 FIX: Inherits from Model
    """
    A structured content model for the AI Assessment request.
    This replaces the custom '::ASSESSMENT_REQUEST::' string parsing.
    """
    text: str 
    type: str = "assessment_request" # CRITICAL: This field identifies the message type

class RecommendationContent(Model): # 🚀 FIX: Inherits from Model
    """
    A structured content model for relaying the final AI recommendation.
    This replaces the custom '::AI_RECOMMENDATION::' string parsing.
    """
    subject: str
    level: str
    analysis: str
    type: str = "ai_recommendation" # CRITICAL: This field identifies the message type