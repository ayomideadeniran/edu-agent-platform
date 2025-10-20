from datetime import datetime
from uuid import uuid4
import re  # Added for simple regex/string parsing
from uagents import Agent, Context, Protocol
from uagents.setup import fund_agent_if_low
from uagents_core.contrib.protocols.chat import (
   ChatAcknowledgement,
   ChatMessage,
   EndSessionContent,
   StartSessionContent,
   TextContent,
   chat_protocol_spec,
)

# Import the Knowledge Protocol message types (assuming you have them defined)
# NOTE: Replace 'knowledge_protocol_messages' with your actual file name if different
try:
    from knowledge_protocol_messages import KnowledgeQuery, KnowledgeResponse
except ImportError:
    print("WARNING: knowledge_protocol_messages.py not found. Using placeholder classes.")
    class KnowledgeQuery:
        def __init__(self, student_address, subject, query):
            self.student_address = student_address
            self.subject = subject
            self.query = query
    class KnowledgeResponse:
        def __init__(self, student_address, result):
            self.student_address = student_address
            self.result = result

# --- CONFIGURATION ---
AGENT_MAILBOX_KEY = "tutor_agent_mailbox"

agent = Agent(
    name="tutor_agent",
    port=8001,
    seed="tutor_agent_seed_phrase",
    endpoint=["http://127.0.0.1:8001/submit"],
    mailbox=AGENT_MAILBOX_KEY,
)

# Attempt to fund the agent (errors here are usually ignorable in this setup)
fund_agent_if_low(agent.wallet.address())

chat_proto = Protocol(spec=chat_protocol_spec)

# Safely load the knowledge address
try:
    with open("knowledge_address.txt", "r") as f:
        KNOWLEDGE_AGENT_ADDRESS = f.read().strip()
except FileNotFoundError:
    KNOWLEDGE_AGENT_ADDRESS = None

# --- HELPER FUNCTIONS ---

def create_text_chat(text: str, end_session: bool = False) -> ChatMessage:
    content = [TextContent(type="text", text=text)]
    if end_session:
        content.append(EndSessionContent())
    return ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=content,
    )

async def send_lesson(ctx: Context, student_address: str, student_text: str):
    # 🌟 MODIFIED: Only query the Knowledge Agent, do NOT send a placeholder response.
    # The response will be handled *after* the Knowledge Agent replies.
    
    # Get the student's stored subject (retrieved during handle_message)
    student_data = ctx.storage.get(student_address) or {"subject": "Math"}
    subject = student_data.get("subject", "Math")
    
    # 1. QUERY KNOWLEDGE AGENT
    knowledge_query = KnowledgeQuery(
        student_address=student_address, 
        subject=subject, 
        # Pass the full text so the Knowledge Agent can check for level updates
        query=student_text 
    )
    
    # Check for the address before sending
    if not KNOWLEDGE_AGENT_ADDRESS:
        ctx.logger.error("Cannot send query: KNOWLEDGE_AGENT_ADDRESS is not set.")
        return

    await ctx.send(KNOWLEDGE_AGENT_ADDRESS, knowledge_query)
    ctx.logger.info(f"Sent knowledge query to {KNOWLEDGE_AGENT_ADDRESS} for student {student_address}")

    # The conversation halts here until handle_knowledge_response is triggered.


# --- AGENT EVENT HANDLERS ---

@agent.on_event("startup")
async def setup_agent(ctx: Context):
    if not KNOWLEDGE_AGENT_ADDRESS:
        ctx.logger.error("Knowledge Agent address not found. Please ensure it's running first.")
        # NOTE: The main execution block below will set a placeholder if the file is missing
        return

# -------------------------------------------------------------
# HANDLERS FOR CHAT PROTOCOL (Student Agent Communication)
# -------------------------------------------------------------

