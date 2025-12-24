def competitions_index_url(season: int) -> str:
    # This is intentionally generic. If KSÍ changes paths, we only update here.
    # We'll rely on extracting motnumer links from the HTML.
    return f"https://www.ksi.is/mot/?year={season}"
    
def competition_url(motnumer: str) -> str:
    return f"https://www.ksi.is/mot/stakt-mot/?motnumer={motnumer}"
