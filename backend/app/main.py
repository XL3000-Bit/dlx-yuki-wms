from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router
from app.core.config import settings

app=FastAPI(title=settings.app_name,version="3.0.0-phase7",debug=settings.debug)
app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins,allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
app.include_router(api_router,prefix=settings.api_v1_prefix)

@app.get("/health",tags=["System"])
def health()->dict[str,str]:return {"status":"ok","service":settings.app_name,"phase":"7"}
