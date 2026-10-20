"""
Serveur local qui relie l'interface (lovable-front-end) au pipeline Python.
Il ne contient pas de logique : il reçoit les demandes de l'interface et les
transmet à la candidature en cours (workflows/application_run.py).

Lancement :  python server.py   (puis ouvrir l'interface sur http://localhost:8080)
"""

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from workflows.application_run import ApplicationRun


app = FastAPI(title="Job application agent")

# L'interface tourne sur un autre port : on l'autorise à appeler ce serveur
app.add_middleware(
    CORSMiddleware,
    # localhost, 127.0.0.1, [::1] ou l'adresse réseau du Mac (affichée par « npm run dev »)
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|\[::1\]|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+):8080",
    allow_methods=["*"],
    allow_headers=["*"],
)

# Une seule candidature à la fois, gardée en mémoire
current: ApplicationRun | None = None


class NewApplication(BaseModel):
    url: str


def _current() -> ApplicationRun:
    if current is None:
        raise HTTPException(status_code=404, detail="Aucune candidature en cours.")
    return current


@app.post("/api/applications")
def create_application(body: NewApplication) -> dict:
    global current

    if current is not None and current.is_active():
        raise HTTPException(status_code=409, detail="Une candidature est déjà en cours.")

    current = ApplicationRun(body.url.strip())
    current.start()

    return {"id": current.id}


@app.get("/api/applications/current")
def get_current() -> dict:
    return _current().snapshot()


@app.post("/api/applications/current/retry")
def retry() -> dict:
    try:
        _current().retry()
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))
    return {}


@app.post("/api/applications/current/submitted")
def submitted() -> dict:
    _current().mark("submitted")
    return {}


@app.post("/api/applications/current/abandon")
def abandon() -> dict:
    _current().mark("abandoned")
    return {}


@app.get("/api/applications/current/cv.pdf")
def cv_pdf() -> FileResponse:
    run = _current()
    if run.pdf is None or not run.pdf.exists():
        raise HTTPException(status_code=404, detail="Le CV n'est pas encore prêt.")
    return FileResponse(run.pdf, media_type="application/pdf", filename=run.pdf.name)


class Answers(BaseModel):
    text: str


@app.post("/api/applications/current/continue")
def continue_() -> dict:
    try:
        _current().continue_()
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))
    return {}


@app.post("/api/applications/current/answers")
def answers(body: Answers) -> dict:
    try:
        _current().answer(body.text)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))
    return {}


# Étape suivante du projet : mettre l'onglet Chrome de la candidature au premier plan
@app.post("/api/applications/current/focus-chrome")
def focus_chrome() -> dict:
    raise HTTPException(status_code=501, detail="Pas encore disponible.")


if __name__ == "__main__":
    # 127.0.0.1 : le serveur n'est accessible que depuis ton Mac
    uvicorn.run(app, host="127.0.0.1", port=8000)
