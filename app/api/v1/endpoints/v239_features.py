from app.api.v1.endpoints.v239.approval_builder import router as approval_builder_router
from app.api.v1.endpoints.v239.baselines import router as baselines_router
from app.api.v1.endpoints.v239.branding import router as branding_router

# Puedes agregar más routers de v239 aquí si es necesario

routers = [
    approval_builder_router,
    baselines_router,
    branding_router,
]
