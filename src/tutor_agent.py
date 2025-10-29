import json
import sys
import os
from datetime import datetime
from uuid import uuid4
from uagents import Agent, Context, Protocol, Model
from uagents.setup import fund_agent_if_low

# 🚀 NEW: Updated to import all structured content models
from models import (
    KnowledgeQuery, 
    KnowledgeResponse, 
    AssessmentRequest, 
    AssessmentResponse,
    AssessmentRequestContent,
    RecommendationContent      
)

# Import necessary components for handling the Student Agent's generic ChatMessage
from uagents_core.contrib.protocols.chat import (
    ChatMessage,
    TextContent,
    ChatAcknowledgement,
    StartSessionContent,
    chat_protocol_spec
)

# --- CRITICAL ABSOLUTE PATH FIX ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)


# --- AGENT SETUP ---
AGENT_NAME = "tutor_agent"
agent = Agent(
    name=AGENT_NAME,
    port=8001,
    seed=f"{AGENT_NAME}_seed_phrase",
    endpoint=[f"http://127.0.0.1:8001/submit"],
)

fund_agent_if_low(agent.wallet.address())

# Define protocols
tutor_protocol = Protocol(name="Tutor", version="0.1")
chat_proto = Protocol(spec=chat_protocol_spec)

# 🚫 FIX: REMOVED invalid chat_proto.add_model() calls.
# The correct way is to ensure all models are imported and included in the final manifest publish.

# --- GLOBAL VARIABLES & CONFIGURATION ---

KNOWLEDGE_AGENT_ADDRESS = None
try:
    with open("knowledge_address.txt", "r") as f:
        KNOWLEDGE_AGENT_ADDRESS = f.read().strip()
except FileNotFoundError:
    print("FATAL: knowledge_address.txt not found. Please run knowledge_agent.py first.")
    KNOWLEDGE_AGENT_ADDRESS = "" 

AI_ASSESSMENT_AGENT_ADDRESS_FILE = "ai_assessment_address.txt"
AI_ASSESSMENT_AGENT_ADDRESS = None
PENDING_ASSESSMENT_SENDER = None 

try:
    with open(AI_ASSESSMENT_AGENT_ADDRESS_FILE, "r") as f:
        AI_ASSESSMENT_AGENT_ADDRESS = f.read().strip()
    print(f"Loaded AI Assessment Agent address: {AI_ASSESSMENT_AGENT_ADDRESS}")
except FileNotFoundError:
    AI_ASSESSMENT_AGENT_ADDRESS = "agent1q..." 
    print("FATAL: ai_assessment_address.txt not found. Please run ai_assessment_agent.py first.")


PENDING_QUERY = {}
AVAILABLE_SUBJECTS = ["Math", "History", "Science"]
AVAILABLE_LEVELS = ["Beginner", "Intermediate"]


def load_local_curriculum():
    """Load curriculum from `curriculum.json` if present and normalize into lists."""
    global AVAILABLE_SUBJECTS, AVAILABLE_LEVELS
    try:
        with open('curriculum.json', 'r') as cf:
            data = json.load(cf)
        subjects_field = data.get('subjects')
        if isinstance(subjects_field, dict):
            AVAILABLE_SUBJECTS = list(subjects_field.keys())
            levels_set = set()
            for v in subjects_field.values():
                if isinstance(v, list):
                    levels_set.update(v)
            AVAILABLE_LEVELS = sorted(list(levels_set)) if levels_set else data.get('levels', AVAILABLE_LEVELS)
        elif isinstance(subjects_field, list):
            AVAILABLE_SUBJECTS = subjects_field
            AVAILABLE_LEVELS = data.get('levels', AVAILABLE_LEVELS)
        print(f"Loaded curriculum: subjects={AVAILABLE_SUBJECTS}, levels={AVAILABLE_LEVELS}")
    except FileNotFoundError:
        print("curriculum.json not found; using default curriculum lists")
    except Exception as e:
        print(f"Failed to load curriculum.json: {e}; using defaults")


