# Focus Time

Plateforme Streamlit d’inscription en remédiation et de répartition en dépassement. Les données sont enregistrées uniquement dans Supabase, dans les tables `ft2_*`. Une nouvelle séance est vide : l’administrateur ajoute les activités manuellement ou importe un fichier CSV.

## Installation initiale

1. Exécuter `sql/01_schema.sql` dans l’éditeur SQL Supabase pour créer les tables et fonctions `ft2_*`. Ce script ne contient aucun jeu d’activités de départ ni migration d’anciennes tables.
2. Renseigner les comptes dans `ft2_people` : `email`, `name`, `degree`, `is_admin`.
3. Pour les élèves, utiliser les degrés 1, 2 ou 3. Pour les professeurs, utiliser le degré 4. Pour l’administrateur, utiliser le degré 4 et `is_admin = true`.

## Streamlit Community Cloud

Mettre le contenu du dossier du projet à la racine du dépôt GitHub. Déployer `main.py`, avec Python 3.12 et les dépendances de `requirements.txt`.

Dans les secrets de Community Cloud, utiliser `.streamlit/secrets.toml.example` comme modèle :

- `SUPABASE_URL` : URL du projet Supabase ;
- `SUPABASE_SERVICE_ROLE_KEY` : clé serveur du projet ;
- `[auth]` et `[auth.microsoft]` : configuration Microsoft Entra de l’école.

Le nom de configuration `SUPABASE_SERVICE_ROLE_KEY` accepte la clé serveur `service_role` ou sa remplaçante `sb_secret_…`. Ne pas utiliser une clé publique. La clé serveur reste dans les secrets, jamais dans le dépôt.

L’URL de retour déclarée dans Entra et dans les secrets doit être identique : `https://TON-APPLICATION.streamlit.app/oauth2callback`.

Le script SQL active le RLS et bloque les accès directs aux tables/fonctions pour `anon` et `authenticated`. Le serveur Streamlit vérifie la connexion Microsoft et les rôles. Les opérations de gestion et de finalisation contrôlent également les droits administrateur dans SQL. Aucune politique RLS supplémentaire n’est nécessaire pour cette architecture.

