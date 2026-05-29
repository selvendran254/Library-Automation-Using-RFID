TRANSLATIONS = {
    "en": {
        "dashboard": "Dashboard",
        "messages": "Messages",
        "my_books": "My Books",
        "history": "History",
        "logout": "Logout",
        "welcome": "Hello",
        "click_chat": "Click any message to open chat",
        "no_messages": "No messages yet",
        "request_book": "Request a Book",
        "reserve_book": "Reserve a Book",
        "renew_membership": "Renew Membership",
    },
    "ta": {
        "dashboard": "டாஷ்போர்டு",
        "messages": "செய்திகள்",
        "my_books": "என் புத்தகங்கள்",
        "history": "வரலாறு",
        "logout": "வெளியேறு",
        "welcome": "வணக்கம்",
        "click_chat": "அரட்டை திறக்க செய்தியை கிளிக் செய்யவும்",
        "no_messages": "இன்னும் செய்திகள் இல்லை",
        "request_book": "புத்தகம் கோரு",
        "reserve_book": "புத்தகம் முன்பதிவு",
        "renew_membership": "உறுப்பினர் நீட்டிப்பு",
    },
}


def get_lang(session):
    lang = session.get("portal_lang", "en")
    return lang if lang in TRANSLATIONS else "en"


def t(key, lang="en"):
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, key)
