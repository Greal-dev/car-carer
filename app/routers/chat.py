from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Conversation, Message, Vehicle
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse, ConversationOut, MessageOut
from app.services.agent import chat
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _get_user_vehicle_ids(db: Session, user: User) -> list[int]:
    """Return list of vehicle IDs belonging to the user."""
    return [v.id for v in db.query(Vehicle.id).filter(
        (Vehicle.user_id == user.id) | (Vehicle.user_id.is_(None))
    ).all()]


def _check_conversation_ownership(conv: Conversation, user: User, db: Session):
    """Raise 404 if conversation does not belong to a vehicle owned by the user."""
    if conv.vehicle_id is not None:
        vehicle = db.get(Vehicle, conv.vehicle_id)
        if not vehicle or (vehicle.user_id and vehicle.user_id != user.id):
            raise HTTPException(404, "Conversation non trouvee")


@router.post("", response_model=ChatResponse)
def send_message(req: ChatRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Get or create conversation
    if req.conversation_id:
        conv = db.get(Conversation, req.conversation_id)
        if not conv:
            raise HTTPException(404, "Conversation non trouvee")
        _check_conversation_ownership(conv, user, db)
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
def list_conversations(vehicle_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_vehicle_ids = _get_user_vehicle_ids(db, user)
    query = db.query(Conversation).filter(Conversation.vehicle_id.in_(user_vehicle_ids))
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
def get_messages(conversation_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(404, "Conversation non trouvee")
    _check_conversation_ownership(conv, user, db)
    return (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
        .all()
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(404, "Conversation non trouvee")
    _check_conversation_ownership(conv, user, db)
    db.delete(conv)
    db.commit()


