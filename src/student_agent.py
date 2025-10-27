import sys
import os
import json
from datetime import datetime
from uuid import uuid4
import asyncio

# --- CRITICAL ABSOLUTE PATH FIX ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

# --- UAGENTS CORE IMPORTS ---
from uagents import Agent, Context, Protocol   
from uagents.setup import fund_agent_if_low
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)
# 🚀 NEW: Updated to import new structured content models
from models import KnowledgeQuery, KnowledgeResponse, AssessmentRequest, AssessmentRequestContent, RecommendationContent 


# --- AGENT SETUP ---
chat_proto = Protocol(spec=chat_protocol_spec)

# --- CONFIGURATION ---
TUTOR_AGENT_ADDRESS = None 
try:
    with open("tutor_address.txt", "r") as f:
        TUTOR_AGENT_ADDRESS = f.read().strip()
except FileNotFoundError:
    print("Tutor Agent address not found. Please run tutor_agent.py first.")

# --- AGENT SETUP ---
agent = Agent(
    name="student_agent",
    port=8000,
    seed="student_agent_seed_phrase",
    endpoint=["http://127.0.0.1:8000/submit"],
)

fund_agent_if_low(agent.wallet.address())


# --- STATE TRACKING (Global Variables) ---
# 0: Waiting for agent response
# 1: Waiting for subject selection (Main Menu)
# 1.5: Waiting for level selection
# 1.8: Waiting for challenge input (AI Assessment)
# 2: Waiting for question answer
# 3: Waiting for next action (after answer/feedback/history)
CURRENT_STATE = 0 
SUBJECT_OPTIONS = ["Math", "History", "Science", "English", "Geography", "Literature", "Physics", "Computer Science", "Art History"]
LEVEL_OPTIONS = ["Beginner", "Intermediate", "Advanced"] 
CURRENT_QUESTION_TEXT = ""
INPUT_TASK_STARTED = False 
TEMP_SUBJECT = None 
STUDENT_HISTORY = [] 


# --- HELPER FUNCTIONS ---

def create_text_chat(text: str) -> ChatMessage:
    """Creates a generic ChatMessage with a single content item."""
    return ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[TextContent(text=text)],
    )

def create_history_query(query: str) -> ChatMessage:
    """Uses a special TextContent string for the Tutor to parse History requests."""
    history_request_text = f"::HISTORY_REQUEST::{query}"
    return ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[TextContent(text=history_request_text)],
    )

# NOTE: create_assessment_request helper is no longer needed as we use the structured model directly in the input loop.


def print_menu():
    global CURRENT_STATE, SUBJECT_OPTIONS, LEVEL_OPTIONS
    print("\n" + "="*50)
    
    if CURRENT_STATE == 1: # Subject Selection/Main Menu
        print("Please choose a subject or option:")
        for i, subject in enumerate(SUBJECT_OPTIONS):
            print(f"  [{i+1}] {subject}")
            
        print("  [A] AI Assessment (Diagnostic)") 
        print("  [0] Check My History")
        print("  [q] Quit Session") 
        print("="*50)
        print("Enter choice (1-9, A, 0, or q): ", end="", flush=True) 

    elif CURRENT_STATE == 1.5: # Level Selection
        print("Please choose a difficulty level:")
        for i, level in enumerate(LEVEL_OPTIONS):
            print(f"  [{i+1}] {level}")
        print("  [q] Quit Session")
        print("="*50)
        print("Enter choice (1-3 or q): ", end="", flush=True)

    elif CURRENT_STATE == 1.8: # Challenge Input
        print("--- AI Assessment ---")
        print("Please describe your learning challenges in detail (e.g., 'I struggle with word order and sequencing in math'):")
        print("="*50)
        print("Enter challenges (or 'q' to cancel): ", end="", flush=True)

    elif CURRENT_STATE == 2: # Answer Input
        print(f"**Question:** {CURRENT_QUESTION_TEXT}")
        print("="*50)
        print("Enter your answer (or 'q' to quit): ", end="", flush=True)
    
    elif CURRENT_STATE == 3: # Next Action
        print("What would you like to do next?")
        print("  [1] Select New Subject/Level")
        print("  [0] Check My History")
        print("  [q] Quit Session") 
        print("="*50)
        print("Enter choice (1, 0, or q): ", end="", flush=True)

    elif CURRENT_STATE == 0:
        print("Waiting for agent response...")


# --- ASYNCHRONOUS USER INPUT TASK ---

