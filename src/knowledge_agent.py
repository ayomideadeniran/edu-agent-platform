import sys
import os
import random 
from uuid import uuid4
import re

# --- CRITICAL ABSOLUTE PATH FIX ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

# --- UAGENTS CORE IMPORTS ---
from uagents import Agent, Context
from uagents.setup import fund_agent_if_low
# Import the shared models
from models import KnowledgeQuery, KnowledgeResponse

# --- MeTTa IMPORTS ---
try:
    from hyperon import MeTTa
except ImportError:
    print("FATAL: 'hyperon' library not found. Please ensure you have run 'pip install hyperon' in the active venv.")
    sys.exit(1)


# --- GLOBAL MeTTa VARIABLES ---
METTA_ENGINE = None 
METTA_FILE = "curriculum.metta"


def _escape(s: str) -> str:
    """Escape double quotes and backslashes for safe insertion into MeTTa string literals."""
    if s is None:
        return ""
    return s.replace('\\', '\\\\').replace('"', '\\"')


def parse_metta_blocks(path: str):
    """Parse the curriculum.metta file into blocks (inner content of current-context or whole file).

    Returns a list of dicts: {subject, level, topic, qid, question, answer, explanation}
    """
    with open(path, 'r') as f:
        txt = f.read()

    blocks = []
    if '(current-context' in txt:
        idx = 0
        while True:
            start = txt.find('(current-context', idx)
            if start == -1:
                break
            depth = 0
            j = start
            found_end = False
            while j < len(txt):
                if txt[j] == '(':
                    depth += 1
                elif txt[j] == ')':
                    depth -= 1
                    if depth == 0:
                        inner = txt[start + len('(current-context'):j]
                        blocks.append(inner)
                        idx = j + 1
                        found_end = True
                        break
                j += 1
            if not found_end:
                blocks.append(txt[start + len('(current-context'):])
                break
    else:
        blocks = [txt]

    results = []
    for b in blocks:
        fs = re.search(r'\(:\s*subject\s*"([^"]+)"\)', b)
        fl = re.search(r'\(:\s*level\s*"([^"]+)"\)', b)
        ft = re.search(r'\(:\s*topic\s*"([^"]+)"\)', b)
        file_subject = fs.group(1) if fs else None
        file_level = fl.group(1) if fl else None
        file_topic = ft.group(1) if ft else None

        for qid, qtext in re.findall(r'\(has-question\s+([^\s]+)\s+"([^"]+)"\)', b):
            ansm = re.search(r'\(has-answer\s+%s\s+"([^"]+)"\)' % re.escape(qid), b)
            exm = re.search(r'\(has-explanation\s+%s\s+"([^"]+)"\)' % re.escape(qid), b)
            ans_text = ansm.group(1) if ansm else ""
            exp_text = exm.group(1) if exm else ""
            results.append({
                'subject': file_subject,
                'level': file_level,
                'topic': file_topic,
                'qid': qid,
                'question': qtext,
                'answer': ans_text,
                'explanation': exp_text,
            })

    return results


# --- AGENT SETUP ---
agent = Agent(
    name="knowledge_agent",
    port=8002,
    seed="knowledge_agent_seed_phrase",
    endpoint=["http://127.0.0.1:8002/submit"],
)

fund_agent_if_low(agent.wallet.address())

# ----------------------------------------------------------------------------------------------------------------------

