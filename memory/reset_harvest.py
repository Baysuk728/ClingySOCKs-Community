# memory/reset_harvest.py
from src.db.session import get_session
from src.db.models import Conversation, Message
def force_reset_harvesting():
    print("🔄 Forcing a full re-harvest reset...")
    with get_session() as session:
        # 1. Reset ALL conversations for this agent to 'pending' and index to -1
        conversations = session.query(Conversation).all()
        
        for conv in conversations:
            print(f"  - Resetting progress for: {conv.title or conv.id}")
            conv.harvest_status = 'pending'
            conv.last_harvested_index = -1  # This forces it to read from message 0 again
        # 2. Clear the harvested flag on messages
        session.query(Message).update({"is_harvested": False})
        session.commit()
        print(f"✅ Reset complete. {len(conversations)} conversations are ready for re-harvest.")
if __name__ == "__main__":
    force_reset_harvesting()