async def user_input_task(ctx: Context):
    global CURRENT_STATE, SUBJECT_OPTIONS, LEVEL_OPTIONS, TEMP_SUBJECT, agent
    
    await asyncio.sleep(1) 

    print("Hello! Welcome to the agent education platform.")
    CURRENT_STATE = 1 
    print_menu()
    
    while True:
        try:
            text = await asyncio.to_thread(input)
            
            if not text.strip():
                print_menu()
                continue

            text = text.strip() 
            text_upper = text.upper() # Use upper for comparison

            # --- QUIT HANDLING ---
            if text_upper == 'Q':
                print("\n[SYSTEM] Session terminated. Shutting down student agent...")
                sys.exit(0) 
                return

            # --- Handle Input Based on Current State ---
            
            if CURRENT_STATE == 1: # Subject Selection/Main Menu
                if text_upper == '0':
                    await ctx.send(TUTOR_AGENT_ADDRESS, create_history_query("check my history"))
                    CURRENT_STATE = 0 
                    print(f"\n[SYSTEM] Sending request for history...")
                
                # Check for AI Assessment option ('A')
                elif text_upper == 'A':
                    CURRENT_STATE = 1.8 # Move to the new state
                    print_menu()

                else:
                    try:
                        choice_index = int(text) - 1
                        if 0 <= choice_index < len(SUBJECT_OPTIONS): 
                            TEMP_SUBJECT = SUBJECT_OPTIONS[choice_index]
                            CURRENT_STATE = 1.5
                            print_menu()
                        else:
                            print("[SYSTEM] Invalid choice. Please enter a number from the menu (1-9), 'A', '0', or 'q'.")
                            print_menu()
                    except ValueError:
                        print("[SYSTEM] Invalid input. Please enter a number, 'A', '0', or 'q'.")
                        print_menu()

            elif CURRENT_STATE == 1.5: # Level Selection
                try:
                    choice_index = int(text) - 1
                    if 0 <= choice_index < len(LEVEL_OPTIONS): 
                        level = LEVEL_OPTIONS[choice_index]
                        subject = TEMP_SUBJECT
                        
                        ctx.logger.info(f"User chose subject: {subject} and level: {level}")
                        
                        # Send the query as a simple text message with the format "Subject:Level"
                        message = f"{subject}:{level}"
                        await ctx.send(TUTOR_AGENT_ADDRESS, create_text_chat(message))
                        
                        CURRENT_STATE = 0 
                        TEMP_SUBJECT = None
                        print(f"\n[SYSTEM] Sending request for {subject} at {level} level...")
                    else:
                        print("[SYSTEM] Invalid choice. Please enter a number from the menu (1-3).")
                        print_menu()
                except ValueError:
                    print("[SYSTEM] Invalid input. Please enter a number or 'q'.")
                    print_menu()

            # 🚀 NEW: Handle structured AssessmentRequestContent
            elif CURRENT_STATE == 1.8:
                challenges = text # Capture the free-form text
                if not challenges.strip():
                    print("[SYSTEM] Please provide some challenges.")
                else:
                    ctx.logger.info(f"User submitted challenges for AI assessment: {challenges[:20]}...")
                    
                    # 1. Create the structured content
                    assessment_content = AssessmentRequestContent(text=challenges)
                    
                    # 2. Wrap the content in a ChatMessage
                    assessment_msg = ChatMessage(
                        timestamp=datetime.utcnow(),
                        msg_id=uuid4(),
                        content=[assessment_content] 
                    )

                    # 3. Send the message
                    await ctx.send(TUTOR_AGENT_ADDRESS, assessment_msg)
                    
                    CURRENT_STATE = 0 # Wait for the AI's response
                    print(f"\n[SYSTEM] Sending challenges for AI analysis...")


            elif CURRENT_STATE == 2: # Answer Input
                ctx.logger.info(f"User submitted answer: {text}")
                await ctx.send(TUTOR_AGENT_ADDRESS, create_text_chat(text))
                CURRENT_STATE = 0 
                print(f"\n[SYSTEM] Sending answer...")

            elif CURRENT_STATE == 3: # Next Action
                if text == '1':
                    CURRENT_STATE = 1
                    print_menu()
                elif text == '0':
                    await ctx.send(TUTOR_AGENT_ADDRESS, create_history_query("check my history"))
                    CURRENT_STATE = 0 
                    print(f"\n[SYSTEM] Sending request for history...")
                else:
                    print("[SYSTEM] Invalid choice. Please enter 1, 0, or 'q'.")
                    print_menu()
                    
            elif CURRENT_STATE == 0:
                print("[SYSTEM] Please wait for the agent's response...")


        except EOFError:
            ctx.logger.info("Input stream closed.")
            break
        except Exception as e:
            ctx.logger.error(f"Input task error: {e}")
            await asyncio.sleep(0.5)


# --- AGENT EVENTS ---

async def start_input_task_safely(ctx: Context):
    global INPUT_TASK_STARTED
    if not INPUT_TASK_STARTED:
        ctx.logger.info("Starting user input task *immediately* on agent startup...")
        asyncio.create_task(user_input_task(ctx))
        INPUT_TASK_STARTED = True

@agent.on_event("startup")
async def on_startup(ctx: Context):
    await send_initial_message(ctx)
    await start_input_task_safely(ctx)


async def send_initial_message(ctx: Context):
    """Initiates the conversation and session."""
    if not TUTOR_AGENT_ADDRESS:
        ctx.logger.error("Tutor Agent address is not set. Cannot start session.")
        return

    ctx.logger.info(f"Initiating new session with Tutor at {TUTOR_AGENT_ADDRESS}")
    start_msg = ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[StartSessionContent()],
    )
    await ctx.send(TUTOR_AGENT_ADDRESS, start_msg)


