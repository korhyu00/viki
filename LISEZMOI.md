# Compagnon de bureau (KDE Plasma / CachyOS)

Un personnage animé qui vit sur ton bureau : il respire, se balance doucement,
cligne des yeux, saute quand tu cliques dessus et parle avec une voix française
générée en local (Piper), bouche synchronisée sur la voix.

## Installation

```bash
unzip compagnon.zip && cd compagnon
chmod +x install.sh && ./install.sh
./run.sh
```

## Utilisation

| Action | Effet |
|---|---|
| Clic gauche | elle sautille et dit une petite phrase |
| Double-clic | elle te donne l'heure |
| Glisser | la déplacer (la position est mémorisée) |
| Clic droit | menu : personnage, phrases, taille, premier plan, voix, discuter, quitter |
| Clic sur une zone | tête : yeux rieurs, rougeur, cœurs · cheveux : penche la tête · joue : rougit et fait un clin d'œil · nez : « boop » · main : coucou · bras : se tourne · épaule : sursaut « ! » · pieds : danse avec des notes · accessoire : fière, étoiles |
| Frotter la tête (sans cliquer) | caresse : elle ferme les yeux, rougit, des cœurs s'envolent |
| La secouer en la traînant | elle a le tournis (yeux en spirale) |
| Cliquer trop vite | elle s'agace et trépigne |
| Clic droit → Animations | danse, coucou, fredonne, s'étire, regarde autour, clin d'œil, bâille |
| Icône près de l'horloge | même menu + **mode fantôme** + afficher/cacher |

Elle ne gêne pas tes fenêtres : seuls ses pixels réagissent à la souris, et les
zones transparentes autour d'elle laissent passer les clics. Le **mode fantôme**
(dans le menu de l'icône) la rend semi-transparente et totalement traversable ;
on le désactive au même endroit.

Si elle est « bavarde », elle annonce les heures pile et te rappelle de temps
en temps de faire une pause ou de boire de l'eau.

## Expressions et humeur

Toute seule, de temps en temps, elle s'étire, regarde autour d'elle, fredonne,
fait un clin d'œil ou bâille (plus souvent la nuit). Elle se penche doucement
vers ta souris, hoche la tête en parlant, salue en arrivant et rebondit quand
tu la poses. Les zones tête, nez et joues sont créées automatiquement à partir
des yeux et de la bouche.

Elle sourit de temps en temps, rougit quand on lui caresse la tête, penche quand
tu la traînes à la souris, et **s'endort** (yeux fermés, petits « z ») si tu
la laisses seule 20 minutes. Un clic la réveille. « Faire une sieste » l'endort
tout de suite ; l'option « S'endort quand on la laisse seule » se coupe dans
le menu.

## Voix plus naturelle (optionnel, carte graphique AMD/NVIDIA conseillée)

```bash
./install_voix_naturelle.sh
```

Installe **Chatterbox Multilingual** (Resemble AI, licence MIT) dans un
environnement séparé, avec PyTorch ROCm pour les Radeon (réglé pour la
RX 6600). Environ 6 Go à télécharger. Si le script t'ajoute aux groupes
`video`/`render`, déconnecte-toi puis reconnecte-toi.

Ensuite : clic droit → **Voix → Naturelle (Chatterbox)**. Le premier chargement
prend un peu de temps, puis elle te prévient quand sa voix est prête.
Dans le même menu :

- **Expressivité** : calme, normale, expressive, très expressive ;
- **Choisir un extrait de voix (clonage)** : un enregistrement de 10 à 30 s,
  une seule personne, sans musique. Utilise ta propre voix ou celle de
  quelqu'un qui est d'accord.

Tout reste local : le modèle tourne sur ta carte graphique, le compagnon lui
parle via `127.0.0.1`. En cas de souci, regarde
`~/.config/compagnon/voix_naturelle.log` ; elle revient automatiquement à
Piper si la voix naturelle ne répond pas.

## Encore plus vivante

- **Ses yeux suivent ta souris** : l'iris et le blanc de l'œil sont détectés
  automatiquement à partir des 3 clics, pour n'importe quelle image.
- **Elle danse sur ta musique** (Spotify, VLC, navigateur… via `playerctl`) et
  annonce parfois le titre du morceau.
- **Humeur** (clic droit → Toi et elle) : caresses et attention la rendent ravie
  (plus de sourires et de cœurs) ; trop de clics, la secouer ou l'ignorer
  longtemps la rend boudeuse (paupières tombantes, petites remarques).
- **Ton prénom** et **ce dont elle se souvient** : elle t'appelle par ton prénom,
  et avec Ollama elle retient ce que tu lui racontes (goûts, projets…). Tout est
  dans `~/.config/compagnon/memoire.json`, modifiable ou effaçable depuis le menu.
- **Émotions dans le chat** : chaque réponse d'Ollama porte une émotion (joie,
  surprise, tristesse, bouderie, timidité) qui change son expression et, avec la
  voix naturelle, son intonation.
