import json
import sys
import os
from datetime import datetime
from uagents import Agent, Context, Protocol, Model
from uagents.setup import fund_agent_if_low

# Import the shared models
# Ensure models.py defines KnowledgeQuery, KnowledgeResponse, AssessmentRequest, and AssessmentResponse
try:
    from models import KnowledgeQuery, KnowledgeResponse, AssessmentRequest, AssessmentResponse # <-- UPDATED
except ImportError:
    print("Error: models.py not found or doesn't contain required models.")
    sys.exit(1)

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

# --- GLOBAL VARIABLES & CONFIGURATION ---

# 1. Knowledge Agent Address (Existing)
KNOWLEDGE_AGENT_ADDRESS = None
try:
    with open("knowledge_address.txt", "r") as f:
        KNOWLEDGE_AGENT_ADDRESS = f.read().strip()
except FileNotFoundError:
    print("FATAL: knowledge_address.txt not found. Please run knowledge_agent.py first.")
    KNOWLEDGE_AGENT_ADDRESS = "" 

# 2. AI Assessment Agent Configuration (NEW)
AI_ASSESSMENT_AGENT_ADDRESS_FILE = "ai_assessment_address.txt"
AI_ASSESSMENT_AGENT_ADDRESS = None
PENDING_ASSESSMENT_SENDER = None  # State for tracking which student requested the assessment

try:
    with open(AI_ASSESSMENT_AGENT_ADDRESS_FILE, "r") as f:
        AI_ASSESSMENT_AGENT_ADDRESS = f.read().strip()
    print(f"Loaded AI Assessment Agent address: {AI_ASSESSMENT_AGENT_ADDRESS}")
except FileNotFoundError:
    AI_ASSESSMENT_AGENT_ADDRESS = "agent1q..." # Placeholder address for startup
    print("FATAL: ai_assessment_address.txt not found. Please run ai_assessment_agent.py first.")


# Global state to manage the conversation flow (used by on_interval)
PENDING_QUERY = {}

# Available curriculum (used for validation and AI constraints)
AVAILABLE_SUBJECTS = ["Math", "History", "Science"]
AVAILABLE_LEVELS = ["Beginner", "Intermediate"]


# --- HELPER FUNCTIONS ---

