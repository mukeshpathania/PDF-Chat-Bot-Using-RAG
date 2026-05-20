from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from upload.upload import router as upload_router
from query.query import router as query_router


app = FastAPI()

app.include_router(upload_router)
app.include_router(query_router)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def serve_frontend():
    return FileResponse("static/index.html")