load_local_curriculum()


# --- HELPER FUNCTIONS ---

def create_text_chat(text: str) -> ChatMessage:
    """Creates a generic ChatMessage with a single content item."""
    return ChatMessage(
        content=[TextContent(text=text)],
        timestamp=datetime.utcnow().isoformat(),
        msg_id=uuid4()
    )

# --- CHAT PROTOCOL HANDLERS ---

@chat_proto.on_message(model=ChatAcknowledgement)
async def handle_acknowledgement(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(f"Received acknowledgement from {sender} for message {msg.acknowledged_msg_id}")

@chat_proto.on_message(model=ChatMessage)
async def handle_student_chat_message(ctx: Context, sender: str, msg: ChatMessage):
    """
    Handles generic ChatMessages from the Student Agent (session start, curriculum query, answer submission, or assessment request).
    """
    global PENDING_QUERY, PENDING_ASSESSMENT_SENDER

    await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=msg.msg_id, timestamp=datetime.utcnow().isoformat()))

    for item in msg.content:
        
        # NEW: Check for structured Assessment Request Content
        if isinstance(item, AssessmentRequestContent):
            
            challenge_text = item.text
            
            # 1. Store state and sender
            PENDING_ASSESSMENT_SENDER = sender 
            
            # 2. Forward structured request to AI Assessment Agent
            assessment_msg = AssessmentRequest(user_challenges=challenge_text) # Use the text field
            await ctx.send(AI_ASSESSMENT_AGENT_ADDRESS, assessment_msg)
            
            ctx.logger.info(f"Forwarded structured assessment request to AI Agent.")
            
            # Inform the Student Agent that analysis is in progress
            await ctx.send(
                sender, 
                create_text_chat(f"[SYSTEM] Analyzing your challenges with the AI... This may take a moment.")
            )
            return


        # 1. Handle TextContent (Answer Submission, Query Submission, or History)
        if isinstance(item, TextContent):
            text = item.text.strip()
            ctx.logger.info(f"Received text message from Student Agent: {text}")

            if not text:
                return

            # --- Check for the Subject:Level pattern (a NEW CURRICULUM QUERY) (Existing) ---
            if ":" in text and text.count(':') == 1:
                parts = text.split(":", 1)
                subject = parts[0].strip()
                level = parts[1].strip()

                PENDING_QUERY = {
                    'subject': subject,
                    'level': level,
                    'sender': sender
                }
                ctx.storage.set('last_student_query_addr', sender)
                ctx.logger.info("Query saved to PENDING_QUERY state.")
                return

            # --- Check for the Special History Command (::HISTORY_REQUEST::) (Existing) ---
            if text.startswith("::HISTORY_REQUEST::"):
                history_ack_msg = "History request acknowledged. Please check your Student Agent console for local history."
                await ctx.send(sender, create_text_chat(history_ack_msg))
                ctx.logger.info("Special History Command acknowledged.")
                return

            # --- Check for Assessment Request prefix (::ASSESSMENT_REQUEST::) ---
            if text.startswith("::ASSESSMENT_REQUEST::"):
                # Extract the free-form challenges text and forward as AssessmentRequest
                challenge_text = text.replace("::ASSESSMENT_REQUEST::", "", 1).strip()
                if not challenge_text:
                    await ctx.send(sender, create_text_chat("Please provide some details for the AI assessment."))
                    return

                # Store state and original sender so we can relay the response later
                PENDING_ASSESSMENT_SENDER = sender

                # Forward the structured AssessmentRequest model to the AI Assessment Agent
                try:
                    assessment_msg = AssessmentRequest(user_challenges=challenge_text)
                    await ctx.send(AI_ASSESSMENT_AGENT_ADDRESS, assessment_msg)
                    ctx.logger.info("Forwarded assessment request to AI Assessment Agent.")
                except Exception as e:
                    ctx.logger.error(f"Failed to forward assessment request: {e}")
                    await ctx.send(sender, create_text_chat("Sorry, I couldn't reach the AI Assessment Agent right now. Please try again later."))

                # Inform the student that analysis is in progress
                await ctx.send(sender, create_text_chat("[SYSTEM] Analyzing your challenges with the AI... This may take a moment."))
                return

            # --- Handle Answer Submission (GRADING) (Existing) ---
            user_answer = text
            user_answer_normalized = text.strip().lower()

            active_data_key = f"active_question_data_{sender}"
            active_data = ctx.storage.get(active_data_key)

            if active_data and active_data.get('question'):
                correct_answer = active_data.get('correct_answer', '').strip()
                correct_answer_normalized = correct_answer.lower()
                topic = active_data.get('topic', 'N/A')
                explanation = active_data.get('explanation', '')

                is_correct = user_answer_normalized == correct_answer_normalized

                if is_correct:
                    feedback = "That is **CORRECT**! 🎉"
                else:
                    feedback = f"That is **INCORRECT**. The correct answer was **{correct_answer}**. 😔"
                
                if explanation:
                    feedback += f" **Hint/Explanation:** {explanation}"

                history_data = {
                    'topic': topic,
                    'question': active_data['question'],
                    'user_answer': user_answer,
                    'correct_answer': correct_answer,
                    'is_correct': is_correct
                }

                display_message = f"{feedback} Please select a new subject/level from the menu to continue your lesson."
                history_payload = f"::HISTORY_UPDATE::{json.dumps(history_data)}::{display_message}"

                await ctx.send(sender, create_text_chat(history_payload))
                ctx.logger.info(f"Answer received and graded. Sent history payload.")

                ctx.storage.set(active_data_key, None) 
            
            else:
                confirmation_text = "Input received, but no active question was found. Please select a new subject/level from the menu to start a lesson."
                await ctx.send(sender, create_text_chat(confirmation_text))
                ctx.logger.info(f"Input received and acknowledged: {text}")

            return

    # 2. Handle StartSessionContent (initial message)
    if any(isinstance(c, StartSessionContent) for c in msg.content):
        welcome_msg = "Welcome to the Agent Education Platform! Please select a subject and level to begin."
        await ctx.send(sender, create_text_chat(welcome_msg))
        return

