# Fichiers volumineux (> 1000 lignes)

Quand un fichier dépasse ~1000 lignes :

1. Avant de le faire grossir davantage, étudier si une modularisation
   en plusieurs fichiers est possible sans tout casser (découpage par
   responsabilité, pas en tranches arbitraires).
2. Si c'est le cas, l'implémenter plutôt que d'empiler.
3. Si le découpage est trop risqué/coûteux, documenter pourquoi dans
   le fichier (commentaire en tête) avant d'y ajouter du code.

Principes de découpage pour ce projet :

- `ui/` : un module par zone fonctionnelle (un onglet / une fenêtre).
  Les widgets créés dans un module sont exposés sur `self` de la
  fenêtre (mixins sans `__init__`) — pas de refactor des signatures.
- `nextevents/` : un module par domaine métier (fetch, rendu, synchro,
  secrets) — le package reste le point d'entrée public.
- Après un split : l'app doit démarrer (`python desktop.py`), aucun
  comportement ne doit changer — déplacement de code, pas réécriture.
