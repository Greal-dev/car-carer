"""Lightweight GPT-4o-mini chat for discussing alerts and maintenance issues."""

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Vehicle

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-4o-mini"

SYSTEM_PROMPT = """Tu es un expert en mecanique automobile. L'utilisateur te pose des questions
sur une alerte ou un probleme detecte sur son vehicule.

VEHICULE : {vehicle_info}

ALERTE EN COURS DE DISCUSSION :
- Niveau : {alert_level}
- Titre : {alert_title}
- Detail : {alert_detail}

Ton role :
1. EXPLIQUER clairement le probleme en termes simples (causes possibles, mecanisme)
2. EVALUER l'impact : securite, risque de panne, degradation d'autres pieces
3. PRIORISER : est-ce urgent, peut-on attendre, quel delai raisonnable
4. ESTIMER un budget approximatif pour la reparation (fourchette en euros)
5. CONSEILLER sur les precautions a prendre en attendant la reparation

Regles :
- Reponds TOUJOURS en francais
- Sois pedagogique mais precis techniquement
- Donne des fourchettes de prix realistes pour le marche francais
- Si tu n'es pas sur de quelque chose, dis-le
- Adapte tes reponses au vehicule specifique (marque, modele, motorisation, km)"""


def _build_vehicle_info(db: Session, vehicle_id: int) -> str:
    v = db.get(Vehicle, vehicle_id)
    if not v:
        return "Vehicule inconnu"
    parts = [v.name or ""]
    if v.brand:
        parts.append(v.brand)
    if v.model:
        parts.append(v.model)
    if v.year:
        parts.append(f"({v.year})")
    if v.fuel_type:
        parts.append(f"- {v.fuel_type}")
    if v.plate_number:
        parts.append(f"- Plaque: {v.plate_number}")
    return " ".join(parts)


def alert_chat(
    vehicle_id: int,
    alert: dict,
    messages: list[dict],
    db: Session,
) -> str:
    """Chat with GPT-4o-mini about a specific alert.

    Args:
        vehicle_id: Vehicle ID for context
        alert: Alert dict with level, title, detail
        messages: Conversation history [{"role": "user"/"assistant", "content": "..."}]
        db: Database session

    Returns:
        Assistant response text
    """
    vehicle_info = _build_vehicle_info(db, vehicle_id)

    system = SYSTEM_PROMPT.format(
        vehicle_info=vehicle_info,
        alert_level=alert.get("level", "?"),
        alert_title=alert.get("title", "?"),
        alert_detail=alert.get("detail", "?"),
    )

    api_messages = [{"role": "system", "content": system}]
    for msg in messages:
        api_messages.append({"role": msg["role"], "content": msg["content"]})

    resp = httpx.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": api_messages,
            "max_tokens": 2048,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