- **Routine** : café le matin, faim à midi, rappel pour dormir le soir ; elle
  s'endort plus vite la nuit.
- **Minuteur Pomodoro** (25/50 min de travail, 5 min de pause) : elle te prévient
  à la fin ; le temps restant s'affiche sur son icône.
- **Batterie faible** (portable) : elle te prévient à 15 %.
- **Ombre au sol** pour les personnages en pied.

## Discuter avec elle

```bash
bash install_ollama.sh
```

Installe Ollama (version ROCm, réglée pour la RX 6600) et un modèle au choix :
`qwen2.5:7b` (conseillé, meilleur français) ou `llama3.2:3b` (plus léger, utile
si tu utilises aussi la voix naturelle, les deux se partagent les 8 Go de la
carte graphique).

Pour installer d'autres modèles **sans terminal** : clic droit →
**Modèles de discussion (installer / choisir)…**. Choisis dans la liste
(taille indiquée), clique sur **Installer** (barre de progression), puis
**Utiliser**. Le champ « Autre modèle Ollama » accepte n'importe quel nom de la
bibliothèque Ollama ; **Supprimer** libère la place sur le disque.

Ensuite : clic droit → **Discuter avec elle…** ouvre une fenêtre de discussion
(historique, Entrée pour envoyer). Elle répond par écrit, dans sa bulle et à
voix haute, avec l'émotion qui va avec. Si tu as plusieurs modèles, choisis-le
dans **Modèle de discussion**. Tout reste sur ton PC.

## Supprimer un personnage

Clic droit → **Personnage → Supprimer un personnage** (confirmation demandée).
Rubis, le personnage fourni, ne peut pas être supprimée ; si tu supprimes celui
qui est affiché, elle reprend sa place.

## KDE Wayland

`run.sh` lance l'appli en XWayland (`QT_QPA_PLATFORM=xcb`) : c'est ce qui
permet le premier plan, la position mémorisée et les clics traversants.
Si jamais elle passe derrière les fenêtres, va dans
*Paramètres système → Gestion des fenêtres → Règles de fenêtres*, ajoute une
règle pour la classe `compagnon` avec « Garder au-dessus : Forcer — Oui ».

## Changer l'image et les textes

Tout se fait depuis le clic droit (ou l'icône près de l'horloge) :

- **Personnage → Nouveau personnage depuis une image…** : choisis une image.
  Si elle a un fond, il est retiré automatiquement (si le détourage a été
  installé ; sinon `.venv/bin/pip install "rembg[cpu]"`). Une fenêtre s'ouvre :
  donne-lui un nom, une personnalité pour le chat, puis clique sur l'œil gauche,
  l'œil droit et la bouche. Une zone « Tête » est créée automatiquement.
  Ensuite (optionnel) choisis un type de zone (tête, cheveux, main, épaule,
  pieds) et dessine des rectangles en glissant sur l'image.
  Les images **en pied** marchent aussi : utilise Zoom + (ou Ctrl + molette)
  pour viser précisément les yeux et la bouche.
- **Personnage → (liste)** : passer d'un personnage à l'autre.
- **Personnage → Replacer les yeux, la bouche et les zones…** : pour corriger
  les 3 points ou ajouter / retirer des zones.
- **Modifier les phrases…** : un onglet par situation (au clic, spontanées,
  salutations, heure, chaque zone, après un déplacement, au réveil).
  Une phrase par ligne ; `{heure}` et `{nom}` sont remplacés automatiquement.
  Chaque personnage a ses propres phrases.

Au moment de retirer le fond, tu choisis **Anime (rapide)**, **Précis** (plus
lent, garde mieux les mèches fines, mains et accessoires) ou **Garder le fond**.
Si un morceau manque dans la fenêtre de calibrage (damier), annule et
recommence avec l'autre choix.

Astuce : une image PNG avec fond transparent, personnage en pied ou à mi-corps,
visage de face, donne le meilleur résultat.

Les personnages ajoutés sont rangés dans `~/.config/compagnon/personnages/`,
les réglages dans `~/.config/compagnon/config.json`
(`volume` entre 0 et 1, `ollama_model`, etc.).