# --- AGENT STARTUP EVENT: Load MeTTa Knowledge Base ---
@agent.on_event("startup")
async def load_metta_curriculum(ctx: Context):
    global METTA_ENGINE
    ctx.logger.info(f"Loading MeTTa knowledge base from {METTA_FILE}...")
    
    if not os.path.exists(METTA_FILE):
        ctx.logger.error(f"FATAL: Missing MeTTa Knowledge Base file: {METTA_FILE}.")
        await ctx.stop()
        sys.exit(1)

    try:
        METTA_ENGINE = MeTTa()
        with open(METTA_FILE, "r") as f:
            metta_code = f.read()
        METTA_ENGINE.run(metta_code) 
        ctx.logger.info("MeTTa Knowledge Base loaded successfully.")

        # --- ASSERT parsed blocks into the MeTTa engine (improves reliability of primary queries) ---
        try:
            parsed = parse_metta_blocks(METTA_FILE)
            if parsed:
                # group by subject/level/topic
                groups = {}
                for e in parsed:
                    key = (e.get('subject'), e.get('level'), e.get('topic'))
                    groups.setdefault(key, []).append(e)

                for (subj, lvl, top), entries in groups.items():
                    parts = []
                    if subj:
                        parts.append(f'(: subject "{_escape(subj)}")')
                    if lvl:
                        parts.append(f'(: level "{_escape(lvl)}")')
                    if top:
                        parts.append(f'(: topic "{_escape(top)}")')

                    seen_qids = set()
                    for ent in entries:
                        qid = ent.get('qid')
                        if not qid or qid in seen_qids:
                            continue
                        seen_qids.add(qid)
                        q = _escape(ent.get('question', ''))
                        a = _escape(ent.get('answer', ''))
                        ex = _escape(ent.get('explanation', ''))
                        parts.append(f'(has-question {qid} "{q}")')
                        parts.append(f'(has-answer {qid} "{a}")')
                        parts.append(f'(has-explanation {qid} "{ex}")')

                    assertion = '(current-context\n  ' + '\n  '.join(parts) + '\n)'
                    try:
                        METTA_ENGINE.run(assertion)
                        ctx.logger.info(f"Asserted MeTTa block for {subj}/{lvl}/{top}")
                    except Exception as ae:
                        ctx.logger.warning(f"Failed to assert MeTTa block for {subj}/{lvl}/{top}: {ae}")
                        ctx.logger.debug(f"Assertion attempted:\n{assertion}")
        except Exception as pe:
            ctx.logger.warning(f"Failed to parse-and-assert curriculum into MeTTa engine: {pe}")
        # --- Diagnostic: run quick checks to confirm facts were loaded as expected ---
        try:
            # 1) list all has-question facts
            test_qs = METTA_ENGINE.run('''
            (match
                (current-context)
                (has-question $id $q)
                (list $id $q)
            )
            ''')
            ctx.logger.info(f"MeTTa diagnostic - has-question facts: {test_qs}")

            # 2) run the exact subject/level query used by handlers for an early sanity check
            sample_query = f'''
            (match
                (current-context)
                (and
                    (: subject "Math")
                    (: level "Beginner")
                    (: topic $topic)
                    (has-question $q_id $q_text)
                    (has-answer $q_id $ans)
                    (has-explanation $q_id $exp)
                )
                (list $topic $q_text $ans $exp)
            )
            '''
            sample_results = METTA_ENGINE.run(sample_query)
            ctx.logger.info(f"MeTTa diagnostic - sample Math/Beginner query results: {sample_results}")
        except Exception as dex:
            ctx.logger.warning(f"MeTTa diagnostic check failed: {dex}")
    except Exception as e:
        ctx.logger.error(f"FATAL: Failed to load MeTTa Knowledge Base. Error: {e}")
        await ctx.stop()
        sys.exit(1)

# ----------------------------------------------------------------------------------------------------------------------