[Déployer dans Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), [configurer les secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management), [connexion Microsoft](https://docs.streamlit.io/develop/tutorials/authentication/microsoft), [clés API Supabase](https://supabase.com/docs/guides/getting-started/api-keys).

## Créer une séance

L’administrateur ouvre « Créer une séance », renseigne le nom, la date, l’ouverture et la fin des inscriptions, puis sélectionne D1, D2 et/ou D3 dans la liste « Degrés participants ».

La liste des élèves participants est copiée à la création de la séance. Les comptes doivent donc être complets avant la création. Les élèves ajoutés ultérieurement ne sont pas ajoutés rétroactivement à cette séance.

Les horaires utilisent Europe/Brussels. La fin des inscriptions ne déclenche aucun calcul : seul le bouton administrateur « Répartir les élèves » lance la répartition.

## Ajouter les remédiations et dépassements

Dans « Gestion des activités », renseigner :

- le degré de l’activité ;
- le type : Remédiation ou Dépassement ;
- le nom de l’activité ;
- le professeur, dans son propre champ ;
- le local, dans son propre champ ;
- le nombre maximum de places, par défaut 12 ;
- éventuellement « Sans limite de places » ;
- P9 et/ou P10 dans la liste « Périodes proposées ».

Le nom, le professeur et le local sont obligatoires. Si « Sans limite de places » est coché, la valeur du nombre maximum est ignorée et la capacité est enregistrée à `null` dans Supabase. Les capacités finies doivent être des entiers strictement positifs. Cette possibilité existe pour les deux types d’activités.

Sélectionner P9 et P10 crée deux groupes indépendants. Il n’existe plus d’activité P910 de deux heures.

### Le nom remplace la clé

Aucune clé d’activité n’est à saisir ou à importer. Le nom identifie l’activité entre les périodes, sans tenir compte des majuscules/minuscules ni des espaces au début et à la fin.

Par exemple, « Mathématiques » en P9 et « mathématiques » en P10 désignent la même activité. Un élève ne peut pas suivre les deux, même si le professeur ou le local change. Un nom ne peut pas exister deux fois pour le même degré et la même période, même sous deux types différents.

Les activités de D1, D2 et D3 sont indépendantes. Un même nom peut apparaître dans plusieurs degrés. La base conserve une copie normalisée du nom dans `ft2_assignments.activity_name` uniquement pour faire respecter cette unicité ; ce n’est pas une clé supplémentaire à gérer.

### L’étude est une activité ordinaire

Aucune activité nommée « Étude » n’est créée automatiquement, reconnue comme spéciale ou réservée dans le code. Pour la proposer, créer un dépassement nommé « Étude », renseigner son professeur et son local, puis choisir sa capacité comme pour toute autre activité.

Un dépassement « Étude » avec 10 places est un groupe limité et donc prioritaire. Un dépassement « Lecture libre » sans limite est un groupe illimité utilisé après les groupes limités. C’est la capacité qui détermine la priorité, pas le nom.

## Importer un CSV

Le fichier `activities.example.csv` contient neuf activités fictives réparties sur D1, D2 et D3, soit 18 groupes P9/P10. Il est fourni en UTF-8 avec séparateur point-virgule pour une ouverture dans Excel et n’est jamais importé automatiquement.

Dans « Gestion des activités » → « Importer plusieurs activités depuis un CSV », choisir le fichier, vérifier l’aperçu et cliquer sur « Importer les activités ».

Format : une activité par ligne, avec les colonnes suivantes. Les en-têtes doivent être écrits exactement comme ci-dessous.

```csv
degree;name;professor;room;kind;periods;capacity;unlimited
D2;Robotique;Mme Exemple;Salle informatique;depassement;9|10;16;false
D2;Étude;M. Exemple;Salle d'étude;depassement;9|10;;true
D3;Anglais;Mme Exemple;C1;remediation;9;12;false
```

| Colonne | Valeur |
|---|---|
| `degree` | D1, D2 ou D3 (1, 2 ou 3 également acceptés) |
| `name` | Nom de l’activité |
| `professor` | Professeur obligatoire |
| `room` | Local obligatoire |
| `kind` | `remediation` ou `depassement` |
| `periods` | `9`, `10` ou `9&#124;10` ; P9/P10 acceptés avec le même séparateur |
| `capacity` | Entier positif ; 12 si vide ou colonne absente |
| `unlimited` | `true` ou `false` ; `false` si vide/absent. Oui/non et 1/0 acceptés |

Si `unlimited` vaut `true`, la capacité est ignorée. Les colonnes `capacity` et `unlimited` sont facultatives ; les six premières sont obligatoires. Les CSV avec séparateur virgule sont également acceptés. Enregistrer le fichier en CSV UTF-8 ; les champs contenant le séparateur doivent être entre guillemets, ce qu’Excel fait lors de l’enregistrement.

Un fichier peut mélanger les degrés participants. Une ligne pour un degré absent de la séance provoque une erreur, sans être ignorée. Retirer cette ligne ou sélectionner une séance incluant ce degré.

L’import ajoute des groupes sans remplacer les activités existantes. Un doublon de nom pour un même degré/période ou une ligne invalide bloque tout l’import. La transaction SQL assure que tous les groupes sont ajoutés, ou aucun. L’interface accepte uniquement des fichiers CSV pour cet import.

## Supprimer une activité

Dans « Gestion des activités », sélectionner un groupe puis cliquer sur « Supprimer cette activité ». La suppression concerne un degré et une période. Pour supprimer les deux groupes P9/P10, effectuer les deux suppressions.

Un groupe contenant des élèves ne peut pas être supprimé : il faut d’abord annuler les inscriptions. Une séance finalisée ne peut plus être modifiée. Ces contrôles sont aussi appliqués dans Supabase.

## Supprimer une séance

L’administrateur peut ouvrir « Supprimer la séance » sous la séance sélectionnée. Il clique directement sur « Supprimer définitivement cette séance », sans saisie de confirmation.

La suppression concerne la séance complète, ses activités, sa liste de participants et toutes ses inscriptions, y compris si elle est finalisée. Elle ne supprime pas les comptes de `ft2_people` ni les autres séances. Elle est définitive et effectuée en une transaction. Le rôle administrateur est revérifié par la fonction SQL `ft2_delete_session` ; les professeurs non administrateurs n’ont pas ce bouton.

## Inscrire les élèves

Les professeurs voient uniquement « Inscrire un élève » et « Groupes par degré ». L’onglet « Répartition et Excel » est réservé à l’administrateur.

Après sélection du degré puis de l’élève, les activités autorisées du bon degré, à une période libre, non complètes et de nom différent d’une activité déjà choisie sont proposées.

Les capacités configurées sont appliquées dans l’interface et dans la base. Après une inscription ou une annulation, l’affichage se recharge automatiquement. Aucun bouton « Actualiser » n’est nécessaire ou présent.

Deux cases à cocher à la création de la séance configurent les inscriptions. Elles sont décochées par défaut et enregistrées dans `ft2_sessions` :

- « Autoriser les élèves à s'inscrire eux-mêmes » : `allow_student_enrollment`. Sans cette option, les élèves consultent uniquement leur planning.
- « Autoriser les inscriptions aux dépassements » : `allow_enrichment_enrollment`. Les professeurs peuvent inscrire dans les dépassements ; les élèves aussi si la première option est activée. Sinon, seules les remédiations sont accessibles manuellement.

Les élèves ne peuvent inscrire qu’eux-mêmes et annuler que leurs propres inscriptions (`source = student`). Ils ne peuvent pas retirer une inscription faite par un professeur. Les professeurs peuvent annuler les inscriptions manuelles des deux origines. Les inscriptions et annulations respectent les mêmes horaires pour tous et sont bloquées après finalisation. Les contrôles sont appliqués par les fonctions SQL, avec l’identité Microsoft transmise uniquement par le serveur Streamlit.

Le script `sql/01_schema.sql` reste un script d’installation initiale : ces champs et la nouvelle source `student` doivent être présents dans Supabase avant d’utiliser cette version. Il ne met pas à jour des tables déjà créées.

## Répartition et Excel

Seul le clic administrateur sur « Répartir les élèves » déclenche le traitement. Aucun worker, aucune tâche programmée et aucun calcul au simple affichage de la page.

Le calcul conserve toutes les inscriptions existantes, y compris les dépassements choisis manuellement, et attribue les périodes libres aux dépassements :

- le degré doit correspondre ;
- chaque élève a une activité en P9 et une en P10 ;
- une activité de même nom ne peut pas être répétée ;
- les capacités finies sont respectées ;
- les dépassements à capacité limitée sont sélectionnés en priorité ;
- les dépassements sans limite accueillent ensuite les élèves restants.

Le calcul traite les deux périodes ensemble et minimise le nombre d’affectations dans les groupes illimités. Le départage entre les solutions se fait aléatoirement. La priorité s’applique sous réserve des contraintes : une place finie peut rester libre si y placer un élève empêcherait une répartition complète respectant les degrés et les noms différents.

Si aucune répartition complète n’est possible, aucun ajout automatique n’est enregistré. Ajouter un dépassement différent ou une capacité adaptée avant de relancer. Une activité illimitée ne peut pas être suivie deux fois sous le même nom.

La base vérifie les rôles, les places, les noms, les périodes et la révision de la séance. Si une inscription ou une activité change pendant le calcul, le plan est refusé : relancer la génération.

Le clic peut intervenir avant ou après la fin prévue des inscriptions. S’il réussit, la séance est finalisée et les inscriptions sont fermées. Le bouton « Télécharger l’Excel » apparaît ensuite. Le classeur contient trois feuilles D1, D2 et D3 dans la disposition du modèle « Focus Time 06-01-26.xlsx » : activités en colonnes, en-têtes colorés avec nom puis professeur/local, élèves listés en dessous, lignes grises et blanches alternées, grand libellé P9 à gauche puis second bloc P10 plus bas. Une même activité garde sa colonne et sa couleur entre les périodes. Si elle n’est proposée qu’à une période, l’autre bloc l’indique.

Chaque bloc prévoit au moins 12 lignes et s’étend au nombre réel d’élèves : aucun groupe illimité n’est tronqué. Les noms sont triés alphabétiquement selon le nom affiché. Une feuille sans activité porte une mention explicite. L’impression est configurée en A3 paysage, adaptée à la largeur, avec date et degré dans l’en-tête d’impression. Il n’y a plus de feuille Planning tabulaire.

Regénérer l’Excel après finalisation reprend les groupes enregistrés sans nouveau tirage. Le calcul est limité à 30 secondes ; s’il n’aboutit pas, l’administrateur peut relancer sans perdre les remédiations.

## Fichiers et tests

- `main.py` : interface et commandes par rôle.
- `service.py` : accès Supabase et finalisation.
- `allocator.py` : répartition avec priorité aux capacités finies.
- `activity_import.py` : validation du fichier CSV et comparaison des noms.
- `exports.py` : export Excel avec professeur/local.
- `activities.example.csv` : exemple à adapter et importer manuellement.
- `sql/01_schema.sql` : création initiale des tables/fonctions `ft2`.

Toutes les chaînes Python utilisent des guillemets doubles. Les littéraux SQL utilisent la syntaxe SQL habituelle.

Après installation de `requirements.txt`, lancer les tests depuis le dossier du projet :

```bash
python -m unittest discover -s tests -v
```

Tests SQL locaux facultatifs :

```bash
npm install --prefix tests @electric-sql/pglite
node tests/test_database.mjs
```

Node.js ne sert qu’à ces tests locaux et n’est pas nécessaire sur Community Cloud. Les résultats et limites sont dans `VALIDATION.md`.

Les listes de sélection affichent des invitations en français (« Choisir un élève », « Choisir une activité », etc.). Les champs de date et les dates affichées utilisent le format jour/mois/année.
