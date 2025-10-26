# ai_assessment_agent.py (Live Gemini API Integration with Fallback)
import sys
import os
import json
from uagents import Agent, Context, Protocol
from uagents.setup import fund_agent_if_low
from models import AssessmentRequest, AssessmentResponse 
from typing import Dict, Any

# --- CRITICAL ABSOLUTE PATH FIX ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

# --- GEMINI IMPORTS & SETUP ---
try:
    from google import genai
    from google.genai import types
except ImportError:
    print("FATAL: 'google-genai' library not found. Please install with 'pip install google-genai'.")
    sys.exit(1)

# Initialize the Gemini Client. It relies on the GOOGLE_API_KEY environment variable.
# NOTE: The client initialization will still fail without a valid key,
# but we need this structure to define the try/except flow.
try:
    GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
    if not GOOGLE_API_KEY:
         raise ValueError("GOOGLE_API_KEY environment variable is not set.")

    GEMINI_CLIENT = genai.Client(api_key=GOOGLE_API_KEY)
    GEMINI_MODEL = 'gemini-2.5-flash' 
except Exception as e:
    # This exception block prevents the agent from starting if the key is bad/missing.
    # We will log the error but allow the script to continue to the main logic 
    # where the real API call failure will be handled gracefully.
    print(f"INFO: Failed to initialize Gemini Client at startup: {e}. Assuming local mock will be needed.")
    GEMINI_CLIENT = None
    GEMINI_MODEL = None
# ------------------------------------

# --- LOCAL MOCK FALLBACK FUNCTION ---
def determine_mock_recommendation(challenges: str, error_message: str) -> Dict[str, Any]:
    """
    Analyzes user challenges using keyword matching to generate a realistic mock recommendation
    when the Gemini API is unavailable.
    """
    
    # Define the possible subject and level names for structured output
    SUBJECTS = ["Math", "History", "Science"]
    LEVELS = ["Beginner", "Intermediate"]
    
    # Default recommendation
    recommended_subject = "History"
    recommended_level = "Beginner"
    
    challenges_lower = challenges.lower()
    
    # --- Logic 1: Dyslexia/Reading Challenges (Highest Priority) ---
    reading_keywords = ['letters', 'sound blends', 'phonetically', 'spelling', 'reading aloud', 'sight words', 'dyslexia', 'decode']
    if any(word in challenges_lower for word in reading_keywords):
        recommended_subject = "History" # Choose a low-reading-complexity subject
        recommended_level = "Beginner"
        summary = (
            "**Mock Analysis:** User challenges indicate core difficulties with **phonetic decoding** and **automatic word recognition** "
            "('sight words', 'stumble over simple words'), which strongly aligns with **dyslexic tendencies**. "
            "Recommending **Beginner History** to build literacy confidence using simplified, structured content, bypassing high-stakes reading."
        )
    
    # --- Logic 2: Math/Numeracy Challenges ---
    elif any(word in challenges_lower for word in ['numbers', 'calculate', 'equations', 'algebra', 'addition', 'subtraction', 'math']):
        recommended_subject = "Math"
        recommended_level = "Beginner"
        summary = (
            "**Mock Analysis:** Challenges are centered on **numerical concepts** and **calculation**. "
            "Recommending a **Beginner Math** course to reinforce foundational arithmetic and number sense."
        )

    # --- Logic 3: Science/Abstract/Factual Recall Challenges ---
    elif any(word in challenges_lower for word in ['facts', 'science', 'concepts', 'theory', 'lab']):
        recommended_subject = "Science"
        recommended_level = "Intermediate"
        summary = (
            "**Mock Analysis:** User is struggling with retaining and applying **scientific facts/concepts**. "
            "Recommending **Intermediate Science** with a focus on visual and interactive learning methods to aid memory."
        )

    # --- Logic 4: General/Vague Challenges (Default Fallback) ---
    else:
        summary = (
            "**Mock Analysis:** Challenges are general. Recommending **Beginner History** as a balanced starting point "
            "to work on general study habits and recall."
        )
        
    return {
        "subject": recommended_subject,
        "level": recommended_level,
        "analysis_summary": f"LOCAL FALLBACK TRIGGERED (API Error: {error_message}). {summary}"
    }
