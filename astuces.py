"""Trucs et astuces de Viki + mots-clés dans toutes les langues.
- ACTIONS : chaque action avec son titre (7 langues), une explication, des exemples et des mots-clés par langue.
- to_french(texte) : une commande dite en anglais, espagnol, russe, chinois, japonais ou hindi -> la commande
  française que Viki comprend déjà (« play lofi » -> « mets lofi »).
- TipsWindow : la fenêtre « 💡 Trucs et astuces »."""
import random
import re
import unicodedata

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QScrollArea,
                             QVBoxLayout, QWidget)

LANGS = [("fr", "Français"), ("en", "English"), ("es", "Español"), ("ru", "Русский"), ("zh", "中文"), ("ja", "日本語"),
         ("hi", "हिन्दी")]
LATIN = {"fr", "en", "es"}


def _sa(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


CATS = [("parler", "💬", {"fr": "Parler avec elle", "en": "Talking", "es": "Hablar", "ru": "Разговор", "zh": "聊天",
                          "ja": "会話", "hi": "बातचीत"}),
        ("jour", "☀️", {"fr": "Au quotidien", "en": "Daily life", "es": "Día a día", "ru": "Каждый день", "zh": "日常",
                        "ja": "毎日", "hi": "रोज़मर्रा"}),
        ("media", "🎬", {"fr": "Musique et vidéos", "en": "Music and videos", "es": "Música y vídeos",
                         "ru": "Музыка и видео", "zh": "音乐和视频", "ja": "音楽と動画", "hi": "संगीत और वीडियो"}),
        ("creer", "🎨", {"fr": "Créer", "en": "Create", "es": "Crear", "ru": "Создавать", "zh": "创作", "ja": "作る",
                         "hi": "बनाओ"}),
        ("pc", "💻", {"fr": "PC et travail", "en": "PC and work", "es": "PC y trabajo", "ru": "ПК и работа",
                      "zh": "电脑和工作", "ja": "PCと仕事", "hi": "पीसी और काम"}),
        ("astuces", "💡", {"fr": "Astuces", "en": "Tips", "es": "Trucos", "ru": "Советы", "zh": "小技巧", "ja": "コツ",
                           "hi": "टिप्स"})]

# kw : mots-clés montrés dans la fenêtre. rx : expressions reconnues -> canon ({x} = la suite de la phrase).
ACTIONS = [
    # ---------------------------------------------------------------- parler
    dict(id="chut", cat="parler", ico="🔇", canon="chut",
         t={"fr": "La faire taire", "en": "Make her quiet", "es": "Silenciarla", "ru": "Тишина", "zh": "让她安静",
            "ja": "静かにさせる", "hi": "चुप कराना"},
         d="Elle se tait (pour 1 heure si tu dis « chut 1 heure »). « Tu peux reparler » pour la réentendre.",
         ex=["chut", "chut 30 minutes", "tu peux reparler"],
         kw={"en": ["be quiet", "shut up", "mute"], "es": ["silencio", "cállate"], "ru": ["тихо", "замолчи"],
             "zh": ["安静", "闭嘴"], "ja": ["静かに", "黙って"], "hi": ["चुप", "शांत रहो"]},
         rx={"en": [r"^(?:be quiet|shut up|mute|silence)\b"], "es": [r"^(?:silencio|callate)\b"],
             "ru": [r"^(?:тихо|замолчи|молчи)"], "zh": [r"^(?:安静|闭嘴)"], "ja": [r"^(?:静かに|黙って)"],
             "hi": [r"^(?:चुप|शांत रहो)"]}),
    dict(id="heure", cat="parler", ico="🕐", canon="quelle heure est-il",
         t={"fr": "L'heure", "en": "The time", "es": "La hora", "ru": "Время", "zh": "时间", "ja": "時間", "hi": "समय"},
         d="Elle te dit l'heure.", ex=["quelle heure est-il"],
         kw={"en": ["what time is it"], "es": ["qué hora es"], "ru": ["который час"], "zh": ["几点了"],
             "ja": ["何時"], "hi": ["कितने बजे हैं"]},
         rx={"en": [r"what time is it|the time\b"], "es": [r"que hora es"], "ru": [r"который час|сколько времени"],
             "zh": [r"几点"], "ja": [r"何時"], "hi": [r"कितने बजे|समय क्या"]}),
    dict(id="blague", cat="parler", ico="😄", canon="raconte-moi une blague",
         t={"fr": "Une blague", "en": "A joke", "es": "Un chiste", "ru": "Шутка", "zh": "讲个笑话", "ja": "ジョーク",
            "hi": "चुटकुला"},
         d="Une petite blague pour sourire.", ex=["raconte-moi une blague"],
         kw={"en": ["tell me a joke"], "es": ["cuéntame un chiste"], "ru": ["расскажи шутку", "анекдот"],
             "zh": ["讲个笑话"], "ja": ["ジョークを言って"], "hi": ["चुटकुला सुनाओ"]},
         rx={"en": [r"\bjoke\b"], "es": [r"\bchiste\b"], "ru": [r"шутк|анекдот"], "zh": [r"笑话"], "ja": [r"ジョーク|冗談"],
             "hi": [r"चुटकुला"]}),
    dict(id="apprendre", cat="parler", ico="💡", canon="apprends-moi quelque chose",
         t={"fr": "Apprendre un truc", "en": "Learn something", "es": "Aprender algo", "ru": "Узнать новое",
            "zh": "学点东西", "ja": "豆知識", "hi": "कुछ सिखाओ"},
         d="Un fait étonnant ou utile, chaque jour.", ex=["apprends-moi quelque chose"],
         kw={"en": ["teach me something", "fun fact"], "es": ["enséñame algo"], "ru": ["расскажи что-нибудь интересное"],
             "zh": ["教我点东西"], "ja": ["豆知識"], "hi": ["कुछ सिखाओ"]},
         rx={"en": [r"teach me|fun fact"], "es": [r"ensename algo|dato curioso"], "ru": [r"что-нибудь интересное|научи"],
             "zh": [r"教我"], "ja": [r"豆知識|教えて何か"], "hi": [r"कुछ सिखाओ"]}),
    # ---------------------------------------------------------------- quotidien
    dict(id="actu", cat="jour", ico="📰", canon="donne-moi l'actu {x}",
         t={"fr": "L'actu", "en": "The news", "es": "Las noticias", "ru": "Новости", "zh": "新闻", "ja": "ニュース",
            "hi": "समाचार"},
         d="Les derniers titres des sites que tu suis. Tu peux préciser un sujet ou un site.",
         ex=["donne-moi l'actu", "l'actu sur l'espace", "quoi de neuf en tech ?"],
         kw={"en": ["news", "what's new", "news about …"], "es": ["noticias", "noticias de …"], "ru": ["новости", "новости о …"],
             "zh": ["新闻", "…的新闻"], "ja": ["ニュース", "…のニュース"], "hi": ["समाचार", "खबरें"]},
         rx={"en": [r"^(?:tell me |give me |read me )?(?:the )?(?:latest )?news(?: about| on)?(?P<x>.*)$", r"^what'?s new\b(?P<x>.*)$"],
             "es": [r"^(?:dame |dime )?(?:las )?noticias(?: de| sobre)?(?P<x>.*)$"],
             "ru": [r"^(?:расскажи )?новости(?: о| про)?(?P<x>.*)$"], "zh": [r"^(?P<x>.*?)(?:的)?新闻$"],
             "ja": [r"^(?P<x>.*?)(?:の)?ニュース"], "hi": [r"(?:समाचार|खबरें|न्यूज़)"]}),
    dict(id="note", cat="jour", ico="📝", canon="note que {x}",
         t={"fr": "Prendre une note", "en": "Take a note", "es": "Tomar nota", "ru": "Заметка", "zh": "记笔记",
            "ja": "メモ", "hi": "नोट"},
         d="Elle garde ta note. « Qu'est-ce que j'avais noté sur … ? » pour la retrouver.",
         ex=["note que le code du portail est 1234", "qu'est-ce que j'avais noté sur le portail ?", "mes notes"],
         kw={"en": ["note that …", "take a note …"], "es": ["anota …", "apunta …"], "ru": ["запиши …"], "zh": ["记下…"],
             "ja": ["メモして …"], "hi": ["नोट करो …"]},
         rx={"en": [r"^(?:note that|take a note|write down|remember that)[: ]+(?P<x>.+)$"],
             "es": [r"^(?:anota|apunta|recuerda que)[: ]+(?P<x>.+)$"], "ru": [r"^(?:запиши|запомни)[: ]+(?P<x>.+)$"],
             "zh": [r"^(?:记下|记住)[:：]?(?P<x>.+)$"], "ja": [r"^メモ[:： ]?(?P<x>.+)$", r"^(?P<x>.+)をメモして$"],
             "hi": [r"^नोट करो[: ]+(?P<x>.+)$"]}),
    dict(id="courses", cat="jour", ico="🛒", canon="ajoute {x} à la liste de courses",
         t={"fr": "Liste de courses", "en": "Shopping list", "es": "Lista de la compra", "ru": "Список покупок",
            "zh": "购物清单", "ja": "買い物リスト", "hi": "खरीदारी सूची"},
         d="Ajoute, retire et affiche ta liste de courses.",
         ex=["ajoute du lait à la liste de courses", "j'ai acheté le lait", "ma liste de courses"],
         kw={"en": ["add … to the shopping list"], "es": ["añade … a la lista de la compra"],
             "ru": ["добавь … в список покупок"], "zh": ["把…加到购物清单"], "ja": ["…を買い物リストに追加"],
             "hi": ["… खरीदारी सूची में जोड़ो"]},
         rx={"en": [r"^add (?P<x>.+?) to (?:the |my )?shopping list$"],
             "es": [r"^(?:anade|agrega) (?P<x>.+?) a la lista de (?:la )?compra$"],
             "ru": [r"^добавь (?P<x>.+?) в список покупок$"], "zh": [r"^把(?P<x>.+?)加到购物清单"],
             "ja": [r"^(?P<x>.+?)を買い物リストに"], "hi": [r"^(?P<x>.+?) खरीदारी सूची में"]}),
    dict(id="rappel", cat="jour", ico="⏰", canon="rappelle-moi {x}",
         t={"fr": "Un rappel", "en": "A reminder", "es": "Un recordatorio", "ru": "Напоминание", "zh": "提醒",
            "ja": "リマインダー", "hi": "याद दिलाना"},
         d="Elle te prévient à l'heure dite.",
         ex=["rappelle-moi dans 10 minutes de sortir le linge", "rappelle-moi à 18h30 d'appeler maman"],
         kw={"en": ["remind me in 10 minutes to …"], "es": ["recuérdame en 10 minutos …"],
             "ru": ["напомни через 10 минут …"], "zh": ["10分钟后提醒我…"], "ja": ["10分後に…をリマインド"],
             "hi": ["10 मिनट में याद दिलाना …"]},
         rx={"en": [r"^remind me (?P<x>.+)$"], "es": [r"^recuerdame (?P<x>.+)$"], "ru": [r"^напомни (?P<x>.+)$"],
             "zh": [r"^(?P<x>.*)提醒我(?P<y>.*)$"], "ja": [r"^(?P<x>.+)リマインド"], "hi": [r"याद दिला"]}),
    dict(id="minuteur", cat="jour", ico="⏲️", canon="minuteur {x}",
         t={"fr": "Un minuteur", "en": "A timer", "es": "Un temporizador", "ru": "Таймер", "zh": "计时器", "ja": "タイマー",
            "hi": "टाइमर"},
         d="Un compte à rebours, avec sonnerie.", ex=["minuteur 5 minutes", "minuteur 1 heure"],
         kw={"en": ["timer 5 minutes"], "es": ["temporizador 5 minutos"], "ru": ["таймер 5 минут"], "zh": ["计时5分钟"],
             "ja": ["タイマー5分"], "hi": ["टाइमर 5 मिनट"]},
         rx={"en": [r"^(?:set )?(?:a )?timer(?: for)? (?P<x>.+)$"], "es": [r"^temporizador(?: de)? (?P<x>.+)$"],
             "ru": [r"^таймер(?: на)? (?P<x>.+)$"], "zh": [r"^计时(?P<x>.+)$"], "ja": [r"^タイマー(?P<x>.+)$"],
             "hi": [r"^टाइमर (?P<x>.+)$"]}),
    dict(id="repas", cat="jour", ico="🍽️", canon="une idée de repas",
         t={"fr": "Idée de repas", "en": "Meal idea", "es": "Idea de comida", "ru": "Идея для ужина", "zh": "吃什么",
            "ja": "献立のアイデア", "hi": "खाने का आइडिया"},
         d="Un repas simple, pas cher et sain.", ex=["une idée de repas", "on mange quoi ce soir ?"],
         kw={"en": ["meal idea", "what should I eat"], "es": ["qué como hoy"], "ru": ["что приготовить"],
             "zh": ["今天吃什么"], "ja": ["今日の献立"], "hi": ["आज क्या खाएं"]},
         rx={"en": [r"meal idea|what should i (?:eat|cook)"], "es": [r"que (?:como|cocino)|idea de comida"],
             "ru": [r"что (?:приготовить|поесть)"], "zh": [r"吃什么"], "ja": [r"献立|何を食べ"], "hi": [r"क्या खाएं"]}),
    dict(id="sport", cat="jour", ico="🏃", canon="propose-moi du sport",
         t={"fr": "Pause sport", "en": "Exercise break", "es": "Pausa de ejercicio", "ru": "Разминка", "zh": "运动一下",
            "ja": "運動休憩", "hi": "व्यायाम"},
         d="Quelques mouvements pour bouger.", ex=["propose-moi du sport"],
         kw={"en": ["exercise", "workout"], "es": ["ejercicio"], "ru": ["разминка", "упражнения"], "zh": ["运动"],
             "ja": ["運動", "ストレッチ"], "hi": ["व्यायाम"]},
         rx={"en": [r"\b(?:exercise|workout|stretch)"], "es": [r"\bejercicio"], "ru": [r"разминк|упражнени"],
             "zh": [r"运动|锻炼"], "ja": [r"運動|ストレッチ"], "hi": [r"व्यायाम|कसरत"]}),
    dict(id="pomodoro", cat="jour", ico="🍅", canon="lance un pomodoro",
         t={"fr": "Pomodoro", "en": "Pomodoro", "es": "Pomodoro", "ru": "Помодоро", "zh": "番茄钟", "ja": "ポモドーロ",
            "hi": "पोमोडोरो"},
         d="25 minutes de concentration, puis 5 de pause.", ex=["lance un pomodoro"],
         kw={"en": ["pomodoro", "focus"], "es": ["pomodoro"], "ru": ["помодоро"], "zh": ["番茄钟"], "ja": ["ポモドーロ"],
             "hi": ["पोमोडोरो"]},
         rx={"en": [r"pomodoro|focus mode"], "es": [r"pomodoro"], "ru": [r"помодоро"], "zh": [r"番茄钟"],
             "ja": [r"ポモドーロ"], "hi": [r"पोमोडोरो"]}),
    dict(id="fichier", cat="jour", ico="🔎", canon="trouve {x}",
         t={"fr": "Trouver un fichier", "en": "Find a file", "es": "Buscar un archivo", "ru": "Найти файл",
            "zh": "找文件", "ja": "ファイルを探す", "hi": "फ़ाइल ढूंढो"},
         d="Dans ton dossier perso, tes disques et (si besoin) les dossiers cachés.",
         ex=["trouve mon CV", "le pdf que j'ai téléchargé hier", "trouve mes captures d'écran"],
         kw={"en": ["find …", "where is my …"], "es": ["busca …", "encuentra …"], "ru": ["найди …"], "zh": ["找…"],
             "ja": ["…を探して"], "hi": ["… ढूंढो"]},
         rx={"en": [r"^(?:find|where is|where'?s|locate) (?:my )?(?P<x>.+)$"],
             "es": [r"^(?:busca|encuentra|donde esta) (?:mi |mis )?(?P<x>.+)$"], "ru": [r"^(?:найди|где) (?P<x>.+)$"],
             "zh": [r"^(?:找|查找|帮我找)(?P<x>.+)$"], "ja": [r"^(?P<x>.+?)を探して"], "hi": [r"^(?P<x>.+?) ढूंढो$"]}),
    dict(id="web", cat="jour", ico="🌐", canon="cherche sur internet {x}",
         t={"fr": "Chercher sur internet", "en": "Search the web", "es": "Buscar en internet", "ru": "Поиск в интернете",
            "zh": "上网搜索", "ja": "ネット検索", "hi": "इंटरनेट पर खोजो"},
         d="Elle cherche et te résume (seulement quand tu le demandes).", ex=["cherche sur internet la recette des crêpes"],
         kw={"en": ["search the web for …", "google …"], "es": ["busca en internet …"], "ru": ["поищи в интернете …"],
             "zh": ["上网搜…"], "ja": ["ネットで…を調べて"], "hi": ["इंटरनेट पर … खोजो"]},
         rx={"en": [r"^(?:search (?:the web|online|the internet) for|google|look up) (?P<x>.+)$"],
             "es": [r"^busca en (?:internet|la web|google) (?P<x>.+)$"], "ru": [r"^поищи в интернете (?P<x>.+)$"],
             "zh": [r"^上网搜(?:索)?(?P<x>.+)$"], "ja": [r"^ネットで(?P<x>.+?)を?(?:調べて|検索)"],
             "hi": [r"^इंटरनेट पर (?P<x>.+?) खोजो$"]}),
    # ---------------------------------------------------------------- média
    dict(id="musique", cat="media", ico="🎵", canon="mets de la musique",
         t={"fr": "Mettre de la musique", "en": "Play music", "es": "Poner música", "ru": "Включить музыку",
            "zh": "放音乐", "ja": "音楽をかける", "hi": "संगीत चलाओ"},
         d="Un morceau de ta chaîne, ou ce que tu demandes sur YouTube.",
         ex=["mets-moi de la musique", "je veux écouter du lofi", "mets le dernier son de ma chaîne"],
         kw={"en": ["play music", "play some lofi"], "es": ["pon música", "pon lofi"], "ru": ["включи музыку"],
             "zh": ["放音乐", "播放音乐"], "ja": ["音楽をかけて"], "hi": ["गाना चलाओ", "संगीत चलाओ"]},
         rx={"en": [r"^(?:play|put on) (?:some )?music$", r"^(?:play|put on) some (?P<x>.+)$"],
             "es": [r"^pon (?:algo de )?musica$", r"^pon (?:algo de |un poco de )(?P<x>.+)$"],
             "ru": [r"^(?:включи|поставь) музыку$"], "zh": [r"^(?:放|播放)音乐$"], "ja": [r"^音楽を(?:かけて|流して|再生)"],
             "hi": [r"^(?:गाना|संगीत|म्यूज़िक) (?:चलाओ|बजाओ)$"]}),
    dict(id="regarder", cat="media", ico="📺", canon="je veux regarder {x}",
         t={"fr": "Regarder / reprendre", "en": "Watch / resume", "es": "Ver / continuar", "ru": "Смотреть дальше",
            "zh": "观看 / 继续", "ja": "見る / 続きから", "hi": "देखो / जारी रखो"},
         d="Ouvre un titre de « Ma liste » là où tu t'es arrêté (épisode, minute), avec le site et le navigateur choisis.",
         ex=["je veux regarder One Piece", "One Piece sur ADN", "mets ma playlist chill avec Firefox", "épisode suivant",
             "j'en suis à l'épisode 7 de Frieren", "je me suis arrêté à 23:15 dans Dune"],
         kw={"en": ["watch …", "play …", "resume …", "next episode"], "es": ["quiero ver …", "pon …", "siguiente episodio"],
             "ru": ["включи …", "хочу посмотреть …", "следующая серия"], "zh": ["我要看…", "播放…", "下一集"],
             "ja": ["…を見たい", "…を再生", "次の話"], "hi": ["… देखना है", "… चलाओ", "अगला एपिसोड"]},
         rx={"en": [r"(?P<n>next episode)", r"^(?:watch|resume|continue|play|put on|open) (?P<x>.+)$"],
             "es": [r"(?P<n>(?:siguiente|proximo) episodio)",
                    r"^(?:quiero ver|ver|pon|ponme|continua|reproduce|abre) (?P<x>.+)$"],
             "ru": [r"(?P<n>следующ\w+ сери)", r"^(?:включи|поставь|хочу посмотреть|открой) (?P<x>.+)$"],
             "zh": [r"(?P<n>下一集)", r"^(?:我要看|我想看|播放|打开|继续看)(?P<x>.+)$"],
             "ja": [r"(?P<n>次の(?:話|エピソード))", r"^(?P<x>.+?)を(?:見たい|再生|かけて|開いて)"],
             "hi": [r"(?P<n>अगला एपिसोड)", r"^(?P<x>.+?) (?:देखना है|चलाओ|लगाओ)$"]}),
    dict(id="liste", cat="media", ico="🗂️", canon="ma liste",
         t={"fr": "Ma liste", "en": "My list", "es": "Mi lista", "ru": "Мой список", "zh": "我的列表", "ja": "マイリスト",
            "hi": "मेरी सूची"},
         d="Tes liens de séries, films, animés et musique : plusieurs sites par titre, ajout en masse, recherche.",
         ex=["ma liste", "garde ce lien sous le nom One Piece", "mets de la musique de ma liste"],
         kw={"en": ["my list"], "es": ["mi lista"], "ru": ["мой список"], "zh": ["我的列表"], "ja": ["マイリスト"],
             "hi": ["मेरी सूची"]},
         rx={"en": [r"^(?:open |show )?my list$"], "es": [r"^(?:abre |muestra )?mi lista$"], "ru": [r"^(?:открой )?мой список$"],
             "zh": [r"^(?:打开)?我的列表$"], "ja": [r"^マイリスト"], "hi": [r"^मेरी सूची"]}),
    # ---------------------------------------------------------------- créer
    dict(id="image", cat="creer", ico="🖼️", canon="génère une image de {x}",
         t={"fr": "Créer une image", "en": "Create an image", "es": "Crear una imagen", "ru": "Создать картинку",
            "zh": "生成图片", "ja": "画像を作る", "hi": "तस्वीर बनाओ"},
         d="Dans l'atelier d'images : en ligne ou avec une IA libre sur ton PC.",
         ex=["génère une image d'un dragon bleu", "dessine-moi un fond d'écran cyberpunk"],
         kw={"en": ["generate an image of …", "draw …"], "es": ["genera una imagen de …", "dibuja …"],
             "ru": ["нарисуй …", "создай картинку …"], "zh": ["画…", "生成图片…"], "ja": ["…の絵を描いて"],
             "hi": ["… की तस्वीर बनाओ"]},
         rx={"en": [r"^(?:generate|create|make|draw|paint)(?: me)? (?:an? )?(?:image|picture|drawing|wallpaper)?(?: of)? ?(?P<x>.+)$"],
             "es": [r"^(?:genera|crea|dibuja|pinta)(?:me)? (?:una )?(?:imagen|dibujo)?(?: de)? ?(?P<x>.+)$"],
             "ru": [r"^(?:нарисуй|создай картинку|сгенерируй картинку) ?(?P<x>.+)$"],
             "zh": [r"^(?:画|生成图片|生成一张)(?P<x>.+)$"], "ja": [r"^(?P<x>.+?)の(?:絵|画像)を(?:描いて|作って|生成)"],
             "hi": [r"^(?P<x>.+?) की (?:तस्वीर|फोटो) बनाओ$"]}),
    dict(id="chanson", cat="creer", ico="🎼", canon="compose-moi une chanson",
         t={"fr": "Composer une musique", "en": "Compose music", "es": "Componer música", "ru": "Сочинить музыку",
            "zh": "作曲", "ja": "作曲する", "hi": "गाना बनाओ"},
         d="Le studio musique : style, voix, paroles (elle peut les écrire), durée.", ex=["compose-moi une chanson"],
         kw={"en": ["compose a song", "make a beat"], "es": ["compón una canción"], "ru": ["сочини песню"],
             "zh": ["作一首歌"], "ja": ["曲を作って"], "hi": ["गाना बनाओ"]},
         rx={"en": [r"^(?:compose|make|create|write)(?: me)? (?:a )?(?:song|beat|track|music)"],
             "es": [r"^(?:compon|crea|haz)(?:me)? (?:una )?(?:cancion|musica|beat)"], "ru": [r"сочини|создай (?:песню|музыку)"],
             "zh": [r"作(?:一首)?(?:歌|曲)"], "ja": [r"曲を作"], "hi": [r"गाना बनाओ|संगीत बनाओ"]}),
    # ---------------------------------------------------------------- PC
    dict(id="erreur", cat="pc", ico="🐞", canon="explique cette erreur",
         t={"fr": "Expliquer une erreur", "en": "Explain an error", "es": "Explicar un error", "ru": "Объяснить ошибку",
            "zh": "解释错误", "ja": "エラーを説明", "hi": "एरर समझाओ"},
         d="Copie le message d'erreur, puis demande-lui : sens, cause, correction.", ex=["explique cette erreur"],
         kw={"en": ["explain this error"], "es": ["explica este error"], "ru": ["объясни ошибку"], "zh": ["解释这个错误"],
             "ja": ["このエラーを説明して"], "hi": ["यह एरर समझाओ"]},
         rx={"en": [r"explain (?:this |the )?error"], "es": [r"explica (?:este |el )?error"], "ru": [r"объясни ошибку"],
             "zh": [r"解释.*错误"], "ja": [r"エラー.*説明"], "hi": [r"एरर समझाओ"]}),
    dict(id="securite", cat="pc", ico="🛡️", canon="vérifie la sécurité de mon pc",
         t={"fr": "Sécurité du PC", "en": "PC security", "es": "Seguridad del PC", "ru": "Безопасность ПК",
            "zh": "电脑安全", "ja": "PCのセキュリティ", "hi": "पीसी सुरक्षा"},
         d="Elle vérifie ton PC et t'explique quoi faire.", ex=["vérifie la sécurité de mon pc"],
         kw={"en": ["check my pc security"], "es": ["revisa la seguridad de mi pc"], "ru": ["проверь безопасность"],
             "zh": ["检查电脑安全"], "ja": ["セキュリティをチェック"], "hi": ["सुरक्षा जांचो"]},
         rx={"en": [r"(?:check|scan).*(?:security|virus)"], "es": [r"(?:revisa|comprueba).*seguridad"],
             "ru": [r"провер\w+ безопасност"], "zh": [r"检查.*安全"], "ja": [r"セキュリティ"], "hi": [r"सुरक्षा"]}),
    dict(id="code", cat="pc", ico="💻", canon="relis mon code",
         t={"fr": "Aide au code", "en": "Coding help", "es": "Ayuda con el código", "ru": "Помощь с кодом",
            "zh": "代码帮助", "ja": "コードの手伝い", "hi": "कोड मदद"},
         d="Relecture avant commit, message de commit, TODO, snippets, journal de projet.",
         ex=["relis mon code", "message de commit", "liste les todo", "garde ce code sous le nom tri", "mes snippets"],
         kw={"en": ["review my code", "commit message", "my snippets"], "es": ["revisa mi código"],
             "ru": ["проверь мой код"], "zh": ["检查我的代码"], "ja": ["コードをレビュー"], "hi": ["मेरा कोड जांचो"]},
         rx={"en": [r"review my code"], "es": [r"revisa mi codigo"], "ru": [r"провер\w+ (?:мой )?код"],
             "zh": [r"检查.*代码"], "ja": [r"コード.*レビュー"], "hi": [r"कोड जांचो"]}),
    dict(id="copies", cat="pc", ico="📋", canon="historique du presse-papiers",
         t={"fr": "Ce que j'ai copié", "en": "Clipboard history", "es": "Historial del portapapeles",
            "ru": "История буфера", "zh": "剪贴板历史", "ja": "コピー履歴", "hi": "कॉपी इतिहास"},
         d="Tes 40 dernières copies (en mémoire seulement). « Recolle le lien de tout à l'heure ».",
         ex=["historique du presse-papiers", "recolle le lien de tout à l'heure"],
         kw={"en": ["clipboard history"], "es": ["historial del portapapeles"], "ru": ["история буфера"],
             "zh": ["剪贴板历史"], "ja": ["コピー履歴"], "hi": ["कॉपी इतिहास"]},
         rx={"en": [r"clipboard history"], "es": [r"historial del portapapeles"], "ru": [r"истори\w+ буфера"],
             "zh": [r"剪贴板"], "ja": [r"コピー履歴|クリップボード"], "hi": [r"कॉपी इतिहास"]}),
    dict(id="vieprivee", cat="pc", ico="🛡️", canon="vie privée",
         t={"fr": "Vie privée et sécurité", "en": "Privacy and security", "es": "Privacidad y seguridad",
            "ru": "Приватность и безопасность", "zh": "隐私与安全", "ja": "プライバシーとセキュリティ", "hi": "निजता और सुरक्षा"},
         d="Bilan du PC, ports ouverts et redirections de ta box, navigateurs et outils à installer (Tor, pare-feu, "
           "KeePassXC…), DNS chiffré, proxy, sauvegarde chiffrée. Tout en option.",
         ex=["vie privée", "quels ports sont ouverts ?", "mets un dns chiffré", "installe librewolf",
             "sauvegarde chiffrée"],
         kw={"en": ["privacy", "open ports"], "es": ["privacidad", "puertos abiertos"], "ru": ["приватность", "открытые порты"],
             "zh": ["隐私", "开放端口"], "ja": ["プライバシー", "開いているポート"], "hi": ["निजता", "खुले पोर्ट"]},
         rx={"en": [r"^privacy\b", r"open ports"], "es": [r"^privacidad", r"puertos abiertos"],
             "ru": [r"^приватност", r"открыт\w+ порт"], "zh": [r"隐私", r"开放端口|端口"], "ja": [r"プライバシー", r"ポート"],
             "hi": [r"निजता", r"पोर्ट"]}),
    dict(id="wiki", cat="jour", ico="📖", canon="wikipédia {x}",
         t={"fr": "Wikipédia", "en": "Wikipedia", "es": "Wikipedia", "ru": "Википедия", "zh": "维基百科", "ja": "ウィキペディア",
            "hi": "विकिपीडिया"},
         d="Pose une question de culture : elle propose d'ouvrir Wikipédia sur le sujet. Ou demande-le directement.",
         ex=["c'est quoi un trou noir ?", "wikipédia Marie Curie", "cherche les volcans sur wikipédia"],
         kw={"en": ["wikipedia …"], "es": ["wikipedia …"], "ru": ["википедия …"], "zh": ["维基百科 …"], "ja": ["ウィキペディア …"],
             "hi": ["विकिपीडिया …"]},
         rx={"en": [r"^wikipedia (?P<x>.+)$"], "es": [r"^wikipedia (?P<x>.+)$"], "ru": [r"^википедия (?P<x>.+)$"],
             "zh": [r"^维基百科(?P<x>.+)$"], "ja": [r"^ウィキペディア(?P<x>.+)$"], "hi": [r"^विकिपीडिया (?P<x>.+)$"]}),
    dict(id="trad_sel", cat="jour", ico="🌍", canon="traduis la sélection",
         t={"fr": "Traduire le texte sélectionné", "en": "Translate the selection", "es": "Traducir la selección",
            "ru": "Перевести выделенное", "zh": "翻译选中的文字", "ja": "選択したテキストを翻訳", "hi": "चुना हुआ टेक्स्ट अनुवाद करो"},
         d="Sélectionne un texte n'importe où (ou copie-le), puis demande-lui. Avec un raccourci clavier, c'est "
           "instantané (Réglages → Au quotidien → Raccourcis clavier).",
         ex=["traduis la sélection", "traduis la sélection en espagnol"],
         kw={"en": ["translate the selection"], "es": ["traduce la selección"], "ru": ["переведи выделенное"],
             "zh": ["翻译选中"], "ja": ["選択を翻訳"], "hi": ["चुना हुआ अनुवाद"]},
         rx={"en": [r"translate (?:the |my )?selection"], "es": [r"traduc\w* (?:la )?seleccion"],
             "ru": [r"перевед\w* выделен"], "zh": [r"翻译选中"], "ja": [r"選択.*翻訳"], "hi": [r"चुना हुआ.*अनुवाद"]}),
    dict(id="lire_page", cat="jour", ico="🔊", canon="lis-moi cette page",
         t={"fr": "Lire une page ou un document", "en": "Read a page aloud", "es": "Leer una página en voz alta",
            "ru": "Прочитать страницу вслух", "zh": "朗读网页", "ja": "ページを読み上げる", "hi": "पेज पढ़कर सुनाओ"},
         d="Copie l'adresse d'une page web (ou d'un PDF en ligne) : elle en lit le texte principal, sans les menus. "
           "Ou sélectionne un texte : « lis-moi la sélection ». Un document : glisse-le sur elle.",
         ex=["lis-moi cette page", "lis-moi la sélection", "lis-moi ce pdf"],
         kw={"en": ["read this page"], "es": ["léeme esta página"], "ru": ["прочитай эту страницу"],
             "zh": ["朗读这个网页"], "ja": ["このページを読んで"], "hi": ["यह पेज पढ़ो"]},
         rx={"en": [r"read (?:me )?(?:this|the) (?:page|article)"], "es": [r"leeme (?:esta|la) pagina"],
             "ru": [r"прочитай\w* (?:эту )?страниц"], "zh": [r"朗读.*网页"], "ja": [r"ページ.*読"], "hi": [r"पेज पढ़"]}),
    dict(id="ecran", cat="pc", ico="🖥️", canon="qu'est-ce qu'il y a sur mon écran",
         t={"fr": "Décrire mon écran", "en": "Describe my screen", "es": "Describir mi pantalla",
            "ru": "Описать экран", "zh": "描述我的屏幕", "ja": "画面を説明", "hi": "मेरी स्क्रीन बताओ"},
         d="Elle fait une capture et la décrit avec une IA locale qui voit les images (qwen3-vl). Tu peux poser une "
           "question précise : « explique l'erreur sur mon écran ».",
         ex=["qu'est-ce qu'il y a sur mon écran ?", "explique ce qu'il y a sur mon écran"],
         kw={"en": ["what's on my screen"], "es": ["qué hay en mi pantalla"], "ru": ["что на моём экране"],
             "zh": ["我的屏幕上有什么"], "ja": ["画面に何がある"], "hi": ["स्क्रीन पर क्या है"]},
         rx={"en": [r"what'?s on (?:my|the) screen", r"describe (?:my|the) screen"],
             "es": [r"que hay en (?:mi|la) pantalla"], "ru": [r"что (?:на|у) (?:моём |моем )?экран"],
             "zh": [r"屏幕上有什么"], "ja": [r"画面に何"], "hi": [r"स्क्रीन पर क्या"]}),
    dict(id="agenda_web", cat="jour", ico="🗓️", canon="ajoute mon agenda en ligne",
         t={"fr": "Agenda Google / Nextcloud", "en": "Google / Nextcloud calendar", "es": "Calendario Google / Nextcloud",
            "ru": "Календарь Google / Nextcloud", "zh": "谷歌/Nextcloud 日历", "ja": "Google / Nextcloud カレンダー",
            "hi": "Google / Nextcloud कैलेंडर"},
         d="Colle l'adresse iCal secrète de ton agenda : elle le met à jour toutes les heures, te prévient avant "
           "tes rendez-vous et répond à « qu'est-ce que j'ai demain ? ».",
         ex=["ajoute mon agenda en ligne", "qu'est-ce que j'ai demain ?", "mon agenda de la semaine"],
         kw={"en": ["add my online calendar"], "es": ["añade mi calendario en línea"], "ru": ["добавь онлайн-календарь"],
             "zh": ["添加在线日历"], "ja": ["オンラインカレンダーを追加"], "hi": ["ऑनलाइन कैलेंडर जोड़ो"]},
         rx={"en": [r"add (?:my )?(?:online|google|nextcloud) calendar"], "es": [r"anade (?:mi )?calendario (?:en linea|google)"],
             "ru": [r"добав\w* (?:онлайн-?)?календар"], "zh": [r"添加.*日历"], "ja": [r"カレンダー.*追加"],
             "hi": [r"कैलेंडर जोड़"]}),
    dict(id="jeux", cat="elle", ico="🎮", canon="mes stats de jeu",
         t={"fr": "Mes stats de jeu", "en": "My gaming stats", "es": "Mis estadísticas de juego",
            "ru": "Моя игровая статистика", "zh": "我的游戏统计", "ja": "ゲームの統計", "hi": "मेरे गेम के आँकड़े"},
         d="Elle remarque tes jeux (Steam, Proton, Wine, Lutris…) : temps de jeu, félicitations aux paliers, petite "
           "pause conseillée après 2 h.",
         ex=["mes stats de jeu", "combien j'ai joué cette semaine ?"],
         kw={"en": ["my gaming stats"], "es": ["mis estadísticas de juego"], "ru": ["игровая статистика"],
             "zh": ["游戏统计"], "ja": ["ゲーム統計"], "hi": ["गेम आँकड़े"]},
         rx={"en": [r"(?:gaming|game|play) ?(?:time|stats)"], "es": [r"estadisticas de juego|cuanto he jugado"],
             "ru": [r"игров\w+ статистик|сколько я играл"], "zh": [r"游戏统计|玩了多久"], "ja": [r"ゲーム.*統計"],
             "hi": [r"गेम.*आँकड़े"]}),
    dict(id="neige", cat="elle", ico="❄️", canon="fais tomber la neige",
         t={"fr": "Neige, feuilles, confettis", "en": "Snow, leaves, confetti", "es": "Nieve, hojas, confeti",
            "ru": "Снег, листья, конфетти", "zh": "下雪、落叶、彩纸", "ja": "雪・落ち葉・紙吹雪", "hi": "बर्फ़, पत्ते, कंफ़ेटी"},
         d="Petits effets sur l'écran, tout seuls les jours de fête (Noël, Halloween…) ou quand tu veux. La souris "
           "passe au travers. Son anniversaire : le jour où tu l'as installée !",
         ex=["fais tomber la neige", "mets des feuilles", "lance des confettis", "arrête la neige",
             "c'est quand ton anniversaire ?"],
         kw={"en": ["make it snow"], "es": ["haz que nieve"], "ru": ["пусть идёт снег"], "zh": ["下雪吧"], "ja": ["雪を降らせて"],
             "hi": ["बर्फ़ गिराओ"]},
         rx={"en": [r"make it snow|let it snow"], "es": [r"haz que nieve"], "ru": [r"снег"], "zh": [r"下雪"],
             "ja": [r"雪を降らせ"], "hi": [r"बर्फ़ गिराओ"]}),
    dict(id="batterie", cat="pc", ico="🔋", canon="mode batterie",
         t={"fr": "Mode batterie", "en": "Battery mode", "es": "Modo batería", "ru": "Режим батареи", "zh": "省电模式",
            "ja": "バッテリーモード", "hi": "बैटरी मोड"},
         d="Sur un portable débranché, elle se fait légère toute seule (moins d'animations et de vérifications). "
           "Tu peux le forcer : « mode batterie », ou l'enlever : « désactive le mode batterie ».",
         ex=["mode batterie", "désactive le mode batterie"],
         kw={"en": ["battery mode"], "es": ["modo batería"], "ru": ["режим батареи"], "zh": ["省电模式"], "ja": ["バッテリーモード"],
             "hi": ["बैटरी मोड"]},
         rx={"en": [r"^battery (?:mode|saver)$"], "es": [r"^modo bateria$"], "ru": [r"^режим (?:батареи|экономии)"],
             "zh": [r"^省电模式$"], "ja": [r"^バッテリーモード$"], "hi": [r"^बैटरी मोड$"]}),
    dict(id="apparence", cat="elle", ico="👗", canon="change ton look",
         t={"fr": "Son apparence", "en": "Her look", "es": "Su aspecto", "ru": "Её внешность", "zh": "她的外观",
            "ja": "見た目", "hi": "उसका लुक"},
         d="Couleur des cheveux, de la peau, des yeux, des vêtements et des chaussures, motifs, longueur des cheveux, "
           "silhouette plus fine ou plus ronde, looks tout prêts. Marche avec n'importe quel personnage calibré. "
           "Elle fait un petit défilé pour te montrer !",
         ex=["des cheveux roses", "coupe-toi les cheveux", "grossis un peu", "maigris", "un pull rayé bleu et blanc", "jupe à carreaux rouge et noire", "enlève tes collants",
             "look gothique", "remets ton look d'origine", "montre ta tenue"],
         kw={"en": ["change your look"], "es": ["cambia tu look"], "ru": ["смени образ"], "zh": ["换个造型"],
             "ja": ["見た目を変えて"], "hi": ["अपना लुक बदलो"]},
         rx={"en": [r"change your (?:look|style|outfit)"], "es": [r"cambia tu (?:look|estilo)"], "ru": [r"смени (?:образ|стиль)"],
             "zh": [r"换.*造型"], "ja": [r"見た目.*変え"], "hi": [r"लुक बदलो"]}),
    dict(id="mouvements", cat="elle", ico="💃", canon="applaudis",
         t={"fr": "Ses mouvements", "en": "Her moves", "es": "Sus movimientos", "ru": "Её движения", "zh": "她的动作",
            "ja": "動き", "hi": "उसकी हरकतें"},
         d="Demande-lui un geste : coucou, victoire, applaudir, rire, oui ou non de la tête, défilé, danse, bouder, "
           "s'étirer…",
         ex=["fais la victoire", "fais coucou", "applaudis", "fais non de la tête", "montre ta tenue", "danse pour moi"],
         kw={"en": ["clap", "wave"], "es": ["aplaude", "saluda"], "ru": ["похлопай", "помаши"], "zh": ["鼓掌", "挥手"],
             "ja": ["拍手して", "手を振って"], "hi": ["ताली बजाओ", "हाथ हिलाओ"]},
         rx={"en": [r"^clap\b"], "es": [r"^aplaude"], "ru": [r"^похлопай"], "zh": [r"^鼓掌"], "ja": [r"拍手"], "hi": [r"ताली"]}),
    dict(id="assistant", cat="elle", ico="🪄", canon="relance l'assistant de démarrage",
         t={"fr": "Assistant de démarrage", "en": "Setup wizard", "es": "Asistente de inicio", "ru": "Мастер настройки",
            "zh": "设置向导", "ja": "セットアップウィザード", "hi": "शुरुआती सहायक"},
         d="Les premiers réglages en une minute : prénom, langue, personnage, ce que tu veux activer, ce que ton PC "
           "peut faire. Aussi dans Réglages → Accueil.",
         ex=["relance l'assistant de démarrage"],
         kw={"en": ["setup wizard"], "es": ["asistente de inicio"], "ru": ["мастер настройки"], "zh": ["设置向导"],
             "ja": ["セットアップ"], "hi": ["शुरुआती सहायक"]},
         rx={"en": [r"setup wizard"], "es": [r"asistente de (?:inicio|configuracion)"], "ru": [r"мастер настройки"],
             "zh": [r"设置向导"], "ja": [r"セットアップ"], "hi": [r"शुरुआती सहायक"]}),
    # ---------------------------------------------------------------- apprendre
    dict(id="commande_perso", cat="parler", ico="🗣️", canon="mes commandes",
         t={"fr": "Tes propres commandes", "en": "Your own commands", "es": "Tus propios comandos",
            "ru": "Свои команды", "zh": "自定义命令", "ja": "自分のコマンド", "hi": "अपनी कमांड"},
         d="Apprends-lui une phrase à toi, même pour plusieurs actions d'un coup. Si elle se trompe, corrige-la : "
           "elle retient pour la prochaine fois.",
         ex=["quand je dis mode chill, mets ma playlist chill et le mode nuit", "non, je voulais dire ma playlist chill",
             "mes commandes", "oublie la commande mode chill"],
         kw={"en": ["my commands"], "es": ["mis comandos"], "ru": ["мои команды"], "zh": ["我的命令"], "ja": ["マイコマンド"],
             "hi": ["मेरी कमांड"]},
         rx={"en": [r"^my commands$"], "es": [r"^mis comandos$"], "ru": [r"^мои команды$"], "zh": [r"^我的命令$"],
             "ja": [r"^マイコマンド$"], "hi": [r"^मेरी कमांड"]}),
    dict(id="journee", cat="jour", ico="📅", canon="résumé de ma journée",
         t={"fr": "Ta journée", "en": "Your day", "es": "Tu día", "ru": "Твой день", "zh": "你的一天", "ja": "今日のまとめ",
            "hi": "तुम्हारा दिन"},
         d="Le temps passé par activité, tes projets, ce que tu lui as demandé. « Qu'est-ce que je faisais tout à "
           "l'heure ? » pour les dernières heures.",
         ex=["résumé de ma journée", "qu'est-ce que je faisais tout à l'heure ?", "qu'est-ce que tu sais sur moi ?"],
         kw={"en": ["my day", "what was I doing"], "es": ["mi día", "qué estaba haciendo"], "ru": ["мой день"],
             "zh": ["我的一天"], "ja": ["今日のまとめ"], "hi": ["मेरा दिन"]},
         rx={"en": [r"^(?:my day|summary of my day)$", r"^what was i doing"], "es": [r"^(?:mi dia|resumen de mi dia)$"],
             "ru": [r"^мой день$"], "zh": [r"^我的一天$"], "ja": [r"^今日のまとめ"], "hi": [r"^मेरा दिन"]}),
    # ---------------------------------------------------------------- aide
    dict(id="aide", cat="astuces", ico="❓", canon="__aide",
         t={"fr": "Ouvrir cette aide", "en": "Open this help", "es": "Abrir esta ayuda", "ru": "Открыть справку",
            "zh": "打开帮助", "ja": "ヘルプを開く", "hi": "मदद खोलो"},
         d="Cette fenêtre de trucs et astuces.", ex=["aide", "que sais-tu faire ?", "astuces"],
         kw={"en": ["help", "what can you do"], "es": ["ayuda"], "ru": ["помощь"], "zh": ["帮助"], "ja": ["ヘルプ"],
             "hi": ["मदद"]},
         rx={"fr": [r"^(?:aide|aide-moi a t'utiliser|astuces?|trucs et astuces|que sais[- ]tu faire|tu sais faire quoi|"
                    r"qu'?est[- ]ce que tu sais faire|comment (?:je )?t'utiliser)$"],
             "en": [r"^(?:help|tips|what can you do)$"], "es": [r"^(?:ayuda|que sabes hacer)$"], "ru": [r"^(?:помощь|что ты умеешь)"],
             "zh": [r"^(?:帮助|你会做什么)"], "ja": [r"^(?:ヘルプ|何ができる)"], "hi": [r"^(?:मदद|तुम क्या कर सकती हो)"]}),
]

ASTUCES = [
    "Double-clic sur elle : tu peux lui écrire tout de suite.",
    "Clic droit sur elle : tape ce que tu veux faire dans « Que veux-tu faire ? », puis Entrée.",
    "Glisse un fichier sur elle (PDF, image, manga, musique, code…) : elle te propose quoi en faire.",
    "Sélectionne un texte n'importe où et dis « traduis la sélection » ou « lis-moi la sélection ».",
    "« Qu'est-ce qu'il y a sur mon écran ? » : elle le regarde avec une IA locale et te le décrit.",
    "Sur un portable, elle se fait plus légère toute seule quand tu es sur batterie.",
    "Réglages → Accessibilité : texte plus grand, contraste élevé, tout lu à voix haute.",
    "Elle fête son anniversaire le jour où tu l'as installée. 🎂",
    "Tu peux lui parler naturellement : « mets One Piece », « l'actu sur l'espace », « trouve mon CV ».",
    "Les petites fautes passent : « mes musique chill » marche aussi bien que « mets ma musique chill ».",
    "Dans « Ma liste », mets plusieurs sites pour un même titre et choisis le navigateur de chaque lien (clic droit).",
    "Réglages → Apparence → « Raccourcis à côté d'elle » : une colonne de boutons qui la suit.",
    "L'accueil (🏠) se personnalise : ✏️ « Choisir mes raccourcis ».",
    "Tu peux lui parler en anglais, espagnol, russe, chinois, japonais ou hindi : les commandes de base marchent.",
    "« Chut » la fait taire, « tu peux reparler » la réveille.",
    "Le soir, active le mode nuit automatique : voix plus douce et fenêtres sombres.",
    "Copie un message d'erreur et dis « explique cette erreur ».",
    "Dans l'atelier d'images, le bouton 📜 Journal montre ce qui s'est passé si une image rate.",
    "« Garde ce souvenir : … » : elle te le rappellera dans un mois, ou un an.",
    "Tout reste sur ton PC. Internet seulement quand tu le demandes ou l'actives.",
    "« Quand je dis mode chill, mets ma playlist chill et le mode nuit » : elle apprend ta propre commande.",
    "Elle s'est trompée ? Dis « non, je voulais dire … » : elle retient pour la prochaine fois.",
    "Pendant un appel, un jeu ou un film, elle se fait discrète toute seule.",
    "« Quels ports sont ouverts ? » : elle te montre ce qui est joignable depuis ton réseau et ta box.",
    "Une question de culture ? Elle te propose d'ouvrir Wikipédia sur le sujet.",
]


def title(a, lang):
    return a["t"].get(lang) or a["t"]["en"]


def random_tip():
    return random.choice(ASTUCES)


# ------------------------------------------------------------------ traduction des commandes
def to_french(text):
    """Commande dans une autre langue -> commande française, sinon None."""
    raw = (text or "").strip().rstrip(" !?.。！？")
    if not raw:
        return None
    low = raw.lower()
    sa = _sa(raw).strip()
    for a in sorted(ACTIONS, key=lambda a: "{x}" in a["canon"]):
        for lang, pats in a.get("rx", {}).items():
            if lang == "fr":
                continue
            src = sa if lang in LATIN else low
            for p in pats:
                m = re.search(p, src, re.I)
                if not m:
                    continue
                g = m.groupdict()
                if g.get("n"):                                 # « next episode »
                    return "épisode suivant"
                x = (g.get("x") or "").strip(" :,")
                if g.get("y"):
                    x = (x + " " + g["y"]).strip()
                if lang in LATIN and x:                         # on reprend la casse d'origine
                    i = sa.find(_sa(x))
                    if i >= 0:
                        x = raw[i:i + len(x)]
                if a["id"] == "rappel" and lang in ("en", "es"):
                    x = re.sub(r"\b(?:in|en) (\d+) (?:minutes?|minutos?|mins?)\b", r"dans \1 minutes", x, flags=re.I)
                    x = re.sub(r"\b(?:in|en) (\d+) (?:hours?|horas?)\b", r"dans \1 heures", x, flags=re.I)
                    x = re.sub(r"\b(?:at|a las) (\d{1,2})(?::(\d{2}))?\b", lambda mm: f"à {mm.group(1)}h{mm.group(2) or ''}",
                               x, flags=re.I)
                    x = re.sub(r"^(?:to |de |que )", "de ", x)
                    x = re.sub(r"(minutes|heures|h\d*)\s+(?:to|que)\s+", r"\1 de ", x)
                if a["id"] == "minuteur":
                    x = re.sub(r"(minutes?|minutos?|минут\w*|分钟|分|मिनट)", "minutes", x)
                    x = re.sub(r"(hours?|horas?|час\w*|小时|時間|घंटे)", "heures", x)
                    x = re.sub(r"(seconds?|segundos?|секунд\w*|秒|सेकंड)", "secondes", x)
                if "{x}" in a["canon"] and not x and a["id"] not in ("actu",):
                    continue
                if a["id"] == "regarder" and re.search(r"^(?:play|put on|pon|ponme|reproduce|включи|поставь|播放)|"
                                                       r"(?:再生|かけて|चलाओ|लगाओ)", src):
                    return ("mets " + x).strip()
                if a["id"] == "musique" and x:
                    return "je veux écouter " + x
                if a["id"] == "fichier" and not re.match(r"^(?:mon|ma|mes|le|la|les)\b", x, re.I):
                    return "trouve mon " + x
                return a["canon"].replace("{x}", x).strip()
    return None


def is_help(text):
    t = _sa(text).strip(" ?!.")
    a = next(a for a in ACTIONS if a["id"] == "aide")
    return any(re.search(p, t if lang in LATIN else (text or "").lower()) for lang, ps in a["rx"].items() for p in ps)


# ------------------------------------------------------------------ fenêtre
class TipsWindow(QWidget):
    def __init__(self, comp, lang="fr"):
        super().__init__(None, Qt.WindowType.Window)
        self.comp = comp
        self.setWindowTitle("💡 Trucs et astuces — " + comp.char.get("name", "Viki"))
        self.resize(900, 640)
        self.setStyleSheet("QFrame#carte { border: 1px solid palette(mid); border-radius: 12px; }"
                           "QLabel#titre { font-size: 12pt; font-weight: bold; }"
                           "QLabel#aide { color: palette(placeholder-text); }"
                           "QLabel#kw { background: palette(alternate-base); border-radius: 8px; padding: 4px 8px; }")
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.q = QLineEdit()
        self.q.setPlaceholderText("🔎 Chercher une action ou un mot-clé…")
        self.q.setClearButtonEnabled(True)
        self.q.textChanged.connect(lambda _t: self.show_cat())
        top.addWidget(self.q, 2)
        top.addWidget(QLabel("Mots-clés en :"))
        self.lang = QComboBox()
        for code, name in LANGS:
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(lang if lang in dict(LANGS) else "fr")))
        self.lang.currentIndexChanged.connect(lambda _i: (self._fill_cats(), self.show_cat()))
        top.addWidget(self.lang, 1)
        lay.addLayout(top)
        body = QHBoxLayout()
        self.cats = QListWidget()
        self.cats.setFixedWidth(210)
        self.cats.currentRowChanged.connect(lambda _r: self.show_cat())
        body.addWidget(self.cats)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        self.box = QWidget()
        self.rows = QVBoxLayout(self.box)
        self.rows.setSpacing(10)
        sc.setWidget(self.box)
        body.addWidget(sc, 1)
        lay.addLayout(body, 1)
        tip = QLabel("💡 " + random_tip())
        tip.setWordWrap(True)
        tip.setObjectName("aide")
        lay.addWidget(tip)
        self._fill_cats()
        self.cats.setCurrentRow(0)
        self.show_cat()

    def L(self):
        return self.lang.currentData()

    def _fill_cats(self):
        r = max(0, self.cats.currentRow())
        self.cats.blockSignals(True)
        self.cats.clear()
        for key, ico, names in CATS:
            self.cats.addItem(f"{ico}  {names.get(self.L()) or names['en']}")
        self.cats.setCurrentRow(r)
        self.cats.blockSignals(False)

    def _clear(self):
        while self.rows.count():
            w = self.rows.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def _lab(self, txt, obj=""):
        l = QLabel(txt)
        l.setWordWrap(True)
        l.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if obj:
            l.setObjectName(obj)
        return l

    def show_cat(self):
        self._clear()
        lang = self.L()
        q = _sa(self.q.text()).strip()
        key = CATS[max(0, self.cats.currentRow())][0]
        if key == "astuces" and not q:
            for t in ASTUCES:
                f = QFrame()
                f.setObjectName("carte")
                v = QVBoxLayout(f)
                v.addWidget(self._lab("💡 " + t))
                self.rows.addWidget(f)
        acts = [a for a in ACTIONS if (a["cat"] == key if not q else
                                       q in _sa(" ".join(a["t"].values()) + " " + a["d"] + " " + " ".join(a["ex"]) + " " +
                                                " ".join(k for ks in a["kw"].values() for k in ks)))]
        for a in acts:
            f = QFrame()
            f.setObjectName("carte")
            v = QVBoxLayout(f)
            v.addWidget(self._lab(f"{a['ico']}  {title(a, lang)}" + (f"   ·   {a['t']['fr']}" if lang != "fr" else ""),
                                  "titre"))
            v.addWidget(self._lab(a["d"], "aide"))
            row = QHBoxLayout()
            ex = QVBoxLayout()
            for e in a["ex"]:
                ex.addWidget(self._lab(f"« {e} »"))
            row.addLayout(ex, 1)
            if a["canon"] != "__aide":
                b = QPushButton("▶ Essayer")
                first = a["ex"][0]
                b.clicked.connect(lambda _=False, e=first: self._try(e))
                row.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
            v.addLayout(row)
            kws = a["kw"].get(lang) if lang != "fr" else None
            if kws:
                v.addWidget(self._lab(f"{dict(LANGS)[lang]} : " + "  ·  ".join(kws), "kw"))
            elif lang == "fr":
                others = "  ·  ".join(f"{c.upper()} « {a['kw'][c][0]} »" for c, _n in LANGS[1:] if a["kw"].get(c))
                if others:
                    v.addWidget(self._lab("Dans les autres langues : " + others, "kw"))
            self.rows.addWidget(f)
        if not acts and q:
            self.rows.addWidget(self._lab("Rien trouvé. Essaie un autre mot, ou demande-lui directement !"))
        self.rows.addStretch(1)

    def _try(self, example):
        cmd = re.sub(r"\s*\?$", "", example)
        if not self.comp._local_command(cmd):
            self.comp.say("Essaie de me le dire toi-même : « " + example + " » !")
