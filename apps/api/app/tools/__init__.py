from app.tools.catalog_tool import LOOKUP_PERMIT_CATALOG
from app.tools.fees import GET_FEE_TOTAL
from app.tools.timeline import CHECK_DEPENDENCIES, ESTIMATE_TIMELINE
from app.tools.web_verify import WEB_VERIFY

ALL_TOOLS = [LOOKUP_PERMIT_CATALOG, CHECK_DEPENDENCIES, ESTIMATE_TIMELINE, GET_FEE_TOTAL, WEB_VERIFY]

__all__ = [
    "ALL_TOOLS",
    "CHECK_DEPENDENCIES",
    "ESTIMATE_TIMELINE",
    "GET_FEE_TOTAL",
    "LOOKUP_PERMIT_CATALOG",
    "WEB_VERIFY",
]
