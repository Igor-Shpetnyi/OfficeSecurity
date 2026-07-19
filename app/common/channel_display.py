def initials(name: str) -> str:
    letters = [c for c in name if c.isalnum()]
    return "".join(letters[:2]).upper() or "?"