# --- MESSAGE HANDLERS: Query MeTTa ---
@agent.on_message(model=KnowledgeQuery, replies=KnowledgeResponse) # <-- Use shared model
async def handle_knowledge_query(ctx: Context, sender: str, msg: KnowledgeQuery):
    global METTA_ENGINE
    subject = msg.subject
    level = msg.level
    
    if METTA_ENGINE is None:
        ctx.logger.error("MeTTa engine is not initialized.")
        return 

    ctx.logger.info(f"Querying MeTTa for Subject: {subject}, Level: {level}")

    metta_query = f'''
    (match
        (current-context)
        (and
            (: subject "{subject}")
            (: level "{level}")
            (: topic $topic)
            (has-question $q_id $q_text)
            (has-answer $q_id $ans)
            (has-explanation $q_id $exp)
        )
        (list $topic $q_text $ans $exp)
    )
    '''
    
    results_list = METTA_ENGINE.run(metta_query)

    # Fallback: try a query without wrapping in (current-context) in case facts were asserted at top-level
    if not results_list:
        ctx.logger.info("MeTTa primary query returned no results — trying fallback query without (current-context)")
        fallback_query = f'''
        (match
            (and
                (: subject "{subject}")
                (: level "{level}")
                (: topic $topic)
                (has-question $q_id $q_text)
                (has-answer $q_id $ans)
                (has-explanation $q_id $exp)
            )
            (list $topic $q_text $ans $exp)
        )
        '''
        try:
            results_list = METTA_ENGINE.run(fallback_query)
            ctx.logger.info(f"MeTTa fallback query results: {results_list}")
        except Exception as e:
            ctx.logger.warning(f"MeTTa fallback query failed: {e}")

    # Final fallback: if MeTTa engine didn't return results, try a simple parser over the MeTTa file
    if not results_list:
        ctx.logger.info("MeTTa queries returned no results — attempting simple file-parse fallback on curriculum file.")
        try:
            import re
            request_subject = subject
            request_level = level
            parsed_results = []
            with open(METTA_FILE, 'r') as mf:
                txt = mf.read()

            # Extract (current-context ...) blocks using a balanced-paren scan; if none, treat whole file as single block
            blocks = []
            if '(current-context' in txt:
                idx = 0
                while True:
                    start = txt.find('(current-context', idx)
                    if start == -1:
                        break
                    # scan forward to find matching closing paren for this block
                    depth = 0
                    j = start
                    found_end = False
                    while j < len(txt):
                        if txt[j] == '(':
                            depth += 1
                        elif txt[j] == ')':
                            depth -= 1
                            if depth == 0:
                                # include inner content only (after the token)
                                inner = txt[start + len('(current-context'):j]
                                blocks.append(inner)
                                idx = j + 1
                                found_end = True
                                break
                        j += 1
                    if not found_end:
                        # unmatched — take the rest
                        blocks.append(txt[start + len('(current-context'):])
                        break
            else:
                blocks = [txt]

            for b in blocks:
                fs = re.search(r'\(:\s*subject\s*"([^"]+)"\)', b)
                fl = re.search(r'\(:\s*level\s*"([^"]+)"\)', b)
                ft = re.search(r'\(:\s*topic\s*"([^"]+)"\)', b)
                file_subject = fs.group(1) if fs else None
                file_level = fl.group(1) if fl else None
                file_topic = ft.group(1) if ft else None

                # find all question ids and texts in this block
                for qid, qtext in re.findall(r'\(has-question\s+([^\s]+)\s+"([^"]+)"\)', b):
                    ansm = re.search(r'\(has-answer\s+%s\s+"([^"]+)"\)' % re.escape(qid), b)
                    exm = re.search(r'\(has-explanation\s+%s\s+"([^"]+)"\)' % re.escape(qid), b)
                    ans_text = ansm.group(1) if ansm else ""
                    exp_text = exm.group(1) if exm else ""

                    # only include entries that match requested subject/level
                    if file_subject == request_subject and file_level == request_level:
                        parsed_results.append([file_topic or "", qtext, ans_text, exp_text])

            results_list = [[r] for r in parsed_results]  # keep same structure as METTA results
            ctx.logger.info(f"File-parse fallback produced: {results_list}")
        except Exception as e:
            ctx.logger.warning(f"File-parse fallback failed: {e}")
    
    all_relevant_questions = []
    for result_set in results_list:
        for item in result_set:
            if isinstance(item, list) and len(item) == 4:
                all_relevant_questions.append(item)
    
    if not all_relevant_questions:
        ctx.logger.warning(f"No content found in MeTTa for Subject: {subject}, Level: {level}")
        # Send a generic error response using the shared model
        await ctx.send(
            sender, 
            KnowledgeResponse(
                subject=subject,
                level=level, # <--- FIX 1: Added 'level' here
                topic="Error", 
                question=f"No questions available for {subject} at {level}.", 
                answer="", 
                explanation=""
            )
        )
        return

    selected_result = random.choice(all_relevant_questions)
    
    response = KnowledgeResponse(
        subject=subject,
        level=level, # <--- FIX 2: Added 'level' here
        topic=selected_result[0],
        question=selected_result[1],
        answer=selected_result[2],
        explanation=selected_result[3],
        reply_to=getattr(msg, 'reply_to', "")
    )
    
    ctx.logger.info(f"Sending response for Topic: {response.topic}")
    await ctx.send(sender, response)

# ----------------------------------------------------------------------------------------------------------------------

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    with open("knowledge_address.txt", "w") as f:
        f.write(agent.address)
    agent.run()