"""Chat agent using Claude SDK with tools for vehicle maintenance analysis."""

import logging

import anthropic
from sqlalchemy.orm import Session

from app.config import settings
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import TOOL_DEFINITIONS, execute_tool
from app.models import Vehicle

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _build_context(db: Session, vehicle_id: int | None, allowed_vehicle_ids: list[int] | None = None) -> str:
    """Build context about available vehicles for the system prompt.

    Args:
        db: Database session
        vehicle_id: Currently selected vehicle ID (or None)
        allowed_vehicle_ids: If provided, only show these vehicles (ownership filter)
    """
    if allowed_vehicle_ids is not None:
        vehicles = db.query(Vehicle).filter(Vehicle.id.in_(allowed_vehicle_ids)).all()
    else:
        vehicles = db.query(Vehicle).all()

    if not vehicles:
        return "\n\nAucun vehicule enregistre dans la base."

    lines = ["\n\nVehicules disponibles:"]
    for v in vehicles:
        marker = " (SELECTIONNE)" if v.id == vehicle_id else ""
        lines.append(f"  - ID {v.id}: {v.name} — {v.brand} {v.model} ({v.year or '?'}){marker}")

    if vehicle_id:
        lines.append(f"\nLa conversation porte sur le vehicule ID {vehicle_id}. Utilise cet ID dans tes appels d'outils.")
    else:
        lines.append("\nAucun vehicule selectionne. Demande a l'utilisateur quel vehicule l'interesse si necessaire.")

    return "\n".join(lines)


def chat(
    messages: list[dict],
    vehicle_id: int | None,
    db: Session,
    allowed_vehicle_ids: list[int] | None = None,
) -> str:
    """Run a chat turn with the agent. Handles tool use loop.

    Args:
        messages: Conversation history [{"role": "user"/"assistant", "content": "..."}]
        vehicle_id: Currently selected vehicle ID (or None)
        db: Database session
        allowed_vehicle_ids: If provided, restrict tools to these vehicle IDs only

    Returns:
        Assistant's text response
    """
    logger.info("Chat started — vehicle_id=%s, allowed_vehicles=%s, message_count=%d",
                vehicle_id, allowed_vehicle_ids, len(messages))

    system = SYSTEM_PROMPT + _build_context(db, vehicle_id, allowed_vehicle_ids)

    api_messages = []
    for msg in messages:
        api_messages.append({"role": msg["role"], "content": msg["content"]})

    # Agentic loop: keep calling until we get a text response (max 10 rounds)
    for round_num in range(10):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=system,
                tools=TOOL_DEFINITIONS,
                messages=api_messages,
            )
        except anthropic.APIError as e:
            logger.error("Anthropic API error (round %d): %s", round_num, e)
            return "Desolé, une erreur est survenue lors de la communication avec l'assistant. Veuillez reessayer."
        except Exception as e:
            logger.error("Unexpected error calling Anthropic API (round %d): %s", round_num, e, exc_info=True)
            return "Desolé, une erreur inattendue est survenue. Veuillez reessayer."

        # Collect all content blocks
        text_parts = []
        tool_uses = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        # If no tool calls, return the text
        if not tool_uses:
            logger.info("Chat completed — %d round(s), response length=%d",
                        round_num + 1, sum(len(t) for t in text_parts))
            return "\n".join(text_parts)

        # Add assistant response to messages (with tool use blocks)
        api_messages.append({"role": "assistant", "content": response.content})

        # Execute tools and add results
        tool_results = []
        for tu in tool_uses:
            try:
                result = execute_tool(tu.name, tu.input, db, allowed_vehicle_ids=allowed_vehicle_ids)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result,
                })
            except Exception as e:
                logger.error("Tool execution error — tool=%s, input=%s: %s", tu.name, tu.input, e, exc_info=True)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": f"Erreur lors de l'execution de l'outil: {e}",
                    "is_error": True,
                })

        api_messages.append({"role": "user", "content": tool_results})

    logger.warning("Chat exhausted max rounds (10) without final text response")
    return "Desolé, je n'ai pas pu terminer l'analyse. Veuillez reformuler votre question."