def create_text_chat(text: str) -> ChatMessage:
    """Creates a generic ChatMessage with a single content item."""
    return ChatMessage(
        content=[TextContent(text=text)],
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

    # 1. Acknowledge the message (always)
    await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=msg.msg_id, timestamp=datetime.utcnow()))

    for item in msg.content:
        if isinstance(item, TextContent):
            text = item.text.strip()
            ctx.logger.info(f"Received text message from Student Agent: {text}")

            if not text:
                return

            # --- NEW: Check for Assessment Request Command (::ASSESSMENT_REQUEST::) ---
            if text.startswith("::ASSESSMENT_REQUEST::"):
                challenge_text = text.split("::ASSESSMENT_REQUEST::", 1)[-1].strip()
                
                # 1. Store state and sender
                PENDING_ASSESSMENT_SENDER = sender 
                
                # 2. Forward structured request to AI Assessment Agent
                assessment_msg = AssessmentRequest(user_challenges=challenge_text)
                await ctx.send(AI_ASSESSMENT_AGENT_ADDRESS, assessment_msg)
                
                ctx.logger.info(f"Forwarded assessment request to AI Agent.")
                
                # Inform the Student Agent that analysis is in progress
                await ctx.send(
                    sender, 
                    create_text_chat(f"[SYSTEM] Analyzing your challenges with the AI... This may take a moment.")
                )
                return


            # --- 2. Check for the Subject:Level pattern (a NEW CURRICULUM QUERY) (Existing) ---
            if ":" in text and text.count(':') == 1:
                parts = text.split(":", 1)
                subject = parts[0].strip()
                level = parts[1].strip()

                # Store the data for the on_interval task to process
                PENDING_QUERY = {
                    'subject': subject,
                    'level': level,
                    'sender': sender
                }
                # Store the student sender for the response handler
                ctx.storage.set('last_student_query_addr', sender)
                ctx.logger.info("Query saved to PENDING_QUERY state.")
                return

            # --- 3. Check for the Special History Command (::HISTORY_REQUEST::) (Existing) ---
            if text.startswith("::HISTORY_REQUEST::"):
                # Acknowledge the command and prompt student to use menu
                history_ack_msg = "History request acknowledged. Please check your Student Agent console for local history."
                await ctx.send(sender, create_text_chat(history_ack_msg))
                ctx.logger.info("Special History Command acknowledged.")
                return

            # --- 4. Handle Answer Submission (GRADING) (Existing) ---
            # ... (Existing grading logic remains the same) ...

            user_answer = text
            user_answer_normalized = text.strip().lower()

            # 4a. Retrieve the active question data for this student
            active_data_key = f"active_question_data_{sender}"
            active_data = ctx.storage.get(active_data_key)

            if active_data and active_data.get('question'):
                # We have an active question for this student. Grade it.
                
                # Retrieve question details
                correct_answer = active_data.get('correct_answer', '').strip()
                correct_answer_normalized = correct_answer.lower()
                topic = active_data.get('topic', 'N/A')
                explanation = active_data.get('explanation', '')

                # --- GRADING LOGIC ---
                is_correct = user_answer_normalized == correct_answer_normalized

                if is_correct:
                    feedback = "That is **CORRECT**! 🎉"
                else:
                    # Provide the correct answer for learning
                    feedback = f"That is **INCORRECT**. The correct answer was **{correct_answer}**. 😔"
                
                if explanation:
                    feedback += f" **Hint/Explanation:** {explanation}"

                # --- HISTORY PAYLOAD CREATION ---
                history_data = {
                    'topic': topic,
                    'question': active_data['question'],
                    'user_answer': user_answer,
                    'correct_answer': correct_answer,
                    'is_correct': is_correct
                }

                # Format the message as a special payload for the Student Agent to parse
                display_message = f"{feedback} Please select a new subject/level from the menu to continue your lesson."
                history_payload = f"::HISTORY_UPDATE::{json.dumps(history_data)}::{display_message}"

                await ctx.send(sender, create_text_chat(history_payload))
                ctx.logger.info(f"Answer received and graded. Sent history payload.")

                # Clear the active question data after grading
                ctx.storage.set(active_data_key, None) 
            
            else:
                # Generic acknowledgment for submissions outside of an active question flow
                confirmation_text = "Input received, but no active question was found. Please select a new subject/level from the menu to start a lesson."
                await ctx.send(sender, create_text_chat(confirmation_text))
                ctx.logger.info(f"Input received and acknowledged: {text}")

            return

    # If the content was StartSessionContent (initial message)
    if any(isinstance(c, StartSessionContent) for c in msg.content):
        welcome_msg = "Welcome to the Agent Education Platform! Please select a subject and level to begin."
        await ctx.send(sender, create_text_chat(welcome_msg))
        return

# --- AI ASSESSMENT RESPONSE HANDLER (NEW) ---

@tutor_protocol.on_message(model=AssessmentResponse)
async def handle_assessment_response(ctx: Context, sender: str, msg: AssessmentResponse):
    """
    Handles the structured recommendation from the AI Assessment Agent.
    Includes validation logic as a safety net.
    """
    global PENDING_ASSESSMENT_SENDER
    
    # 1. Verify response is from the expected AI agent and we have a student waiting
    if sender != AI_ASSESSMENT_AGENT_ADDRESS or PENDING_ASSESSMENT_SENDER is None:
        ctx.logger.warning(f"Received unexpected AssessmentResponse from {sender}. Ignoring.")
        return
    
    student_address = PENDING_ASSESSMENT_SENDER
    PENDING_ASSESSMENT_SENDER = None # Clear state

    # --- 2. VALIDATION CHECK (Layer 2 Safety Net) ---
    recommended_subject = msg.recommendation_subject
    recommended_level = msg.recommendation_level
    original_summary = msg.analysis_summary
    
    if recommended_subject not in AVAILABLE_SUBJECTS or recommended_level not in AVAILABLE_LEVELS:
        # Fallback if the AI suggests an unsupported subject/level
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

    # 3. Format and send the recommendation back to the student
    recommendation_text = (
        f"**✅ AI Recommendation Received!**\n\n"
        f"**AI Analysis:** {final_summary}\n\n"
        f"**Suggested Lesson:** {recommended_subject}: {recommended_level}\n\n"
        f"To start this lesson, type the exact suggestion (e.g., '{recommended_subject}:{recommended_level}') or select a different option from the menu."
    )

    # We send a special command back so the Student Agent can identify and process this
    recommendation_command = f"::AI_RECOMMENDATION::{recommended_subject}:{recommended_level}::{recommendation_text}"

    await ctx.send(student_address, create_text_chat(recommendation_command))
    ctx.logger.info(f"Relayed AI recommendation (validated) to Student: {recommended_subject}:{recommended_level}")