# --- AI ASSESSMENT RESPONSE HANDLER (NEW) ---

@tutor_protocol.on_message(model=AssessmentResponse)
async def handle_assessment_response(ctx: Context, sender: str, msg: AssessmentResponse):
    """
    Handles the structured recommendation from the AI Assessment Agent.
    """
    global PENDING_ASSESSMENT_SENDER
    
    if sender != AI_ASSESSMENT_AGENT_ADDRESS or PENDING_ASSESSMENT_SENDER is None:
        ctx.logger.warning(f"Received unexpected AssessmentResponse from {sender}. Ignoring.")
        return
    
    student_address = PENDING_ASSESSMENT_SENDER
    PENDING_ASSESSMENT_SENDER = None 

    # --- VALIDATION CHECK ---
    recommended_subject = msg.recommendation_subject
    recommended_level = msg.recommendation_level
    original_summary = msg.analysis_summary
    
    if recommended_subject not in AVAILABLE_SUBJECTS or recommended_level not in AVAILABLE_LEVELS:
        recommended_subject = "Science"
        recommended_level = "Beginner"
        
        final_summary = (
            f"The AI suggested a topic ({msg.recommendation_subject}:{msg.recommendation_level}) "
            f"which is not currently available in the curriculum. Defaulting to: **Science: Beginner**.\n"
            f"Original AI Summary: {original_summary}"
        )
        ctx.logger.warning("AI suggested unsupported subject. Falling back to default.")
    else:
        final_summary = original_summary 
    # -----------------------------------------------

    # Send recommendation as a TextContent with a prefix so Student Agent (and other
    # generic ChatProtocol clients) can parse it without requiring custom content models.
    try:
        payload = {
            'subject': recommended_subject,
            'level': recommended_level,
            'analysis': final_summary
        }
        recommendation_text = f"::AI_RECOMMENDATION::{json.dumps(payload)}"
        await ctx.send(student_address, create_text_chat(recommendation_text))
        ctx.logger.info(f"Relayed AI recommendation to Student as text: {recommended_subject}:{recommended_level}")
    except Exception as e:
        ctx.logger.error(f"Failed to send AI recommendation to student: {e}")
        # Fallback: send a plain human-readable message
        fallback = (
            f"AI Recommendation: {recommended_subject}:{recommended_level}. {final_summary}"
        )
        await ctx.send(student_address, create_text_chat(fallback))


