"""
Routes de l'Assistant IA de l'onglet CV (assistant/chat.py) : lecture de la conversation (jamais
d'appel au modèle), envoi d'un message (un appel), annulation de la dernière modification faite
par l'assistant. Toute modification du CV passe par cvs.save_cv_document, comme dans l'éditeur.
"""

from pathlib import Path

from fastapi import APIRouter, Body, Depends

from api import cvs
from api.common import ApiError, profile_path
from assistant import chat
from candidate.profile import ProfileError, load_profile
from cv.document import DOCUMENT_FILE, CVDocumentError, load_document
from interview.files import read_json


router = APIRouter(prefix="/api/cvs")

# Un message à la fois par candidature : deux réponses ne s'entremêlent jamais dans la conversation
CHAT_LOCKS = cvs.CvLocks()


def assistant_model():
    """L'appel au modèle (assistant/chat.ask_model) ; remplacé par un faux dans les tests (pas de Claude)."""
    return chat.ask_model


def _editable_folder(cv_id: str, base: Path) -> Path:
    folder = cvs._cv_folder(cv_id, base)
    if not (folder / DOCUMENT_FILE).is_file():
        raise ApiError(409, "CV non modifiable", ["ce CV a été créé avant cv.json : l'assistant ne peut pas le modifier."])
    return folder


def _blocked(folder: Path, allow_changes: bool, base_updated_at) -> str | None:
    """Pourquoi l'assistant ne doit pas toucher au CV maintenant (modifications manuelles, autre version)."""
    if not allow_changes:
        return ("tu as des modifications non enregistrées dans « Modifier » : enregistre-les ou annule-les, "
                "puis redemande-moi.")
    if base_updated_at is not None and abs(cvs._summary(folder)["updated_at"] - float(base_updated_at)) > 1e-6:
        return "le CV a été modifié ailleurs depuis l'ouverture de la page : recharge-la, puis redemande-moi."
    return None


@router.get("/{cv_id}/assistant")
def read_conversation(cv_id: str, base: Path = Depends(cvs.applications_dir)):
    """La conversation enregistrée (vide au départ). Ne lance jamais le modèle."""
    return chat.public_view(chat.load_conversation(cvs._cv_folder(cv_id, base)))


@router.post("/{cv_id}/assistant/messages")
def send_message(cv_id: str, payload: dict = Body(...), path: Path = Depends(profile_path),
                 base: Path = Depends(cvs.applications_dir), rebuilder=Depends(cvs.cv_rebuilder),
                 model=Depends(assistant_model)):
    """
    Un message de l'utilisateur, la réponse de l'assistant et, s'il en a demandé, ses modifications
    du CV : appliquées seulement si elles sont valides, si le CV n'a pas de modification manuelle en
    attente (`allow_changes`) et s'il n'a pas changé depuis `base_updated_at`.
    """
    folder = _editable_folder(cv_id, base)
    text = str(payload.get("text") or "").strip()
    if not text:
        raise ApiError(422, "Message vide", ["écris un message pour l'assistant."])
    if len(text) > chat.MAX_USER_CHARS:
        raise ApiError(422, "Message trop long", [f"{chat.MAX_USER_CHARS} caractères au plus."])
    if not CHAT_LOCKS.try_acquire(cv_id):
        raise ApiError(409, "Réponse en cours", ["l'assistant répond déjà à un message pour ce CV."])
    try:
        try:
            profile = load_profile(path)
            doc = load_document(folder)
        except (ProfileError, CVDocumentError) as error:
            raise ApiError(409, "Données illisibles", [cvs._clean(p) for p in error.problems])
        conversation = chat.load_conversation(folder)
        offer = read_json(folder / "offer.json") or {}
        try:
            answer = model(doc, profile, offer, chat.recent_messages(conversation["messages"]), text)
        except RuntimeError as error:               # rien n'est enregistré : le message peut être renvoyé
            raise ApiError(502, "L'assistant n'a pas pu répondre", [cvs._clean(error)])

        changes = answer.get("changes") or []
        change, saved = None, None
        if changes:
            blocked = _blocked(folder, bool(payload.get("allow_changes")), payload.get("base_updated_at"))
            if blocked:
                change = {"status": "not_applied", "summary": [], "problems": [blocked]}
            else:
                try:
                    new_doc, summary = chat.apply_changes(doc, changes, profile, bool(answer.get("confirmed_removal")))
                    saved = cvs.save_cv_document(cv_id, folder, new_doc, path, rebuilder)
                    change = {"status": "applied", "summary": summary, "problems": []}
                except chat.ChangeError as error:
                    change = {"status": "not_applied", "summary": [], "problems": error.problems}
                except ApiError as error:           # validation, compilation, plus d'une page : CV précédent gardé
                    change = {"status": "failed", "summary": [],
                              "problems": [error.message, *error.problems]}

        reply = chat.new_message("assistant", str(answer.get("reply") or "").strip(), change)
        conversation["messages"] += [chat.new_message("user", text), reply]
        if saved is not None:
            conversation["undo"] = {"message_id": reply["id"], "before": doc, "after": saved["document"]}
        chat.save_conversation(folder, conversation)
        return {**chat.public_view(conversation), "saved": saved}
    finally:
        CHAT_LOCKS.release(cv_id)


@router.post("/{cv_id}/assistant/undo")
def undo_change(cv_id: str, payload: dict = Body(default={}), path: Path = Depends(profile_path),
                base: Path = Depends(cvs.applications_dir), rebuilder=Depends(cvs.cv_rebuilder)):
    """Rétablit le CV d'avant la dernière modification de l'assistant, s'il n'a pas changé depuis."""
    folder = _editable_folder(cv_id, base)
    conversation = chat.load_conversation(folder)
    undo = conversation.get("undo")
    if not undo:
        raise ApiError(409, "Rien à annuler", ["l'assistant n'a pas modifié ce CV depuis la dernière annulation."])
    blocked = _blocked(folder, bool(payload.get("allow_changes", True)), payload.get("base_updated_at"))
    if blocked:
        raise ApiError(409, "Annulation impossible", [blocked])
    if load_document(folder) != undo["after"]:
        raise ApiError(409, "Annulation impossible", [
            "le CV a été modifié depuis la dernière modification de l'assistant : l'annuler écraserait ces changements."])
    saved = cvs.save_cv_document(cv_id, folder, undo["before"], path, rebuilder)
    original = next((m for m in conversation["messages"] if m["id"] == undo["message_id"]), None)
    summary = ((original or {}).get("change") or {}).get("summary") or []
    conversation["messages"].append(chat.new_message(
        "assistant", "J'ai annulé ma dernière modification : le CV est revenu à la version précédente.",
        {"status": "undone", "summary": summary, "problems": []}))
    conversation["undo"] = None
    chat.save_conversation(folder, conversation)
    return {**chat.public_view(conversation), "saved": saved}