# --- KNOWLEDGE AGENT COMMUNICATION (INTERVAL & HANDLER) (Existing) ---

@agent.on_interval(period=1.0)
async def check_pending_query(ctx: Context):
    """Periodically checks if a student has requested a new question and forwards it."""
    global PENDING_QUERY, KNOWLEDGE_AGENT_ADDRESS
    if PENDING_QUERY and KNOWLEDGE_AGENT_ADDRESS:
        subject = PENDING_QUERY["subject"]
        level = PENDING_QUERY["level"]
        student_address = PENDING_QUERY["sender"]

        # Validate query before sending
        is_valid = subject in AVAILABLE_SUBJECTS and level in AVAILABLE_LEVELS

        if is_valid:
            ctx.logger.info(f"Forwarding query for {subject} ({level}) to Knowledge Agent at {KNOWLEDGE_AGENT_ADDRESS}")

            # Use the dedicated KnowledgeQuery model
            await ctx.send(KNOWLEDGE_AGENT_ADDRESS, KnowledgeQuery(subject=subject, level=level))

            # Store the student's address in storage for the asynchronous reply handler
            ctx.storage.set("last_student_query_addr", student_address)

            PENDING_QUERY = {} # Clear the pending query after sending
        else:
            error_msg = f"Sorry, the curriculum for {subject}:{level} is not available."
            await ctx.send(student_address, create_text_chat(error_msg))
            ctx.logger.error(error_msg)
            PENDING_QUERY = {}


@tutor_protocol.on_message(model=KnowledgeResponse, replies=None)
async def handle_knowledge_response(ctx: Context, sender: str, msg: KnowledgeResponse):
    """Receives a question from the Knowledge Agent and relays it to the Student Agent."""

    # Retrieve the student address from storage (set by check_pending_query)
    student_address = ctx.storage.get('last_student_query_addr')

    if not student_address:
         ctx.logger.error("No student address found to relay KnowledgeResponse to.")
         return

    # 1. Store the question data for grading in the next turn
    # Ensure all expected fields are present in the response
    if msg.topic and msg.question and hasattr(msg, 'answer'):
        active_question_data = {
            'topic': msg.topic,
            'question': msg.question,
            'correct_answer': msg.answer, # Store the answer as provided for grading
            'explanation': getattr(msg, 'explanation', ''), # Store explanation if available
            'subject': msg.subject,
            'level': msg.level,
        }
        # Store using the student address as the key
        ctx.storage.set(f"active_question_data_{student_address}", active_question_data)

        # 2. Relay the question to the Student Agent
        question_text = f"Subject: {msg.subject} ({msg.topic})\nQuestion: {msg.question}"

        await ctx.send(
            student_address,
            create_text_chat(question_text)
        )
        ctx.logger.info(f"Successfully relayed knowledge response for {msg.subject}.")
    else:
        # Handle cases where the Knowledge Agent response is incomplete or an error
        error_text = f"Received incomplete data from Knowledge Agent for {msg.subject}:{msg.level}."
        ctx.logger.error(error_text + f" Response: {msg}")
        await ctx.send(
            student_address,
            create_text_chat(f"Sorry, there was an issue retrieving the question for {msg.subject}. Please try again.")
        )


# Register the protocols with the agent
agent.include(tutor_protocol)
agent.include(chat_proto)

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    with open("tutor_address.txt", "w") as f:
        f.write(agent.address)
    agent.run()