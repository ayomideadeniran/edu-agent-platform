from uagents import Agent, Context, Model, Protocol
from uagents.setup import fund_agent_if_low
from hyperon import MeTTa # <-- Only import what is needed



class KnowledgeQuery(Model):
    student_id: str
    topic: str

class KnowledgeUpdate(Model):
    student_id: str
    topic: str
    level: str

class KnowledgeResponse(Model):
    profile: dict

class PersonalizationEngine:
    def __init__(self):
        self.metta = MeTTa()
        self.load_initial_knowledge()

    def load_initial_knowledge(self):
        initial_metta_code = """
        (: Student Concept)
        (: Topic Concept)
        (: Skill Concept)
        (: Level Symbol)
        (: Knows (Student Topic Level) Level)
        (: Prefers (Student Topic) Topic)
        (= (IsAdvanced $student $topic) 
           (match &self (Knows $student $topic High) True))
        """
        self.metta.run(initial_metta_code)

    def update_student_profile(self, student_id: str, topic: str, level: str):
        pattern = self.metta.parse_single(f"(Knows {student_id} {topic} $level)")
        self.metta.space().remove_atoms(self.metta.space().query(pattern))
        new_atom = self.metta.parse_single(f"(Knows {student_id} {topic} {level})")
        self.metta.space().add_atom(new_atom)

    def get_personalization_data(self, student_id: str, topic: str):
        knows_pattern = self.metta.parse_single(f"(Knows {student_id} {topic} $level)")
        knows_results = self.metta.space().query(knows_pattern)
        
        current_level = "Unknown"
        if knows_results:
            knows_list = list(knows_results)
            if len(knows_list) > 0:
                level_atom = knows_list[0].get_bindings().get("level")
                if level_atom:
                    current_level = str(level_atom)

        advanced_query = self.metta.run(f"!(IsAdvanced {student_id} {topic})")
        is_advanced = advanced_query and advanced_query[0] and str(advanced_query[0][0]) == 'True'
        
        return {
            "current_level": current_level,
            "is_advanced": is_advanced
        }

agent = Agent(
    name="knowledge_agent",
    port=8002,
    seed="knowledge_agent_seed_phrase",
    endpoint=["http://127.0.0.1:8002/submit"],
)

fund_agent_if_low(agent.wallet.address())

knowledge_proto = Protocol("KnowledgeProtocol")
engine = PersonalizationEngine()

@knowledge_proto.on_message(KnowledgeQuery, replies=KnowledgeResponse)
async def handle_knowledge_query(ctx: Context, sender: str, msg: KnowledgeQuery):
    ctx.logger.info(f"Received knowledge query from {sender} for student {msg.student_id}")
    profile = engine.get_personalization_data(msg.student_id, msg.topic)
    await ctx.send(sender, KnowledgeResponse(profile=profile))

@knowledge_proto.on_message(KnowledgeUpdate)
async def handle_knowledge_update(ctx: Context, sender: str, msg: KnowledgeUpdate):
    ctx.logger.info(f"Updating knowledge for student {msg.student_id}")
    engine.update_student_profile(msg.student_id, msg.topic, msg.level)

agent.include(knowledge_proto, publish_manifest=True)

with open("knowledge_address.txt", "w") as f:
    f.write(agent.address)

if __name__ == "__main__":
    agent.run()