import sys
import os
import random 
import re

# --- CRITICAL ABSOLUTE PATH FIX ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

# --- UAGENTS CORE IMPORTS ---
from uagents import Agent, Context, Protocol
from uagents.setup import fund_agent_if_low
# Import the shared models
from models import KnowledgeQuery, KnowledgeResponse

# --- MeTTa IMPORTS ---
try:
    from hyperon import MeTTa, GroundedAtom, ExpressionAtom 
except ImportError:
    print("FATAL: 'hyperon' library not found. Please ensure you have run 'pip install hyperon' in the active venv.")
    sys.exit(1)


# --- GLOBAL MeTTa VARIABLES ---
METTA_ENGINE: MeTTa = None 
METTA_FILE = "curriculum.metta"
knowledge_protocol = Protocol(name="Knowledge", version="0.1")

# --- AGENT SETUP ---
agent = Agent(
    name="knowledge_agent",
    port=8002,
    seed="knowledge_agent_seed_phrase",
    endpoint=["http://127.0.0.1:8002/submit"],
)

fund_agent_if_low(agent.wallet.address())


# --- HELPER FUNCTIONS ---

def _escape(s: str) -> str:
    """Escape double quotes and backslashes for safe insertion into MeTTa string literals."""
    if s is None:
        return ""
    # Strip whitespace, then escape quotes and backslashes
    s = s.strip()
    return s.replace('\\', '\\\\').replace('\"', '\\\"')

# The file-parse fallback is no longer needed/supported with the simplified data format

def load_metta_kb(ctx: Context):
    """Initializes the MeTTa engine and loads the knowledge base."""
    global METTA_ENGINE
    
    METTA_ENGINE = MeTTa()
    ctx.logger.info(f"Loading MeTTa knowledge base from {METTA_FILE}...")

    try:
        with open(METTA_FILE, 'r') as f:
            METTA_ENGINE.run(f.read())
        
        ctx.logger.info("MeTTa Knowledge Base loaded successfully.")
        
        # --- DIAGNOSTIC CHECK (Using the new simple 'question' fact format) ---
        test_query_template = lambda subject, level: f'''
        !(match &self (question "{subject}" "{level}" $T $Q $A $E) ($T $Q $A $E))
        '''
        
        # Diagnostic check for 'History: Intermediate'
        history_results_raw = METTA_ENGINE.run(test_query_template("History", "Intermediate"))
        question_count = sum(len(result_set) for result_set in history_results_raw if isinstance(result_set, list))
        ctx.logger.info(f"MeTTa diagnostic - History/Intermediate found {question_count} questions.")
        
        # Diagnostic check for 'Science: Intermediate'
        science_results_raw = METTA_ENGINE.run(test_query_template("Science", "Intermediate"))
        question_count = sum(len(result_set) for result_set in science_results_raw if isinstance(result_set, list))
        ctx.logger.info(f"MeTTa diagnostic - Science/Intermediate found {question_count} questions.")


    except Exception as e:
        ctx.logger.error(f"FATAL: Failed to load MeTTa Knowledge Base: {e}")
        METTA_ENGINE = None

# --- AGENT EVENTS ---

@agent.on_event("startup")
async def on_startup(ctx: Context):
    load_metta_kb(ctx)


# --- KNOWLEDGE PROTOCOL HANDLER ---

@knowledge_protocol.on_message(model=KnowledgeQuery, replies=KnowledgeResponse)
async def handle_knowledge_query(ctx: Context, sender: str, msg: KnowledgeQuery):
    """Handles requests for questions based on subject and level."""
    global METTA_ENGINE
    
    # Aggressive String Cleaning
    subject = ''.join(c for c in msg.subject if c.isprintable()).strip()
    level = ''.join(c for c in msg.level if c.isprintable()).strip()

    ctx.logger.info(f"Querying MeTTa for Subject: {subject}, Level: {level}")
    
    all_relevant_questions = []

    if METTA_ENGINE:
        # --- NEW SIMPLE QUERY ---
        metta_query_template = f"""
        !(match &self (question "{_escape(subject)}" "{_escape(level)}" $T $Q $A $E) ($T $Q $A $E))
        """

        try:
            metta_results = METTA_ENGINE.run(metta_query_template)
            
            for result_set in metta_results:
                if isinstance(result_set, list):
                    for item in result_set:
                        python_list = []
                        if hasattr(item, 'get_children'):
                            for child in item.get_children():
                                # Robust Atom-to-Python String Conversion
                                extracted_value = None
                                if isinstance(child, GroundedAtom):
                                    extracted_value = str(child.get_object().content).strip()
                                elif hasattr(child, 'to_string'):
                                    extracted_value = child.to_string().strip('"').strip()
                                else:
                                    extracted_value = str(child).strip()
                                
                                python_list.append(extracted_value)
                            
                            if len(python_list) == 4:
                                all_relevant_questions.append(python_list)
            
            ctx.logger.info(f"MeTTa primary query successful. Found {len(all_relevant_questions)} questions.")

        except Exception as e:
            ctx.logger.error(f"Error during MeTTa query execution: {e}")
            
    if not all_relevant_questions:
        ctx.logger.warning(f"No content found for Subject: {subject}, Level: {level}")
        
        await ctx.send(
            sender, 
            KnowledgeResponse(
                subject=subject, 
                level=level, 
                topic="Error", 
                question=f"No questions available for {subject} at {level}.", 
                answer="", 
                explanation=""
            )
        )
        return

    # selected_result is now a standard Python list: [topic, question, answer, explanation]
    selected_result = random.choice(all_relevant_questions)
    
    response = KnowledgeResponse(
        subject=subject,
        level=level, 
        topic=selected_result[0],
        question=selected_result[1],
        answer=selected_result[2],
        explanation=selected_result[3],
        reply_to=getattr(msg, 'reply_to', "")
    )
    
    ctx.logger.info(f"Sending response for Topic: {response.topic}")
    await ctx.send(sender, response)

# ----------------------------------------------------------------------------------------------------------------------

# Register the protocol with the agent
agent.include(knowledge_protocol)

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    with open("knowledge_address.txt", "w") as f:
        f.write(agent.address)
    agent.run()





