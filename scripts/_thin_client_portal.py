"""Thin client_portal.py by replacing serializer function bodies."""
import ast, re as _re

with open("app/api/v1/endpoints/client_portal.py", encoding="utf-8") as f:
    src = f.read()

count = 0

# 1. _fr_out (ends just before @router.post("/feature-requests"))
match = _re.search(
    r'def _fr_out\(fr: FeatureRequest\) -> dict:.*?}\n\n\n@router\.post\("/feature-requests"',
    src, _re.DOTALL)
if match:
    src = (src[:match.start()]
           + 'def _fr_out(fr) -> dict:\n    return _svc.fr_out(fr)\n\n\n@router.post("/feature-requests"'
           + src[match.end():])
    count += 1; print("Replaced _fr_out")
else:
    print("WARNING: _fr_out not found")

# 2. _uat_out (ends just before @router.get("/uat"))
match2 = _re.search(
    r'def _uat_out\(s: UATSession\) -> dict:.*?}\n\n\n@router\.get\("/uat"',
    src, _re.DOTALL)
if match2:
    src = (src[:match2.start()]
           + 'def _uat_out(s) -> dict:\n    return _svc.uat_out(s)\n\n\n@router.get("/uat"'
           + src[match2.end():])
    count += 1; print("Replaced _uat_out")
else:
    print("WARNING: _uat_out not found")

# 3. _msg_out (ends just before @router.get("/messages"))
match3 = _re.search(
    r'def _msg_out\(m: ClientMessage\) -> dict:.*?}\n\n\n@router\.get\("/messages"',
    src, _re.DOTALL)
if match3:
    src = (src[:match3.start()]
           + 'def _msg_out(m) -> dict:\n    return _svc.msg_out(m)\n\n\n@router.get("/messages"'
           + src[match3.end():])
    count += 1; print("Replaced _msg_out")
else:
    print("WARNING: _msg_out not found")

# 4. _doc_out (ends just before @router.post("/documents"))
match4 = _re.search(
    r'def _doc_out\(d: ClientDocument\) -> dict:.*?}\n\n\n@router\.post\("/documents"',
    src, _re.DOTALL)
if match4:
    src = (src[:match4.start()]
           + 'def _doc_out(d) -> dict:\n    return _svc.doc_out(d)\n\n\n@router.post("/documents"'
           + src[match4.end():])
    count += 1; print("Replaced _doc_out")
else:
    print("WARNING: _doc_out not found")

# 5. _survey_out (ends just before @router.post("/surveys"))
match5 = _re.search(
    r'def _survey_out\(s: ClientSurvey\) -> dict:.*?}\n\n\n@router\.post\("/surveys"',
    src, _re.DOTALL)
if match5:
    src = (src[:match5.start()]
           + 'def _survey_out(s) -> dict:\n    return _svc.survey_out(s)\n\n\n@router.post("/surveys"'
           + src[match5.end():])
    count += 1; print("Replaced _survey_out")
else:
    print("WARNING: _survey_out not found")

with open("app/api/v1/endpoints/client_portal.py", "w", encoding="utf-8") as f:
    f.write(src)

print(f"\nTotal: {count}/5 replacements")
try:
    ast.parse(src)
    print("Syntax OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