# --- CHAT PROTOCOL HANDLERS ---

@chat_proto.on_message(model=ChatMessage) 
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    global CURRENT_STATE, CURRENT_QUESTION_TEXT, STUDENT_HISTORY
    
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.utcnow(), acknowledged_msg_id=msg.msg_id))

    for item in msg.content:
        
        # 🚀 NEW: Handle the structured Recommendation Content (Highest Priority)
        if isinstance(item, RecommendationContent):
            
            # Print the Tutor's structured response clearly 
            print("\n" + "~"*50)
            print(f"**✅ AI Recommendation Received!**")
            print(f"**AI Analysis:** {item.analysis}")
            print(f"**Suggested Lesson:** {item.subject}: {item.level}")
            print(f"\n[TUTOR] To start this lesson, type the exact suggestion (e.g., '{item.subject}:{item.level}') or select a different option from the menu.")
            print("~"*50)
            
            CURRENT_STATE = 3 
            print_menu()
            return # Exit after processing recommendation
        
        # Existing TextContent handling (Lower Priority)
        if isinstance(item, TextContent):
            text = item.text
            ctx.logger.info(f"Text message from {sender}: {text}")

            # NOTE: The ::AI_RECOMMENDATION:: block has been removed as it's replaced by RecommendationContent.
            
            # --- Handle HISTORY PAYLOADS (Still using text for complexity) ---
            if text.startswith("::HISTORY_RESPONSE::"):
                json_data = text.replace("::HISTORY_RESPONSE::", "", 1)
                try:
                    # NOTE: This block is usually for history sent *from* Tutor, but we rely on local STUDENT_HISTORY.
                    pass 
                except json.JSONDecodeError:
                    ctx.logger.error("Failed to decode history data from Tutor Agent.")
                    print("\n[SYSTEM] Failed to display history due to data error.")
                
                CURRENT_STATE = 3 if CURRENT_QUESTION_TEXT else 1
                print_menu()
                return 

            elif text.startswith("::HISTORY_UPDATE::"):
                json_data = text.replace("::HISTORY_UPDATE::", "", 1)
                try:
                    parts = json_data.split("::")
                    history_json = parts[0]
                    feedback_text = parts[1].strip() if len(parts) > 1 else ""

                    history_entry = json.loads(history_json)
                    STUDENT_HISTORY.append(history_entry)

                    print("\n" + "~"*50)
                    print(f"[TUTOR] {feedback_text}") 
                    print("~"*50)

                    CURRENT_STATE = 3
                    print_menu()
                    return 

                except json.JSONDecodeError:
                    ctx.logger.error("Failed to decode history data from Tutor Agent.")
                
            elif text.startswith("History request acknowledged."):
                ctx.logger.info("Received history acknowledgment. Displaying local history.")
                
                print("\n" + "="*50)
                print("           TUTORING SESSION HISTORY")
                print("="*50)

                # 🌟 FIX START: Logic to display history
                if STUDENT_HISTORY:
                    for i, entry in enumerate(STUDENT_HISTORY, 1):
                        status = "✅ Correct" if entry.get('is_correct') else "❌ Incorrect"
                        print(f"\n--- Entry {i} ({status}) ---")
                        print(f"   Topic: {entry.get('topic', 'N/A')}")
                        print(f"   Question: {entry.get('question', 'N/A')[:60]}...")
                        print(f"   Your Answer: {entry.get('user_answer', 'N/A')}")
                        print(f"   Correct Answer: {entry.get('correct_answer', 'N/A')}")
                else:
                    print("\nNo tutoring history recorded yet in this session.")
                
                print("="*50 + "\n")
                # 🌟 FIX END

                CURRENT_STATE = 3 if CURRENT_QUESTION_TEXT else 1
                print_menu()
                return 
                
            # --- General Text Handler (Question, Acknowledgement, Error) ---
            print("\n" + "~"*50)
            print(f"[TUTOR] {text}") 
            print("~"*50)

            if "Question:" in text:
                CURRENT_STATE = 2 
                question_start = text.find("Question:") + 10 
                CURRENT_QUESTION_TEXT = text[question_start:].strip()
                
            elif "That is **correct**" in text or "That is **incorrect**" in text:
                # Fallback, should be handled by ::HISTORY_UPDATE::
                CURRENT_STATE = 3
                
            else:
                CURRENT_STATE = 1 
            
            print_menu()
            
    return None

@chat_proto.on_message(model=ChatAcknowledgement)
async def handle_acknowledgement(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(
        f"Received acknowledgement from {sender} for message {msg.acknowledged_msg_id}"
    )
    return None



# --- MAIN EXECUTION ---
agent.include(chat_proto, publish_manifest=True) # 🚀 Ensure publish_manifest=True for ASI:One

if __name__ == "__main__":
    with open("student_address.txt", "w") as f:
        f.write(agent.address)
    
    agent.run()