# --- KNOWLEDGE AGENT COMMUNICATION (INTERVAL & HANDLER) (Existing) ---

@agent.on_interval(period=1.0)
async def check_pending_query(ctx: Context):
    """Periodically checks if a student has requested a new question and forwards it."""
    global PENDING_QUERY, KNOWLEDGE_AGENT_ADDRESS
    if PENDING_QUERY and KNOWLEDGE_AGENT_ADDRESS:
        subject = PENDING_QUERY["subject"]
        level = PENDING_QUERY["level"]
        student_address = PENDING_QUERY["sender"]

        is_valid = subject in AVAILABLE_SUBJECTS and level in AVAILABLE_LEVELS

        if is_valid:
            ctx.logger.info(f"Forwarding query for {subject} ({level}) to Knowledge Agent at {KNOWLEDGE_AGENT_ADDRESS}")

            try:
                await ctx.send(KNOWLEDGE_AGENT_ADDRESS, KnowledgeQuery(subject=subject, level=level))
            except Exception as e:
                ctx.logger.error(f"Failed to send KnowledgeQuery to {KNOWLEDGE_AGENT_ADDRESS}: {e}")
                await ctx.send(student_address, create_text_chat("Sorry, I couldn't reach the Knowledge Agent right now. Please try again later."))
                PENDING_QUERY = {}
                return

            ctx.storage.set("last_student_query_addr", student_address)
            PENDING_QUERY = {} 
        else:
            error_msg = f"Sorry, the curriculum for {subject}:{level} is not available."
            await ctx.send(student_address, create_text_chat(error_msg))
            ctx.logger.error(error_msg)
            PENDING_QUERY = {}


@tutor_protocol.on_message(model=KnowledgeResponse, replies=None)
async def handle_knowledge_response(ctx: Context, sender: str, msg: KnowledgeResponse):
    """Receives a question from the Knowledge Agent and relays it to the Student Agent."""

    student_address = ctx.storage.get('last_student_query_addr')
    if not student_address:
        ctx.logger.warning(f"Received KnowledgeResponse from {sender} but no pending student address. Ignoring.")
        return

    # Store the active question data for the student for grading later
    active_data_key = f"active_question_data_{student_address}"
    ctx.storage.set(active_data_key, {
        'question': msg.question,
        'correct_answer': msg.answer,
        'topic': msg.topic,
        'explanation': msg.explanation
    })

    # Relay the question to the student agent via the Chat Protocol
    question_text = f"Subject: {msg.subject} ({msg.level}, {msg.topic})\nQuestion: {msg.question}\nPlease provide your answer."
    await ctx.send(student_address, create_text_chat(question_text))
    ctx.logger.info(f"Question relayed to student: {student_address}")


# --- MAIN EXECUTION ---
# Ensure both protocols are included. publish_manifest=True is crucial for ASI:One visibility
agent.include(tutor_protocol)
agent.include(chat_proto, publish_manifest=True) 

if __name__ == "__main__":
    with open("tutor_address.txt", "w") as f:
        f.write(agent.address)
    
    agent.run()