# ------------------------------------


# --- AGENT SETUP ---
AGENT_NAME = "ai_assessment_agent"
agent = Agent(
    name=AGENT_NAME,
    port=8003,
    seed=f"{AGENT_NAME}_seed_phrase",
    endpoint=[f"http://127.0.0.1:8003/submit"], 
)
fund_agent_if_low(agent.wallet.address())

# Define protocol
assessment_protocol = Protocol(name="Assessment", version="0.1")

# --- PROTOCOL HANDLER ---

@assessment_protocol.on_message(model=AssessmentRequest, replies=AssessmentResponse)
async def handle_assessment_request(ctx: Context, sender: str, msg: AssessmentRequest):
    ctx.logger.info(f"Received assessment request from {sender}. Challenges: {msg.user_challenges[:50]}...")
    
    user_challenges = msg.user_challenges
    recommendation_data = None # Initialize a variable to hold the final result data

    # 1. Define the System Instruction (AI's Persona and Goal) - Only needed for the API call
    SYSTEM_INSTRUCTION = (
        "You are an expert educational AI designed to diagnose learning difficulties based "
        "on a user's self-reported challenges. Your goal is to recommend the best **subject and "
        "level** to address their foundational deficits (e.g., if they have dyslexia, recommend "
        "'History:Beginner' or 'Science:Beginner' to build literacy with low-complexity content). "
        "Subjects are **Math, History, Science**. Levels are **Beginner, Intermediate**. " 
        "You **MUST** return a JSON object with the fields: 'subject', 'level', and 'analysis_summary'. "
        "Do not include any other text or markdown outside of the JSON block."
    )

    # 2. Define the User Prompt - Only needed for the API call
    prompt = (
        f"Analyze the user's reported learning challenges below and provide a recommendation. "
        f"User Challenges: \"{user_challenges}\" "
        f"Output JSON format MUST be: {{\"subject\": \"[Subject]\", \"level\": \"[Level]\", \"analysis_summary\": \"[Summary]\"}}"
    )
    

    try:
        if not GEMINI_CLIENT:
             # Force an error if the client failed to initialize at startup
             raise ValueError("Gemini Client not initialized due to bad/missing API key.")

        # 3. Call the Gemini API
        response = GEMINI_CLIENT.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION, 
                response_mime_type="application/json", 
                response_schema={"type": "object", "properties": {
                    "subject": {"type": "string", "enum": ["Math", "History", "Science"]}, 
                    "level": {"type": "string", "enum": ["Beginner", "Intermediate"]}, 
                    "analysis_summary": {"type": "string"}
                }}
            )
        )
        
        # 4. Parse the JSON output
        recommendation_data = json.loads(response.text)
        
        ctx.logger.info("Successfully received and parsed response from Gemini API.")


    except Exception as e:
        # 5. Fallback to the accurate local mock recommendation on failure
        error_message = f"{e.__class__.__name__}: {str(e)[:50]}..."
        ctx.logger.error(f"Gemini API failed. Running local mock fallback. Error: {error_message}")
        
        # Use the intelligent mock function here
        recommendation_data = determine_mock_recommendation(
            challenges=user_challenges, 
            error_message=error_message
        )


    # 6. Send the structured recommendation back to the Tutor Agent
    response = AssessmentResponse(
        recommendation_subject=recommendation_data.get("subject", "Science"),
        recommendation_level=recommendation_data.get("level", "Beginner"),
        analysis_summary=recommendation_data.get("analysis_summary", "Unknown analysis error.")
    )
    
    ctx.logger.info(f"Sending final recommendation: {response.recommendation_subject}:{response.recommendation_level}")
    await ctx.send(sender, response)

# Register the protocol with the agent
agent.include(assessment_protocol)

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    # Save the address for the tutor agent to read
    with open("ai_assessment_address.txt", "w") as f:
        f.write(agent.address)
    
    # We allow the agent to run even if GEMINI_CLIENT is None,
    # relying on the try/except block in the protocol handler.
    agent.run()