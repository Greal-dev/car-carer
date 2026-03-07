from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Conversation, Message
from app.schemas.chat import ChatRequest, ChatResponse, ConversationOut, MessageOut
from app.services.agent import chat
from app.services.alert_chat import alert_chat

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def send_message(req: ChatRequest, db: Session = Depends(get_db)):
    # Get or create conversation
    if req.conversation_id:
        conv = db.get(Conversation, req.conversation_id)
        if not conv:
            raise HTTPException(404, "Conversation non trouvee")
    else:
        conv = Conversation(vehicle_id=req.vehicle_id, title=req.message[:80])
        db.add(conv)
        db.commit()
        db.refresh(conv)

    # Save user message
    user_msg = Message(conversation_id=conv.id, role="user", content=req.message)
    db.add(user_msg)
    db.commit()

    # Build message history for agent
    history = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at)
        .all()
    )
    messages = [{"role": m.role, "content": m.content} for m in history]

    # Call agent
    try:
        response_text = chat(messages=messages, vehicle_id=conv.vehicle_id, db=db)
    except Exception as e:
        response_text = f"Erreur de l'assistant: {e}"

    # Save assistant message
    assistant_msg = Message(conversation_id=conv.id, role="assistant", content=response_text)
    db.add(assistant_msg)
    db.commit()

    return ChatResponse(message=response_text, conversation_id=conv.id)


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(vehicle_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(Conversation)
    if vehicle_id is not None:
        query = query.filter(Conversation.vehicle_id == vehicle_id)
    convs = query.order_by(Conversation.updated_at.desc()).all()

    results = []
    for c in convs:
        msg_count = db.query(Message).filter(Message.conversation_id == c.id).count()
        results.append(ConversationOut(
            id=c.id,
            vehicle_id=c.vehicle_id,
            title=c.title,
            created_at=c.created_at,
            updated_at=c.updated_at,
            message_count=msg_count,
        ))
    return results


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def get_messages(conversation_id: int, db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(404, "Conversation non trouvee")
    return (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
        .all()
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: int, db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(404, "Conversation non trouvee")
    db.delete(conv)
    db.commit()


class AlertChatRequest(BaseModel):
    vehicle_id: int
    alert: dict
    messages: list[dict]  # [{"role": "user"/"assistant", "content": "..."}]


class AlertChatResponse(BaseModel):
    message: str


@router.post("/alert", response_model=AlertChatResponse)
def chat_about_alert(req: AlertChatRequest, db: Session = Depends(get_db)):
    """Chat with GPT-4o-mini about a specific alert/defect."""
    response = alert_chat(
        vehicle_id=req.vehicle_id,
        alert=req.alert,
        messages=req.messages,
        db=db,
    )
    return AlertChatResponse(message=response)