@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    # Always send acknowledgement first
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.utcnow(), acknowledged_msg_id=msg.msg_id))

    for item in msg.content:
        # Marks the start of a chat session
        if isinstance(item, StartSessionContent):
            ctx.logger.info(f"Session started with {sender}")
            # Ensure student has a data entry if starting a new session
            if not ctx.storage.get(sender):
                 ctx.storage.set(sender, {"subject": "Unknown", "level": "Unknown"})

        # Handles plain text messages (from student agent)
        elif isinstance(item, TextContent):
            ctx.logger.info(f"Text message from {sender}: {item.text}")
            
            # --- DYNAMIC SUBJECT/LEVEL EXTRACTION LOGIC (Keep this to pre-process data) ---
            text_lower = item.text.lower()
            subject = None
            
            # Use regex to find a subject after "start with" or "continue with"
            match = re.search(r'(?:start with|continue with)\s+([a-zA-Z]+)', text_lower)
            
            if match:
                subject = match.group(1).capitalize()
            
            # If a message contains a subject or level change, process and store it
            if subject or any(word in text_lower for word in ["level", "advanced", "beginner"]):
                # Load student data
                student_data = ctx.storage.get(sender) or {"subject": "Unknown", "level": "Unknown"}
                
                # Check for explicit level change (e.g., "my level is advanced now")
                level_match = re.search(r'my level is\s+([a-zA-Z]+)', text_lower)
                if level_match:
                    student_data["level"] = level_match.group(1).capitalize()
                    ctx.logger.info(f"Updated {sender}'s internal level to: {student_data['level']}")
                
                # Update the current subject only if it was explicitly requested
                if subject and ("start with" in text_lower or "continue with" in text_lower):
                    student_data["subject"] = subject
                    ctx.logger.info(f"Set {sender}'s subject to: {subject}")
                
                # Save the updated data
                ctx.storage.set(sender, student_data)
            
            # Proceed to send the lesson response (which now only sends a query)
            await send_lesson(ctx, sender, item.text)

        # Marks the end of a chat session
        elif isinstance(item, EndSessionContent):
            ctx.logger.info(f"Session ended with {sender}")
        # Catches anything unexpected
        else:
            ctx.logger.info(f"Received unexpected content type from {sender}")

@chat_proto.on_message(ChatAcknowledgement)
# Use 'def' to avoid the non-critical TypeError you were seeing previously
def handle_acknowledgement( 
    ctx: Context, sender: str, msg: ChatAcknowledgement
):
    ctx.logger.info(
        f"Received acknowledgement from {sender} for message {msg.acknowledged_msg_id}"
    )

# -------------------------------------------------------------
# HANDLERS FOR KNOWLEDGE PROTOCOL (Knowledge Agent Communication)
# -------------------------------------------------------------

# tutor_agent.py

# tutor_agent.py (Only changes in handle_knowledge_response are shown)

# -------------------------------------------------------------
# HANDLERS FOR KNOWLEDGE PROTOCOL (Knowledge Agent Communication)
# -------------------------------------------------------------

@agent.on_message(model=KnowledgeResponse, replies={ChatMessage, ChatAcknowledgement})
async def handle_knowledge_response(ctx: Context, sender: str, msg: KnowledgeResponse):
    ctx.logger.info(f"Received personalized knowledge response from {sender} for student {msg.student_address}")
    
    # 1. Parse the result dictionary from the Knowledge Agent
    result_data = msg.result
    
    # Extract the necessary fields
    subject = result_data.get("subject", "Unknown Subject")
    level = result_data.get("level", "Unknown")
    suggested_topic = result_data.get("suggested_topic", "General Review")

    # 2. Formulate the final, personalized ChatMessage
    response_text = (
        f"Hello, Tutor here! The Knowledge Agent reports your current **{subject}** "
        f"proficiency is **{level}**. Based on that, let's start with the topic: **{suggested_topic}**."
    )
    
    # 3. Send the final message back to the Student Agent
    tutor_response = create_text_chat(response_text)
    await ctx.send(msg.student_address, tutor_response)
    ctx.logger.info(f"Sent personalized lesson: '{response_text}' to {msg.student_address}")

    # 4. CRITICAL FIX: Send a ChatAcknowledgement back to the Knowledge Agent (sender)
    # This completes the message transport handshake.
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.utcnow(), acknowledged_msg_id=uuid4())) 
    
    # 🌟 NEW FIX: Explicitly return None to ensure the framework doesn't try to 
    # await an invalid return object from the handler function.
    return None # <--- THIS LINE IS THE FIX


# --- MAIN EXECUTION ---
agent.include(chat_proto, publish_manifest=True)

if __name__ == "__main__":
    # Ensure the knowledge address is available or save a placeholder
    if not KNOWLEDGE_AGENT_ADDRESS:
        print("\nWARNING: knowledge_address.txt not found. Using a dummy address.")
        KNOWLEDGE_AGENT_ADDRESS = "agent1q0n0gf3nm2mevkj6mm45cmjvm3sx23glx38sdmn4kjmw8xm4stn2q600dnq" # Use an arbitrary address

    # Save the tutor address for the student agent to use
    with open("tutor_address.txt", "w") as f:
        f.write(agent.address)
        
    agent.run()


